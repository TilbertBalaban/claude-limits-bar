import unittest
from datetime import datetime, timedelta, timezone

from claude_limits_bar.limits import (
    CredentialsNotFound, Limit,
    bar_title, limit_line, local_reset_time, parse_access_token,
    parse_limits, primary_limit, reset_label, time_until,
)

NOW = datetime(2026, 9, 2, 12, 30, tzinfo=timezone.utc)

SAMPLE_RESPONSE = {
    "limits": [
        {"kind": "session", "group": "session", "percent": 41, "severity": "normal",
         "resets_at": "2026-09-02T15:10:00.026681+00:00", "scope": None, "is_active": True},
        {"kind": "weekly_all", "group": "weekly", "percent": 9, "severity": "normal",
         "resets_at": "2026-09-04T22:00:00.026699+00:00", "scope": None, "is_active": False},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 13, "severity": "normal",
         "resets_at": "2026-09-04T22:00:00.026844+00:00",
         "scope": {"model": {"id": None, "display_name": "Fable"}, "surface": None},
         "is_active": False},
    ],
}


def make_limit(kind="session", label="5-Hour Limit", percent=41.0, severity="normal",
               resets_at=NOW + timedelta(hours=2, minutes=40), is_active=True):
    return Limit(kind=kind, label=label, percent=percent, severity=severity,
                 resets_at=resets_at, is_active=is_active)


class TestParseAccessToken(unittest.TestCase):
    def test_valid(self):
        raw = '{"claudeAiOauth": {"accessToken": "sk-ant-oat01-abc"}}'
        self.assertEqual(parse_access_token(raw), "sk-ant-oat01-abc")

    def test_missing_token(self):
        with self.assertRaises(CredentialsNotFound):
            parse_access_token('{"claudeAiOauth": {}}')

    def test_invalid_json(self):
        with self.assertRaises(CredentialsNotFound):
            parse_access_token("not json")


class TestParseLimits(unittest.TestCase):
    def test_sample_response(self):
        limits = parse_limits(SAMPLE_RESPONSE)
        self.assertEqual(len(limits), 3)
        session, weekly, scoped = limits
        self.assertEqual(session.label, "5-Hour Limit")
        self.assertEqual(session.percent, 41)
        self.assertTrue(session.is_active)
        self.assertEqual(session.resets_at.tzinfo.utcoffset(None), timedelta(0))
        self.assertEqual(weekly.label, "7-Day Limit")
        self.assertEqual(scoped.label, "7-Day (Fable)")

    def test_empty_and_missing(self):
        self.assertEqual(parse_limits({}), [])
        self.assertEqual(parse_limits({"limits": None}), [])

    def test_unknown_kind_gets_readable_label(self):
        limits = parse_limits({"limits": [{"kind": "weekly_opus", "percent": 5}]})
        self.assertEqual(limits[0].label, "Weekly opus")
        self.assertIsNone(limits[0].resets_at)


class TestPrimaryLimit(unittest.TestCase):
    def test_prefers_session(self):
        session = make_limit(percent=20)
        weekly = make_limit(kind="weekly_all", label="7-Day Limit", percent=50)
        self.assertIs(primary_limit([weekly, session]), session)

    def test_worse_limit_wins_when_warning(self):
        session = make_limit(percent=20)
        weekly = make_limit(kind="weekly_all", label="7-Day Limit", percent=85)
        self.assertIs(primary_limit([session, weekly]), weekly)

    def test_no_limits(self):
        self.assertIsNone(primary_limit([]))


class TestTimeFormatting(unittest.TestCase):
    def test_time_until(self):
        self.assertEqual(time_until(NOW + timedelta(hours=2, minutes=40), NOW), "2h 40m")
        self.assertEqual(time_until(NOW + timedelta(minutes=5), NOW), "5m")
        self.assertEqual(time_until(NOW + timedelta(days=2, hours=9, minutes=30), NOW), "2d 9h")
        self.assertEqual(time_until(NOW - timedelta(minutes=1), NOW), "now")
        self.assertEqual(time_until(None, NOW), "?")

    def test_local_reset_time_same_day_has_no_weekday(self):
        self.assertNotIn(" ", local_reset_time(NOW + timedelta(hours=1), NOW))
        self.assertIn(" ", local_reset_time(NOW + timedelta(days=2), NOW))

    def test_reset_label(self):
        same_day = NOW.astimezone().replace(hour=18, minute=10)
        self.assertEqual(reset_label(same_day, NOW), "Today 6:10 PM")
        other_day = datetime(2026, 9, 5, 1, 0, tzinfo=NOW.astimezone().tzinfo)
        label = reset_label(other_day, NOW)
        self.assertEqual(label, "Sep 5 1:00 AM")
        self.assertEqual(reset_label(None, NOW), "?")


class TestBarTitle(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(bar_title([make_limit()], NOW), "✳ 41% · 2h 40m")

    def test_warning(self):
        self.assertEqual(bar_title([make_limit(percent=85)], NOW), "✳ ⚠️ 85% · 2h 40m")

    def test_exhausted_shows_time_to_reset(self):
        self.assertEqual(bar_title([make_limit(percent=100)], NOW), "✳ ⛔ 2h 40m")

    def test_no_data(self):
        self.assertEqual(bar_title([], NOW), "✳ ?")


class TestLimitLine(unittest.TestCase):
    def test_contains_label_percent_and_countdown(self):
        line = limit_line(make_limit(), NOW)
        self.assertIn("5-Hour Limit: 41%", line)
        self.assertIn("in 2h 40m", line)


class TestCache(unittest.TestCase):
    def test_roundtrip_and_expiry(self):
        import tempfile
        from pathlib import Path
        from claude_limits_bar.limits import load_cache, save_cache
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "usage.json"
            self.assertIsNone(load_cache(path))
            save_cache(SAMPLE_RESPONSE, path)
            self.assertEqual(load_cache(path), SAMPLE_RESPONSE)
            self.assertIsNone(load_cache(path, max_age=-1))
            path.write_text("garbage")
            self.assertIsNone(load_cache(path))


if __name__ == "__main__":
    unittest.main()
