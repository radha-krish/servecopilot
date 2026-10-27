import json
from pathlib import Path

from servecopilot.ingest.fetch_sync import parse_issue


def test_parse_issue():
    fixture_path = Path(__file__).parent / "fixtures" / "issue.json"

    with open(fixture_path, encoding="utf-8") as file:
        issue = json.load(file)

    result = parse_issue(issue)

    assert result["number"] == 123
    assert result["title"] == "Example GPU issue"
    assert result["labels"] == ["bug", "cuda"]
    assert result["fixing_prs"] == [456]
