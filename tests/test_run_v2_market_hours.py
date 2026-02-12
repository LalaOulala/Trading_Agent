from __future__ import annotations

import unittest
from datetime import datetime, timezone

from run_v2 import _coerce_utc, _format_duration, _market_closed_message


class RunV2MarketHoursTests(unittest.TestCase):
    def test_format_duration(self) -> None:
        self.assertEqual(_format_duration(0), "0s")
        self.assertEqual(_format_duration(59), "59s")
        self.assertEqual(_format_duration(61), "1m 1s")
        self.assertEqual(_format_duration(3661), "1h 1m 1s")
        self.assertEqual(_format_duration(90061), "1j 1h 1m 1s")

    def test_coerce_utc_handles_naive_and_aware(self) -> None:
        naive = datetime(2026, 2, 12, 12, 0, 0)
        aware = datetime(2026, 2, 12, 12, 0, 0, tzinfo=timezone.utc)

        naive_utc = _coerce_utc(naive)
        aware_utc = _coerce_utc(aware)

        self.assertIsNotNone(naive_utc.tzinfo)
        self.assertEqual(aware_utc.tzinfo, timezone.utc)

    def test_market_closed_message_contains_remaining_time(self) -> None:
        now = datetime(2026, 2, 12, 12, 0, 0, tzinfo=timezone.utc)
        next_open = datetime(2026, 2, 12, 13, 10, 5, tzinfo=timezone.utc)

        message = _market_closed_message(now, next_open)

        self.assertIn("Le marché est fermé, il réouvre dans", message)
        self.assertIn("1h 10m 5s", message)
        self.assertIn("prochaine ouverture:", message)


if __name__ == "__main__":
    unittest.main()
