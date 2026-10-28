import json

import httpx
import pytest

from servecopilot.ingest import fetch_sync
from servecopilot.ingest.fetch_sync import Settings, run


def make_issue(number):
    return {
        "number": number,
        "title": f"issue {number}",
        "body": None,
        "createdAt": "2026-01-01T00:00:00Z",
        "closedAt": "2026-01-02T00:00:00Z",
        "stateReason": "COMPLETED",
        "labels": {"totalCount": 0, "nodes": []},
        "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
    }


def make_page(numbers, has_next_page):
    return {
        "rateLimit": {
            "cost": 1,
            "remaining": 4999,
            "resetAt": "2026-01-01T01:00:00Z",
        },
        "repository": {
            "issues": {
                "nodes": [make_issue(n) for n in numbers],
                "pageInfo": {"hasNextPage": has_next_page, "endCursor": "c"},
            }
        },
    }


def test_run_writes_all_pages(tmp_path, monkeypatch):
    pages = iter([make_page([1, 2], True), make_page([3], False)])
    monkeypatch.setattr(fetch_sync, "fetch_page", lambda *args: next(pages))
    output_path = tmp_path / "issues.jsonl"

    run(Settings(token="t", limit=10, output_path=output_path))

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["number"] for line in lines] == [1, 2, 3]
    assert not (tmp_path / "issues.jsonl.tmp").exists()


def test_run_crash_on_page_two_keeps_old_file(tmp_path, monkeypatch):
    def fake_fetch_page(client, settings, cursor):
        if cursor is None:
            return make_page([1, 2], True)
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(fetch_sync, "fetch_page", fake_fetch_page)
    output_path = tmp_path / "issues.jsonl"
    output_path.write_text('{"number": 99}\n', encoding="utf-8")

    with pytest.raises(httpx.ConnectError):
        run(Settings(token="t", limit=10, output_path=output_path))

    assert output_path.read_text(encoding="utf-8") == '{"number": 99}\n'
    assert not (tmp_path / "issues.jsonl.tmp").exists()


def test_run_sleeps_when_rate_limit_is_low(tmp_path, monkeypatch):
    first_page = make_page([1], True)
    first_page["rateLimit"]["remaining"] = 5
    first_page["rateLimit"]["resetAt"] = "2999-01-01T00:00:00Z"
    pages = iter([first_page, make_page([2], False)])
    monkeypatch.setattr(fetch_sync, "fetch_page", lambda *args: next(pages))
    sleeps = []
    monkeypatch.setattr(fetch_sync.time, "sleep", sleeps.append)

    run(Settings(token="t", limit=10, output_path=tmp_path / "issues.jsonl"))

    assert len(sleeps) == 1
    assert sleeps[0] > 0
