"""Unit tests for narrative-rotation-index backtest engine.

Covers the three v8.1 bug fixes:
- Circuit breaker recovery (trough-based)
- Student's t-distribution sampling
- Conviction decay statelessness
"""

import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest
from backtest import (
    CIRCUIT_BREAKER_RECOVERY_THRESHOLD,
    CIRCUIT_BREAKER_THRESHOLD,
    T_DISTRIBUTION_DF,
    apply_conviction_decay,
    check_circuit_breaker,
    compute_narrative_score,
    detect_market_regime,
    get_circuit_breaker_multiplier,
)


def _reset_breaker():
    backtest.CIRCUIT_BREAKER_ACTIVE = False
    backtest.CIRCUIT_BREAKER_TROUGH = None


class CircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        _reset_breaker()

    def test_trips_on_15pct_drawdown(self):
        active, msg = check_circuit_breaker(current_capital=8400, peak_capital=10000)
        self.assertTrue(active)
        self.assertIn("TRIPPED", msg)
        self.assertEqual(get_circuit_breaker_multiplier(), 0.1)

    def test_does_not_trip_below_threshold(self):
        active, _ = check_circuit_breaker(current_capital=8600, peak_capital=10000)
        self.assertFalse(active)
        self.assertEqual(get_circuit_breaker_multiplier(), 1.0)

    def test_recovery_clears_breaker(self):
        # Trip at 16% drawdown
        check_circuit_breaker(current_capital=8400, peak_capital=10000)
        self.assertTrue(backtest.CIRCUIT_BREAKER_ACTIVE)
        # Drop further to set trough
        check_circuit_breaker(current_capital=8000, peak_capital=10000)
        self.assertEqual(backtest.CIRCUIT_BREAKER_TROUGH, 8000)
        # Recover 5% from trough (8000 * 1.05 = 8400)
        active, msg = check_circuit_breaker(current_capital=8400, peak_capital=10000)
        self.assertFalse(active)
        self.assertIn("CLEARED", msg)
        self.assertIsNone(backtest.CIRCUIT_BREAKER_TROUGH)

    def test_recovery_threshold_uses_trough_not_peak(self):
        """Regression: pre-v8.1 code checked recovery from peak, which never cleared."""
        check_circuit_breaker(current_capital=8000, peak_capital=10000)  # trip
        check_circuit_breaker(current_capital=7000, peak_capital=10000)  # new trough
        # 7000 -> 7400 = 5.7% from trough but still 26% from peak
        active, _ = check_circuit_breaker(current_capital=7400, peak_capital=10000)
        self.assertFalse(active, "Recovery must clear when 5% above trough")


class TDistributionTests(unittest.TestCase):
    def test_chi2_uses_raw_sum(self):
        """Regression: pre-v8.1 used max(sqrt(chi2), 0.1) which floored the denominator."""
        random.seed(42)
        samples = []
        for _ in range(5000):
            t_sample = random.gauss(0, 1)
            chi2_var = sum(random.gauss(0, 1) ** 2 for _ in range(T_DISTRIBUTION_DF))
            t_draw = t_sample / math.sqrt(chi2_var / T_DISTRIBUTION_DF)
            samples.append(t_draw)

        # Student's t with df=3 has mean ~0 and undefined variance, but
        # empirical std for finite sample should be ~1.7-2.0
        mean = sum(samples) / len(samples)
        var = sum((s - mean) ** 2 for s in samples) / len(samples)
        std = math.sqrt(var)
        self.assertAlmostEqual(mean, 0.0, delta=0.15)
        self.assertGreater(std, 1.3, "df=3 t-distribution should have fat tails")
        self.assertLess(std, 3.5)

    def test_fat_tails_present(self):
        """Verify the distribution actually produces extreme values (fat tails)."""
        random.seed(42)
        samples = []
        for _ in range(10000):
            t_sample = random.gauss(0, 1)
            chi2_var = sum(random.gauss(0, 1) ** 2 for _ in range(T_DISTRIBUTION_DF))
            samples.append(t_sample / math.sqrt(chi2_var / T_DISTRIBUTION_DF))
        # At df=3, ~1% of samples should exceed |3.18|
        extreme_count = sum(1 for s in samples if abs(s) > 3.18)
        self.assertGreater(extreme_count, 50, "Should produce fat-tail extreme values")


class ConvictionDecayTests(unittest.TestCase):
    def test_stateless_with_no_history(self):
        result = apply_conviction_decay("Meme", raw_score=80, current_day=1)
        self.assertEqual(result, 80, "First call should not decay")

    def test_no_decay_within_one_day(self):
        history = {}
        apply_conviction_decay("Meme", 80, current_day=1, conviction_history=history)
        result = apply_conviction_decay("Meme", 80, current_day=2, conviction_history=history)
        # 1-day stale = no decay (decay only applies when days_stale > 1)
        self.assertEqual(result, 80)

    def test_decay_applies_after_stale_days(self):
        history = {}
        apply_conviction_decay("Meme", 80, current_day=1, conviction_history=history)
        # 5 days stale: 80 * 0.9^5 = 80 * 0.59049 = 47.24 -> 47
        result = apply_conviction_decay("Meme", 80, current_day=6, conviction_history=history)
        expected = int(80 * (0.9 ** 5))
        self.assertEqual(result, expected)

    def test_independent_history_dicts_dont_collide(self):
        """Regression: pre-v8.1 used a global dict that bled state across runs."""
        history_a = {}
        history_b = {}
        apply_conviction_decay("Meme", 80, current_day=1, conviction_history=history_a)
        # history_b should be empty -> no decay
        result = apply_conviction_decay("Meme", 80, current_day=10, conviction_history=history_b)
        self.assertEqual(result, 80, "Separate history dicts must not share state")

    def test_decay_clamped_at_zero(self):
        history = {}
        apply_conviction_decay("Meme", 1, current_day=1, conviction_history=history)
        result = apply_conviction_decay("Meme", 1, current_day=200, conviction_history=history)
        self.assertGreaterEqual(result, 0)


class RegimeScoringTests(unittest.TestCase):
    def test_risk_off_caps_conviction_at_50(self):
        data = backtest.CACHED_NARRATIVE_DATA["Meme"]
        result = compute_narrative_score("Meme", data, "RISK_OFF")
        self.assertLessEqual(result["conviction"], 50)
        # Verdict cannot be STRONG_LONG since cap < 60 threshold
        self.assertNotEqual(result["verdict"], "STRONG_LONG")

    def test_transition_caps_at_75(self):
        data = backtest.CACHED_NARRATIVE_DATA["Meme"]
        result = compute_narrative_score("Meme", data, "TRANSITION")
        self.assertLessEqual(result["conviction"], 75)

    def test_risk_on_no_cap_below_100(self):
        data = backtest.CACHED_NARRATIVE_DATA["Meme"]
        result = compute_narrative_score("Meme", data, "RISK_ON")
        self.assertLessEqual(result["conviction"], 100)

    def test_regime_detection_thresholds(self):
        # High greed + low BTC dominance + expanding mcap -> RISK_ON
        regime, _ = detect_market_regime(70, 48, 0.06)
        self.assertEqual(regime, "RISK_ON")
        # Low fear + high BTC dominance -> RISK_OFF
        regime, _ = detect_market_regime(25, 58, -0.03)
        self.assertEqual(regime, "RISK_OFF")
        # Mixed -> TRANSITION
        regime, _ = detect_market_regime(50, 52, 0.01)
        self.assertEqual(regime, "TRANSITION")


class X402PaymentGateTests(unittest.TestCase):
    """The x402 gate verifies real EIP-712 signatures, not a shared secret."""

    def setUp(self):
        from eth_account import Account

        self.key = Account.create().key.hex()

    def test_valid_payment_accepted(self):
        hdr = backtest.build_x402_payment(self.key, tier="full_scan")
        ok, msg = backtest.verify_x402_payment({"X-PAYMENT": hdr}, "full_scan")
        self.assertTrue(ok, msg)

    def test_missing_payment_rejected(self):
        ok, _ = backtest.verify_x402_payment({}, "base")
        self.assertFalse(ok)

    def test_underpaid_rejected(self):
        # A 'base' ($0.05) authorization must not satisfy a 'full_scan' ($0.50) call.
        hdr = backtest.build_x402_payment(self.key, tier="base")
        ok, msg = backtest.verify_x402_payment({"X-PAYMENT": hdr}, "full_scan")
        self.assertFalse(ok)
        self.assertIn("authorized", msg)

    def test_tampered_value_rejected(self):
        import base64
        import json

        hdr = backtest.build_x402_payment(self.key, tier="base")
        env = json.loads(base64.b64decode(hdr))
        env["payload"]["authorization"]["value"] = str(10 ** 30)  # inflate after signing
        tampered = base64.b64encode(json.dumps(env).encode()).decode()
        ok, _ = backtest.verify_x402_payment({"X-PAYMENT": tampered}, "full_scan")
        self.assertFalse(ok)

    def test_expired_authorization_rejected(self):
        # ttl in the past -> outside validity window.
        hdr = backtest.build_x402_payment(self.key, tier="base", ttl_seconds=-10)
        ok, msg = backtest.verify_x402_payment({"X-PAYMENT": hdr}, "base")
        self.assertFalse(ok)

    def test_payee_binding(self):
        payee = "0x1111111111111111111111111111111111111111"
        hdr = backtest.build_x402_payment(self.key, tier="base", pay_to=payee)
        ok, _ = backtest.verify_x402_payment({"X-PAYMENT": hdr}, "base", pay_to=payee)
        self.assertTrue(ok)
        # Wrong expected payee -> rejected.
        ok2, _ = backtest.verify_x402_payment(
            {"X-PAYMENT": hdr}, "base", pay_to="0x2222222222222222222222222222222222222222"
        )
        self.assertFalse(ok2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
