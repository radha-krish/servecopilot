import json
from pathlib import Path

from servecopilot.ingest.fetch_sync import parse_issue, truncated_fields


def test_parse_issue():
    fixture_path = Path(__file__).parent / "fixtures" / "issue.json"

    with open(fixture_path, encoding="utf-8") as file:
        issue = json.load(file)

    result = parse_issue(issue, "vllm-project/vllm")

    assert result["number"] == 123
    assert result["title"] == "Example GPU issue"
    assert result["labels"] == ["bug", "cuda"]
    assert result["fixing_prs"] == [456]
    assert result["state_reason"] == "COMPLETED"


def make_pr(number, repo, merged_at="2026-10-04T10:00:00Z"):
    return {
        "number": number,
        "mergedAt": merged_at,
        "repository": {"nameWithOwner": repo},
    }


def test_parse_issue_keeps_only_merged_prs_from_same_repo():
    fixture_path = Path(__file__).parent / "fixtures" / "issue.json"
    with open(fixture_path, encoding="utf-8") as file:
        issue = json.load(file)
    issue["closedByPullRequestsReferences"]["nodes"] = [
        make_pr(1, "vllm-project/vllm"),
        make_pr(2, "other/repo"),  # merged, but in another repo
        make_pr(3, "VLLM-Project/VLLM"),  # same repo, different case
        make_pr(4, "vllm-project/vllm", merged_at=None),  # not merged
    ]

    result = parse_issue(issue, "vllm-project/vllm")

    assert result["fixing_prs"] == [1, 3]


def test_truncated_fields_none_when_complete():
    issue = {
        "labels": {"totalCount": 2, "nodes": [{"name": "a"}, {"name": "b"}]},
        "closedByPullRequestsReferences": {"totalCount": 0, "nodes": []},
    }

    assert truncated_fields(issue) == []


def test_truncated_fields_reports_cut_off_connections():
    issue = {
        "labels": {"totalCount": 25, "nodes": [{"name": "a"}] * 20},
        "closedByPullRequestsReferences": {"totalCount": 12, "nodes": [{}] * 10},
    }

    assert truncated_fields(issue) == ["labels", "closedByPullRequestsReferences"]
