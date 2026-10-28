import argparse
import asyncio
import json
import logging
import random
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

from servecopilot.ingest.fetch_sync import (
    GITHUB_GRAPHQL_URL,
    Settings,
    atomic_write,
    check_graphql_errors,
    positive_int,
    read_token,
    write_jsonl_lines,
)

logger = logging.getLogger(__name__)

# Transient server-side failures that are worth retrying.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
BASE_DELAY = 1.0
MAX_DELAY = 30.0
REQUEST_TIMEOUT = 30.0
# GitHub documents a secondary limit of 100 concurrent requests.
MAX_CONCURRENCY = 100

# Errors that mean "this one PR failed" (HTTP/network failures after retries,
# GraphQL errors, unexpected response shape). Anything else is a bug: let it crash.
PR_FETCH_ERRORS = (httpx.HTTPError, TimeoutError, RuntimeError, KeyError, TypeError)


@dataclass(frozen=True)
class PRSettings:
    token: str
    owner: str = Settings.owner
    repo: str = Settings.repo
    input_path: Path = Settings.output_path
    output_path: Path = Path("data/raw/prs.jsonl")
    concurrency: int = 32

    @classmethod
    def from_env(cls, **overrides):
        return cls(token=read_token(), **overrides)


def concurrency_limit(value):
    number = positive_int(value)
    if number > MAX_CONCURRENCY:
        raise argparse.ArgumentTypeError(
            f"must be <= {MAX_CONCURRENCY} (GitHub's concurrent request limit)"
        )
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch details of the fixing PRs listed in an issues JSONL file."
    )
    parser.add_argument("--owner", default=PRSettings.owner)
    parser.add_argument("--repo", default=PRSettings.repo)
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        default=PRSettings.input_path,
        help="issues JSONL from servecopilot-ingest (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=PRSettings.output_path,
        help="output JSONL path (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency",
        type=concurrency_limit,
        default=PRSettings.concurrency,
        help="max requests in flight (default: %(default)s)",
    )
    return parser.parse_args(argv)


QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
    repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
            number
            title
            body
            mergedAt
            files(first: 100) {
                nodes {
                    path
                }
            }
        }
    }
}
"""


def get_needed_prs(data_path):
    pr_numbers = set()

    with open(Path(data_path), encoding="utf-8") as f:
        for line in f:
            issue = json.loads(line)

            for pr_number in issue["fixing_prs"]:
                pr_numbers.add(pr_number)

    logger.info("Unique PRs: %d", len(pr_numbers))

    return pr_numbers


def is_retryable(response):
    if response.status_code in RETRY_STATUSES:
        return True

    # GitHub signals secondary rate limits with 403 plus one of these headers.
    # A plain 403 (e.g. missing permission) will not fix itself, so don't retry it.
    return response.status_code == 403 and (
        "retry-after" in response.headers
        or response.headers.get("x-ratelimit-remaining") == "0"
    )


def retry_after_seconds(response, now):
    if "retry-after" in response.headers:
        return float(response.headers["retry-after"])

    if response.headers.get("x-ratelimit-remaining") == "0":
        reset_at = float(response.headers["x-ratelimit-reset"])
        return max(0.0, reset_at - now)

    return None


def backoff_delay(attempt):
    # "Full jitter": pick uniformly in [0, cap] so many clients that failed
    # together don't all retry at the same moment.
    cap = min(MAX_DELAY, BASE_DELAY * 2**attempt)
    return random.uniform(0, cap)


async def post_with_retry(client, semaphore, payload, stats, sleep=asyncio.sleep):
    for attempt in range(MAX_ATTEMPTS):
        retry_after = None

        try:
            # Hold a concurrency slot only while the request is in flight,
            # not while backing off, so other tasks can use it.
            async with semaphore, asyncio.timeout(REQUEST_TIMEOUT):
                stats["requests"] += 1
                response = await client.post(GITHUB_GRAPHQL_URL, json=payload)
        except (httpx.TransportError, TimeoutError) as error:
            reason = repr(error)
            if attempt == MAX_ATTEMPTS - 1:
                raise
        else:
            if response.is_success:
                return response
            if not is_retryable(response) or attempt == MAX_ATTEMPTS - 1:
                response.raise_for_status()
            reason = f"HTTP {response.status_code}"
            retry_after = retry_after_seconds(response, time.time())

        delay = retry_after if retry_after is not None else backoff_delay(attempt)
        stats["retries"] += 1
        logger.warning(
            "Attempt %d/%d failed (%s); retrying in %.1fs",
            attempt + 1,
            MAX_ATTEMPTS,
            reason,
            delay,
        )
        await sleep(delay)


async def fetch_pr(client, semaphore, settings, pr_number, stats, sleep=asyncio.sleep):
    payload = {
        "query": QUERY,
        "variables": {
            "owner": settings.owner,
            "repo": settings.repo,
            "number": pr_number,
        },
    }
    response = await post_with_retry(client, semaphore, payload, stats, sleep)

    result = response.json()
    check_graphql_errors(result)

    pr = result["data"]["repository"]["pullRequest"]

    return {
        "number": pr["number"],
        "title": pr["title"],
        "body": pr["body"],
        "merged_at": pr["mergedAt"],
        "changed_files": [file["path"] for file in pr["files"]["nodes"]],
    }


async def fetch_all(client, settings, pr_numbers, stats, sleep=asyncio.sleep):
    semaphore = asyncio.Semaphore(settings.concurrency)
    results = []
    failures = []

    async def fetch_one(pr_number):
        # Catch per PR so one bad PR doesn't make TaskGroup cancel all the others.
        try:
            results.append(
                await fetch_pr(client, semaphore, settings, pr_number, stats, sleep)
            )
        except PR_FETCH_ERRORS as error:
            logger.error("PR #%d failed: %r", pr_number, error)
            failures.append(pr_number)

    async with asyncio.TaskGroup() as tg:
        for pr_number in pr_numbers:
            tg.create_task(fetch_one(pr_number))

    results.sort(key=lambda pr: pr["number"])
    return results, sorted(failures)


async def run(settings):
    if not settings.input_path.exists():
        raise SystemExit(
            f"{settings.input_path} not found — run servecopilot-ingest first"
        )
    settings.output_path.parent.mkdir(parents=True, exist_ok=True)

    pr_numbers = get_needed_prs(settings.input_path)
    headers = {
        "Authorization": f"Bearer {settings.token}",
        "Content-Type": "application/json",
    }
    stats = Counter()

    start_time = time.perf_counter()
    async with httpx.AsyncClient(headers=headers) as client:
        results, failures = await fetch_all(client, settings, pr_numbers, stats)
    elapsed_time = time.perf_counter() - start_time

    with atomic_write(settings.output_path) as output_file:
        write_jsonl_lines(output_file, results)

    logger.info("Wrote %d PRs to %s", len(results), settings.output_path)
    logger.info(
        "PRs: %d ok, %d failed | requests=%d retries=%d | concurrency=%d | %.2fs",
        len(results),
        len(failures),
        stats["requests"],
        stats["retries"],
        settings.concurrency,
        elapsed_time,
    )

    if failures:
        raise SystemExit(f"{len(failures)} PRs failed: {failures}")


def main(argv=None):
    args = parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run(PRSettings.from_env(**vars(args))))


if __name__ == "__main__":
    main()
