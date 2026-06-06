#!/usr/bin/env python3
"""
Compare regime scenarios for Narrative Rotation Index.

Shows how the same narrative scores differently across RISK_ON, TRANSITION, and RISK_OFF regimes.
Demonstrates regime-aware conviction caps and position sizing.
"""

import json
import math
import random
from datetime import datetime

# Mock data for demonstration
def simulate_narrative_scores(narrative):
    """Generate consistent mock scores for a narrative across regimes."""
    base_scores = {
        "Meme": {"momentum": 70, "liquidity": 85, "attention": 55, "fundamental": 60, "risk": 70},
        "AI Tokens": {"momentum": 65, "liquidity": 60, "attention": 20, "fundamental": 75, "risk": 85},
        "RWA": {"momentum": 70, "liquidity": 40, "attention": 15, "fundamental": 60, "risk": 100},
        "DePIN": {"momentum": 70, "liquidity": 40, "attention": 0, "fundamental": 60, "risk": 100},
        "Privacy": {"momentum": 80, "liquidity": 30, "attention": 0, "fundamental": 60, "risk": 100},
    }
    return base_scores.get(narrative, base_scores["Meme"])

def calculate_conviction(scores, regime):
    """Calculate conviction score with regime-specific caps."""
    # Weighted sum
    total = (
        scores["momentum"] * 0.30 +
        scores["liquidity"] * 0.25 +
        scores["attention"] * 0.20 +
        scores["fundamental"] * 0.15 +
        scores["risk"] * 0.10
    )
    
    # Apply regime caps
    if regime == "RISK_ON":
        cap = 100
        position_multiplier = 1.0
    elif regime == "TRANSITION":
        cap = 75
        position_multiplier = 0.6
    else:  # RISK_OFF
        cap = 50
        position_multiplier = 0.3
    
    conviction = min(total, cap)
    
    # Determine verdict
    if conviction >= 60:
        verdict = "STRONG_LONG"
    elif conviction >= 40:
        verdict = "LONG"
    elif conviction >= 20:
        verdict = "NEUTRAL"
    else:
        verdict = "AVOID"
    
    return {
        "conviction": round(conviction),
        "cap": cap,
        "verdict": verdict,
        "position_multiplier": position_multiplier,
        "position_size_pct": round(5.0 * position_multiplier, 1)
    }

def main():
    print("=" * 80)
    print("NARRATIVE ROTATION INDEX - REGIME SCENARIO COMPARISON")
    print("=" * 80)
    print("\nShows how the same narrative scores differently across market regimes.")
    print("Regime detection → conviction cap → position sizing → execution signal.")
    print("\n")
    
    # Test with Meme narrative (strongest in our mock data)
    narrative = "Meme"
    scores = simulate_narrative_scores(narrative)
    
    print(f"Narrative: {narrative}")
    print(f"Base Scores: Momentum={scores['momentum']}, Liquidity={scores['liquidity']}, ")
    print(f"             Attention={scores['attention']}, Fundamental={scores['fundamental']}, Risk={scores['risk']}")
    print("\n")
    
    # Table header
    print(f"{'Regime':<15} {'Conviction':<12} {'Cap':<8} {'Verdict':<15} {'Position':<12} {'Signal'}")
    print("-" * 80)
    
    # Compare all three regimes
    for regime in ["RISK_ON", "TRANSITION", "RISK_OFF"]:
        result = calculate_conviction(scores, regime)
        
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
              f"{result['verdict']:<15} {result['position_size_pct']}%{'':<6} {signal}")
    
    print("\n" + "=" * 80)
    print("KEY INSIGHTS:")
    print("=" * 80)
    print("\n1. REGIME CAPS CONVICTION")
    print("   - RISK_ON:    100 cap → STRONG_LONG (62/100)")
    print("   - TRANSITION:  75 cap → STRONG_LONG (62/75)")
    print("   - RISK_OFF:    50 cap → LONG (50/50) - STRONG_LONG impossible")
    
    print("\n2. POSITION SIZING ADJUSTS")
    print("   - RISK_ON:    5.0% base × 1.0 = 5.0% allocation")
    print("   - TRANSITION: 5.0% base × 0.6 = 3.0% allocation")
    print("   - RISK_OFF:   5.0% base × 0.3 = 1.5% allocation")
    
    print("\n3. EXECUTION SIGNAL CHANGES")
    print("   - RISK_ON:    ✅ CONCENTRATE (full allocation)")
    print("   - TRANSITION: ✅ CONCENTRATE (reduced allocation)")
    print("   - RISK_OFF:   📈 MODERATE (minimal allocation)")
    
    print("\n4. PRACTICAL IMPLICATIONS")
    print("   • Same narrative, same metrics → different conviction based on regime")
    print("   • RISK_OFF prevents overconfidence (STRONG_LONG impossible)")
    print("   • Position sizing protects capital in uncertain regimes")
    print("   • Markov chain (70% persistence) prevents regime whipsaw")
    
    print("\n" + "=" * 80)
    print("SCORING MODEL (5-BUCKET WEIGHTED)")
    print("=" * 80)
    print("Momentum:      30%  (price action, RSI, relative strength)")
    print("Liquidity:     25%  (volume growth, market cap expansion)")
    print("Attention:     20%  (social velocity, CMC trending, Kaito CT)")
    print("Fundamental:   15%  (narrative-specific utility metrics)")
    print("Risk Adj:      10%  (volatility penalty + exhaustion detector)")
    print("\nTotal = Σ(bucket_score × weight)")
    print(f"Meme example: {scores['momentum']}×0.30 + {scores['liquidity']}×0.25 + "
          f"{scores['attention']}×0.20 + {scores['fundamental']}×0.15 + {scores['risk']}×0.10 = {sum([scores['momentum']*0.30, scores['liquidity']*0.25, scores['attention']*0.20, scores['fundamental']*0.15, scores['risk']*0.10]):.1f}")
    
    print("\n" + "=" * 80)
    print("USE CASE: AGENT DECISION FLOW")
    print("=" * 80)
    print("1. Detect regime (Fear & Greed + BTC dominance + mcap momentum)")
    print("2. Score all 5 narratives (Meme, AI, RWA, DePIN, Privacy)")
    print("3. Apply regime cap to each conviction score")
    print("4. Apply quadratic weighting: w_i = conv_i² / Σ(conv_j²)")
    print("5. Check execution guardrails (liquidity, slippage, token age)")
    print("6. Output structured JSON with reasons + risks + TWAK payload")
    
    print("\n" + "=" * 80)
    print("DEMO OUTPUT (TRANSITION regime)")
    print("=" * 80)
    
    # Show full structured output for TRANSITION regime
    transition_result = calculate_conviction(scores, "TRANSITION")
    
    demo_output = {
        "skill": "narrative-rotation-index",
        "version": "8.0",
        "regime": "TRANSITION",
        "top_narrative": narrative,
        "verdict": transition_result["verdict"],
        "conviction": transition_result["conviction"],
        "cap": transition_result["cap"],
        "position_size": f"{transition_result['position_size_pct']}%",
        "rotation_signal": f"CONCENTRATE_{narrative.upper().replace(' ', '_')} (conviction {transition_result['conviction']}/{transition_result['cap']})",
        "exhaustion": "25/100",
        "bucket_scores": scores,
        "reasons": [
            "Strong relative strength vs BTC (1.215x)",
            "Healthy 7d return (+21.5%)",
            "RSI approaching oversold (38.5)",
            "Volume expanding rapidly (85% WoW)",
            "Market cap expanding (19% WoW)",
            "Deep liquidity ($85M)"
        ],
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