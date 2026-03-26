"""
Tests for enforce_rate_limit() sliding-window rate limiter.
"""
import time
from unittest.mock import patch

import app


class TestEnforceRateLimit:

    def test_no_sleep_when_under_limit(self):
        """Does not sleep when fewer than 100 requests have been made."""
        with patch("app.time.sleep") as mock_sleep:
            for _ in range(50):
                app.enforce_rate_limit()
            mock_sleep.assert_not_called()

    def test_no_sleep_when_window_has_expired(self):
        """Does not sleep when 100 requests were made more than 60s ago."""
        old_timestamp = time.time() - 61  # outside the window
        for _ in range(100):
            app._rate_limiter.append(old_timestamp)

        with patch("app.time.sleep") as mock_sleep:
            app.enforce_rate_limit()
            mock_sleep.assert_not_called()

    def test_sleeps_when_window_is_full_and_recent(self):
        """Sleeps when 100 requests happened within the last 60s."""
        recent_timestamp = time.time() - 10  # 10s ago, still inside the window
        for _ in range(100):
            app._rate_limiter.append(recent_timestamp)

        with patch("app.time.sleep") as mock_sleep:
            app.enforce_rate_limit()
            mock_sleep.assert_called_once()
            sleep_arg = mock_sleep.call_args[0][0]
            # Should sleep for ~50s (60 - 10 + 0.05 buffer)
            assert 49 < sleep_arg < 52

    def test_appends_timestamp_after_call(self):
        """Each call appends a timestamp to the deque."""
        assert len(app._rate_limiter) == 0
        app.enforce_rate_limit()
        assert len(app._rate_limiter) == 1

    def test_deque_maxlen_enforced(self):
        """Deque never exceeds 100 entries."""
        for _ in range(150):
            app._rate_limiter.append(time.time() - 61)  # old timestamps, no sleep

        app.enforce_rate_limit()
        assert len(app._rate_limiter) == 100

    def test_sleeps_correct_duration(self):
        """Sleep duration = window_remaining + 0.05 buffer."""
        elapsed = 30  # 30s into the window
        timestamp = time.time() - elapsed
        for _ in range(100):
            app._rate_limiter.append(timestamp)

        with patch("app.time.sleep") as mock_sleep:
            with patch("app.time.time", return_value=timestamp + elapsed):
                app.enforce_rate_limit()
            sleep_arg = mock_sleep.call_args[0][0]
            expected = app.RATE_LIMIT_WINDOW - elapsed + 0.05
            assert abs(sleep_arg - expected) < 1.0
