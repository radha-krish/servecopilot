import json

import pytest

from servecopilot.ingest.fetch_sync import atomic_write, write_jsonl_lines


def test_atomic_write_writes_one_line_per_issue(tmp_path):
    output_path = tmp_path / "issues.jsonl"

    with atomic_write(output_path) as file:
        write_jsonl_lines(file, [{"number": 1}, {"number": 2}])

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"number": 1}, {"number": 2}]
    assert not (tmp_path / "issues.jsonl.tmp").exists()


def test_atomic_write_failure_keeps_old_file(tmp_path):
    output_path = tmp_path / "issues.jsonl"
    output_path.write_text('{"number": 1}\n', encoding="utf-8")

    # object() is not JSON-serializable, so the write fails halfway through.
    with pytest.raises(TypeError), atomic_write(output_path) as file:
        write_jsonl_lines(file, [{"number": 2}, {"bad": object()}])

    assert output_path.read_text(encoding="utf-8") == '{"number": 1}\n'
    assert not (tmp_path / "issues.jsonl.tmp").exists()
