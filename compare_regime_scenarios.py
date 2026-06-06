#!/usr/bin/env python3
"""
Compare regime scenarios for Narrative Rotation Index.

Shows how the same narrative scores differently across RISK_ON, TRANSITION, and RISK_OFF regimes.
Demonstrates regime-aware conviction caps and position sizing.

Uses the actual scoring pipeline from backtest.py for consistency.
"""

import json
import sys
import os

# Import actual scoring pipeline from backtest.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backtest import (
    compute_narrative_score,
    detect_market_regime,
    CACHED_NARRATIVE_DATA,
    REGIME_CONVICTION_CAP,
)


def main():
    print("=" * 80)
    print("NARRATIVE ROTATION INDEX - REGIME SCENARIO COMPARISON")
    print("=" * 80)
    print("\nShows how the same narrative scores differently across market regimes.")
    print("Regime detection → conviction cap → position sizing → execution signal.")
    print("Uses actual scoring pipeline from backtest.py (5-bucket weighted).\n")

    # Test with Meme narrative (strongest in our mock data)
    narrative = "Meme"
    data = CACHED_NARRATIVE_DATA[narrative]

    # Table header
    print(f"{'Regime':<15} {'Conviction':<12} {'Cap':<8} {'Verdict':<15} {'Position':<12} {'Signal'}")
    print("-" * 80)

    # Compare all three regimes
    position_multipliers = {"RISK_ON": 1.0, "TRANSITION": 0.6, "RISK_OFF": 0.3}
    results = {}

    for regime in ["RISK_ON", "TRANSITION", "RISK_OFF"]:
        result = compute_narrative_score(narrative, data, regime)
        results[regime] = result

        pos_mult = position_multipliers[regime]
        pos_size = round(5.0 * pos_mult, 1)

        # Determine signal strength
        if result["verdict"] == "STRONG_LONG":
            signal = "✅ CONCENTRATE"
        elif result["verdict"] == "LONG":
            signal = "📈 MODERATE"
        elif result["verdict"] == "NEUTRAL":
            signal = "⚖️  NEUTRAL"
        else:
            signal = "⛔ AVOID"

        print(f"{regime:<15} {result['conviction']:<12} {result['cap']:<8} "
              f"{result['verdict']:<15} {pos_size}%{'':<6} {signal}")

    # Show bucket breakdown
    print("\n" + "=" * 80)
    print("BUCKET SCORE BREAKDOWN (same data, different regimes)")
    print("=" * 80)

    ref = results["TRANSITION"]
    buckets = ref["bucket_scores"]
    print(f"\nMomentum:     {buckets['momentum']:<4} × 0.30 = {buckets['momentum'] * 0.30:.1f}")
    print(f"Liquidity:    {buckets['liquidity']:<4} × 0.25 = {buckets['liquidity'] * 0.25:.1f}")
    print(f"Attention:    {buckets['attention']:<4} × 0.20 = {buckets['attention'] * 0.20:.1f}")
    print(f"Fundamental:  {buckets['fundamental']:<4} × 0.15 = {buckets['fundamental'] * 0.15:.1f}")
    print(f"Risk Adj:     {buckets['risk_adjustment']:<4} × 0.10 = {buckets['risk_adjustment'] * 0.10:.1f}")
    raw = sum(buckets[k] * w for k, w in [
        ("momentum", 0.30), ("liquidity", 0.25), ("attention", 0.20),
        ("fundamental", 0.15), ("risk_adjustment", 0.10)
    ])
    print(f"{'─' * 35}")
    print(f"Weighted raw: {raw:.1f}")
    print(f"After regime multiplier + cap → see table above")

    print("\n" + "=" * 80)
    print("KEY INSIGHTS:")
    print("=" * 80)
    ro, tr, off = results["RISK_ON"], results["TRANSITION"], results["RISK_OFF"]
    print(f"\n1. REGIME CAPS CONVICTION")
    print(f"   - RISK_ON:    {ro['cap']} cap → {ro['verdict']} ({ro['conviction']}/{ro['cap']})")
    print(f"   - TRANSITION: {tr['cap']} cap → {tr['verdict']} ({tr['conviction']}/{tr['cap']})")
    print(f"   - RISK_OFF:   {off['cap']} cap → {off['verdict']} ({off['conviction']}/{off['cap']})")

    print(f"\n2. POSITION SIZING ADJUSTS")
    print(f"   - RISK_ON:    5.0% base × 1.0 = 5.0% allocation")
    print(f"   - TRANSITION: 5.0% base × 0.6 = 3.0% allocation")
    print(f"   - RISK_OFF:   5.0% base × 0.3 = 1.5% allocation")

    print(f"\n3. REGIME MULTIPLIERS (applied before cap)")
    print(f"   - RISK_ON:    × 1.1 (bonus)")
    print(f"   - TRANSITION: × 0.9 (penalty)")
    print(f"   - RISK_OFF:   × 0.7 (penalty) + Meme-specific × 0.6")

    print(f"\n4. PRACTICAL IMPLICATIONS")
    print(f"   • Same narrative, same metrics → different conviction based on regime")
    print(f"   • RISK_OFF prevents overconfidence (STRONG_LONG impossible at cap {off['cap']})")
    print(f"   • Position sizing protects capital in uncertain regimes")
    print(f"   • Markov chain (70% persistence) prevents regime whipsaw")

    print(f"\n5. EXHAUSTION SCORE: {ref['exhaustion_score']}/100")
    exh = ref['exhaustion_score']
    if exh <= 30:
        print(f"   → Healthy trend — full conviction allowed")
    elif exh <= 60:
        print(f"   → Caution — sizing reduced")
    else:
        print(f"   → Crowded/late-cycle — strong penalty")

    print("\n" + "=" * 80)
    print("SCORING MODEL (5-BUCKET WEIGHTED)")
    print("=" * 80)
    print("Momentum:      30%  (price action, RSI, relative strength)")
    print("Liquidity:     25%  (volume growth, market cap expansion)")
    print("Attention:     20%  (social velocity, CMC trending, Kaito CT)")
    print("Fundamental:   15%  (narrative-specific utility metrics)")
    print("Risk Adj:      10%  (volatility penalty + exhaustion detector)")
    print(f"\nTotal = Σ(bucket_score × weight) × regime_mult → capped at regime limit")

    print("\n" + "=" * 80)
    print("DEMO OUTPUT (TRANSITION regime)")
    print("=" * 80)

    demo_output = {
        "skill": "narrative-rotation-index",
        "version": "8.1",
        "regime": "TRANSITION",
        "top_narrative": narrative,
        "verdict": tr["verdict"],
        "conviction": tr["conviction"],
        "cap": tr["cap"],
        "position_size": "3.0%",
        "rotation_signal": f"CONCENTRATE_{narrative.upper().replace(' ', '_')} (conviction {tr['conviction']}/{tr['cap']})",
        "exhaustion": f"{tr['exhaustion_score']}/100",
        "bucket_scores": tr["bucket_scores"],
        "reasons": tr["reasons"][:6],
        "risks": [
            "Regime is TRANSITION — not full risk-on, allocation reduced",
            "If volume drops below 20d average, signal downgrades to LONG"
        ],
        "execution_guardrails": {
            "execution_allowed": True,
            "violations": [],
            "limits": {
                "max_slippage_large_cap_pct": 1.0,
                "max_slippage_meme_pct": 2.5,
                "max_allocation_per_narrative_pct": 35.0,
                "max_allocation_per_token_pct": 15.0,
                "min_liquidity_usd": 500000,
                "max_spread_pct": 1.5,
                "min_token_age_days": 7,
                "requires_user_confirmation": True
            }
        }
    }

    print(json.dumps(demo_output, indent=2))


if __name__ == "__main__":
    main()
