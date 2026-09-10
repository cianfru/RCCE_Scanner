import unittest

import ratelimit
from ratelimit import SlidingWindowLimiter


class RateLimitTests(unittest.TestCase):
    def test_allows_up_to_max_then_blocks(self):
        lim = SlidingWindowLimiter(max_requests=3, window_seconds=60)
        allowed = [lim.check("ip")[0] for _ in range(5)]
        self.assertEqual(allowed, [True, True, True, False, False])

    def test_retry_after_is_positive_when_blocked(self):
        lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(lim.check("ip")[0])
        allowed, retry_after = lim.check("ip")
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_keys_are_isolated(self):
        lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(lim.check("a")[0])
        self.assertFalse(lim.check("a")[0])
        # A different key is unaffected.
        self.assertTrue(lim.check("b")[0])

    def test_window_expiry_frees_budget(self):
        lim = SlidingWindowLimiter(max_requests=1, window_seconds=0.05)
        self.assertTrue(lim.check("ip")[0])
        self.assertFalse(lim.check("ip")[0])
        import time
        time.sleep(0.06)
        self.assertTrue(lim.check("ip")[0])

    def test_key_cap_is_bounded_under_unique_flood(self):
        # Regression for the unbounded-map bug: a flood of fresh identities
        # must not grow the tracked-key map past the cap.
        orig = ratelimit._MAX_KEYS
        ratelimit._MAX_KEYS = 5
        try:
            lim = SlidingWindowLimiter(max_requests=1, window_seconds=60)
            results = [lim.check(f"ip-{i}")[0] for i in range(50)]
            self.assertLessEqual(len(lim._hits), 5)
            # First 5 fresh keys admitted; the rest rejected while saturated.
            self.assertEqual(results[:5], [True] * 5)
            self.assertTrue(all(r is False for r in results[5:]))
        finally:
            ratelimit._MAX_KEYS = orig


if __name__ == "__main__":
    unittest.main()
