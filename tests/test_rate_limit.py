from datetime import UTC, datetime

from servecopilot.ingest.fetch_sync import RATE_LIMIT_FLOOR, seconds_until_reset

NOW = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def test_no_wait_when_enough_points_remain():
    rate_limit = {"remaining": RATE_LIMIT_FLOOR, "resetAt": "2026-01-01T00:30:00Z"}

    assert seconds_until_reset(rate_limit, NOW) == 0.0


def test_waits_until_reset_when_points_are_low():
    rate_limit = {"remaining": 5, "resetAt": "2026-01-01T00:30:00Z"}

    assert seconds_until_reset(rate_limit, NOW) == 30 * 60


def test_no_negative_wait_when_reset_already_passed():
    rate_limit = {"remaining": 5, "resetAt": "2025-12-31T23:59:00Z"}

    assert seconds_until_reset(rate_limit, NOW) == 0.0
