import unittest

from app.rate_limit import HourlyRateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit(self) -> None:
        limiter = HourlyRateLimiter(limit=2, window_seconds=10)
        self.assertTrue(limiter.allow(7, now=1))
        self.assertTrue(limiter.allow(7, now=2))
        self.assertFalse(limiter.allow(7, now=3))

    def test_expires_old_events(self) -> None:
        limiter = HourlyRateLimiter(limit=1, window_seconds=10)
        self.assertTrue(limiter.allow(7, now=1))
        self.assertTrue(limiter.allow(7, now=12))

    def test_refund_does_not_count_a_failed_attempt(self) -> None:
        limiter = HourlyRateLimiter(limit=1, window_seconds=10)
        self.assertTrue(limiter.allow(7, now=1))
        limiter.refund_last(7)
        self.assertTrue(limiter.allow(7, now=2))


if __name__ == "__main__":
    unittest.main()
