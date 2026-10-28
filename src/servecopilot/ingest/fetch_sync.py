import argparse
import json
import logging
import os
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
# Pause before GitHub's rate limit runs out; each page costs ~2 points.
RATE_LIMIT_FLOOR = 100

logger = logging.getLogger(__name__)


def read_token():
    token = os.getenv("GIT_API_KEY")
    if not token:
        raise SystemExit("GIT_API_KEY not set — add it to .env")
    return token


@dataclass(frozen=True)
class Settings:
    token: str
    owner: str = "vllm-project"
    repo: str = "vllm"
    limit: int = 500
    output_path: Path = Path("data/raw/issues.jsonl")

    @classmethod
    def from_env(cls, **overrides):
        return cls(token=read_token(), **overrides)


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError(f"must be > 0, got {value}")
    return number


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Fetch closed GitHub issues and their fixing PRs into JSONL."
    )
    parser.add_argument("--owner", default=Settings.owner)
    parser.add_argument("--repo", default=Settings.repo)
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=Settings.limit,
        help="minimum number of issues to fetch (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Settings.output_path,
        help="output JSONL path (default: %(default)s)",
    )
    return parser.parse_args(argv)


QUERY = """
query($owner: String!, $repo: String!, $cursor: String) {
    rateLimit {
        cost
        remaining
        resetAt
    }

  repository(owner: $owner, name: $repo) {
    issues(
      first: 100
      after: $cursor
      states: CLOSED
      orderBy: {field: CREATED_AT, direction: DESC}
    ) {
      nodes {
        number
        title
        body
        createdAt
        closedAt
        stateReason
        labels(first: 20) {
          totalCount
          nodes {
            name
          }
        }
        closedByPullRequestsReferences(first: 10) {
          totalCount
          nodes {
            number
            mergedAt
            repository {
              nameWithOwner
            }
          }
        }
      }

      pageInfo {
        hasNextPage
        endCursor
      }
    }
  }
}
"""


@contextmanager
def atomic_write(output_path):
    # Write to a temp file in the same directory, then atomically swap it in,
    # so a crash mid-write never leaves a half-written output_path behind.
    tmp_path = output_path.with_name(output_path.name + ".tmp")

    try:
        with open(tmp_path, "w", encoding="utf-8") as file:
            yield file
            file.flush()
            os.fsync(file.fileno())

        os.replace(tmp_path, output_path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_jsonl_lines(file, issues):
    file.writelines(json.dumps(issue, ensure_ascii=False) + "\n" for issue in issues)


def parse_issue(issue, repo_name):
    fixing_prs = []

    for pr in issue["closedByPullRequestsReferences"]["nodes"]:
        if (
            pr["mergedAt"] is not None
            and pr["repository"]["nameWithOwner"].lower() == repo_name.lower()
        ):
            fixing_prs.append(pr["number"])

    return {
        "number": issue["number"],
        "title": issue["title"],
        "body": issue["body"],
        "labels": [label["name"] for label in issue["labels"]["nodes"]],
        "created_at": issue["createdAt"],
        "closed_at": issue["closedAt"],
        "state_reason": issue["stateReason"],
        "fixing_prs": fixing_prs,
    }


def truncated_fields(issue):
    # A connection is truncated when GitHub has more items than it returned.
    return [
        field
        for field in ("labels", "closedByPullRequestsReferences")
        if issue[field]["totalCount"] > len(issue[field]["nodes"])
    ]


def seconds_until_reset(rate_limit, now):
    if rate_limit["remaining"] >= RATE_LIMIT_FLOOR:
        return 0.0

    reset_at = datetime.fromisoformat(rate_limit["resetAt"])
    return max(0.0, (reset_at - now).total_seconds())


def check_graphql_errors(result):
    if "errors" in result:
        for error in result["errors"]:
            logger.error("GraphQL error: %s", error.get("message"))

        raise RuntimeError("GitHub GraphQL request failed")


def fetch_page(client, settings, cursor):
    response = client.post(
        GITHUB_GRAPHQL_URL,
        json={
            "query": QUERY,
            "variables": {
                "owner": settings.owner,
                "repo": settings.repo,
                "cursor": cursor,
            },
        },
    )

    response.raise_for_status()

    result = response.json()
    check_graphql_errors(result)

    return result["data"]


def run(settings):
    settings.output_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "Authorization": f"Bearer {settings.token}",
        "Content-Type": "application/json",
    }

    repo_name = f"{settings.owner}/{settings.repo}"
    issue_count = 0
    state_reasons = Counter()
    cursor = None
    request_count = 0

    start_time = time.perf_counter()

    with (
        httpx.Client(headers=headers, timeout=30) as client,
        atomic_write(settings.output_path) as output_file,
    ):
        while issue_count < settings.limit:
            data = fetch_page(client, settings, cursor)
            request_count += 1
            rate_limit = data["rateLimit"]

            logger.info(
                "GraphQL request cost=%d remaining=%d",
                rate_limit["cost"],
                rate_limit["remaining"],
            )

            issues = data["repository"]["issues"]
            for issue in issues["nodes"]:
                for field in truncated_fields(issue):
                    logger.warning(
                        "Issue #%d: %s truncated (%d of %d returned)",
                        issue["number"],
                        field,
                        len(issue[field]["nodes"]),
                        issue[field]["totalCount"],
                    )
                state_reasons[issue["stateReason"]] += 1

            write_jsonl_lines(
                output_file,
                (parse_issue(issue, repo_name) for issue in issues["nodes"]),
            )
            issue_count += len(issues["nodes"])

            logger.info("Fetched and wrote %d issues", issue_count)

            if not issues["pageInfo"]["hasNextPage"]:
                break

            cursor = issues["pageInfo"]["endCursor"]

            wait_seconds = seconds_until_reset(rate_limit, datetime.now(UTC))
            if wait_seconds:
                logger.warning(
                    "Rate limit low (remaining=%d); sleeping %.0fs until %s",
                    rate_limit["remaining"],
                    wait_seconds,
                    rate_limit["resetAt"],
                )
                time.sleep(wait_seconds + 1)

    logger.info("Wrote %d issues to %s", issue_count, settings.output_path)
    logger.info("State reasons: %s", dict(state_reasons))

    logger.info("Api calls made for %d is %d  ", settings.limit, request_count)
    elapsed_time = time.perf_counter() - start_time

    logger.info(
        "Total fetch time: %.2f seconds",
        elapsed_time,
    )


def main(argv=None):
    args = parse_args(argv)
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    run(Settings.from_env(**vars(args)))


if __name__ == "__main__":
    main()
