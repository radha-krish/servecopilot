from pathlib import Path

import pytest

from servecopilot.ingest.fetch_sync import Settings, parse_args


def test_settings_from_env_reads_token(monkeypatch):
    monkeypatch.setenv("GIT_API_KEY", "test-token")

    settings = Settings.from_env()

    assert settings.token == "test-token"
    assert settings.owner == "vllm-project"
    assert settings.repo == "vllm"
    assert settings.limit == 500
    assert settings.output_path == Path("data/raw/issues.jsonl")


def test_settings_from_env_fails_without_token(monkeypatch):
    monkeypatch.delenv("GIT_API_KEY", raising=False)

    with pytest.raises(SystemExit):
        Settings.from_env()


def test_settings_is_immutable():
    settings = Settings(token="t")

    with pytest.raises(AttributeError):
        settings.limit = 10


def test_parse_args_defaults_match_settings():
    args = parse_args([])

    assert args.owner == Settings.owner
    assert args.repo == Settings.repo
    assert args.limit == Settings.limit
    assert args.output_path == Settings.output_path


def test_parse_args_overrides():
    args = parse_args(
        ["--owner", "o", "--repo", "r", "--limit", "100", "--out", "x.jsonl"]
    )

    assert args.owner == "o"
    assert args.repo == "r"
    assert args.limit == 100
    assert args.output_path == Path("x.jsonl")


@pytest.mark.parametrize("bad", ["0", "-5", "abc"])
def test_parse_args_rejects_bad_limit(bad):
    with pytest.raises(SystemExit):
        parse_args(["--limit", bad])


def test_from_env_applies_cli_overrides(monkeypatch):
    monkeypatch.setenv("GIT_API_KEY", "test-token")

    settings = Settings.from_env(**vars(parse_args(["--limit", "100"])))

    assert settings.token == "test-token"
    assert settings.limit == 100
