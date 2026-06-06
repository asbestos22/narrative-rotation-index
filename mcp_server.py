#!/usr/bin/env python3
"""MCP server for the Narrative Rotation Index skill.

Exposes the core scoring functions as MCP tools so any MCP-aware client
(Claude Desktop, CMC AI Agent Hub, BNBAgent SDK, custom agents) can call
them over the standard protocol.

Tools exposed:
  - run_skill(narrative)            — single-narrative deep dive
  - global_scan(regime)             — cross-narrative rotation engine
  - detect_regime(fear_greed, btc_dom, mcap_chg) — market regime classifier
  - generate_twak_payload(narrative, amount_usd, verdict) — BSC swap payload

Run:
  python mcp_server.py            # stdio transport (for Claude Desktop)
  python mcp_server.py --http     # HTTP transport on :8765
"""

import argparse
import json
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

import backtest
from backtest import (
    AUTO_EXECUTE,
    CACHED_NARRATIVE_DATA,
    EXECUTION_LIMITS,
    NARRATIVE_BASKETS,
    REGIME_CONVICTION_CAP,
    REGIME_SIZING,
    check_execution_guards,
    compute_narrative_score,
    detect_market_regime,
    generate_twak_payload,
    global_scan as _global_scan,
)

mcp = FastMCP("narrative-rotation-index")


@mcp.tool()
def run_skill(narrative: str) -> dict[str, Any]:
    """Single-narrative deep dive with structured confidence output.

    Args:
        narrative: One of "AI Tokens", "RWA", "DePIN", "Meme", "Privacy".

    Returns:
        Verdict, conviction, bucket scores, exhaustion, reasons, risks,
        execution guardrails, and optional TWAK payload.
    """
    if narrative not in CACHED_NARRATIVE_DATA:
        return {
            "error": f"Unknown narrative: {narrative}",
            "available": list(CACHED_NARRATIVE_DATA.keys()),
        }

    data = CACHED_NARRATIVE_DATA[narrative]
    regime, regime_reason = detect_market_regime(58, 51.3, 0.04)
    cap = REGIME_CONVICTION_CAP[regime]

    score = compute_narrative_score(narrative, data, regime)
    allowed, violations = check_execution_guards(narrative, data)

    sizing_pct = 5 * REGIME_SIZING[regime]
    payload = (
        generate_twak_payload(narrative, 500, score["verdict"])
        if score["verdict"] in ["STRONG_LONG", "LONG"] and allowed
        else None
    )

    return {
        "skill": "narrative-rotation-index",
        "version": "8.1",
        "narrative": narrative,
        "regime": regime,
        "regime_reason": regime_reason,
        "verdict": score["verdict"],
        "conviction": score["conviction"],
        "cap": cap,
        "position_size_pct": round(sizing_pct, 1),
        "exhaustion_score": score["exhaustion_score"],
        "bucket_scores": score["bucket_scores"],
        "reasons": score["reasons"][:6],
        "execution_guardrails": {
            "execution_allowed": allowed,
            "violations": violations,
        },
        "twak_payload": payload,
    }


@mcp.tool()
def global_scan(regime: str | None = None) -> dict[str, Any]:
    """Cross-narrative rotation engine.

    Evaluates all 5 narratives, ranks by conviction, applies quadratic
    portfolio weighting, and detects market regime.

    Args:
        regime: Optional regime override ("RISK_ON", "TRANSITION", "RISK_OFF").
                When None, regime is auto-detected from default macro inputs.

    Returns:
        regime, narrative_rankings, portfolio_weights, rotation_signal, risks.
    """
    if regime is None:
        regime, _ = detect_market_regime(58, 51.3, 0.04)
    if regime not in REGIME_CONVICTION_CAP:
        return {"error": f"Invalid regime: {regime}", "valid": list(REGIME_CONVICTION_CAP)}

    scan = _global_scan(regime)
    return {
        "skill": "narrative-rotation-index",
        "version": "8.1",
        "regime": regime,
        "regime_cap": REGIME_CONVICTION_CAP[regime],
        "top_narrative": scan["top_narrative"],
        "narrative_rankings": [
            {
                "narrative": n,
                "verdict": d["verdict"],
                "conviction": d["conviction"],
                "exhaustion_score": d["exhaustion_score"],
                "bucket_scores": d["bucket_scores"],
                "weight_pct": scan["portfolio_weights"][n],
            }
            for n, d in scan["narrative_rankings"]
        ],
        "rotation_signal": scan["rotation_signal"],
        "risks": scan["risks"],
    }


@mcp.tool()
def detect_regime(
    fear_greed_index: int,
    btc_dominance_pct: float,
    total_mcap_change_7d: float,
) -> dict[str, Any]:
    """Classify market regime from macro inputs.

    Args:
        fear_greed_index: 0-100 (CMC Fear & Greed).
        btc_dominance_pct: BTC market cap as % of total crypto mcap.
        total_mcap_change_7d: 7-day change in total mcap (decimal, e.g. 0.05 = +5%).

    Returns:
        regime, conviction_cap, position_multiplier, reason.
    """
    regime, reason = detect_market_regime(
        fear_greed_index, btc_dominance_pct, total_mcap_change_7d
    )
    return {
        "regime": regime,
        "conviction_cap": REGIME_CONVICTION_CAP[regime],
        "position_multiplier": REGIME_SIZING[regime],
        "reason": reason,
    }


@mcp.tool()
def get_twak_payload(narrative: str, amount_usd: float, verdict: str = "LONG") -> dict[str, Any]:
    """Generate a Trust Wallet Agent Kit (TWAK) BSC swap payload.

    Args:
        narrative: Target narrative basket.
        amount_usd: Total USD amount to deploy across the basket.
        verdict: Signal verdict ("STRONG_LONG", "LONG", "NEUTRAL", "AVOID").

    Returns:
        BNBAgent SDK v1 ToolCall format. Confirmation required unless
        AUTO_EXECUTE is enabled in the consumer's config.
    """
    if narrative not in NARRATIVE_BASKETS:
        return {
            "error": f"Unknown narrative: {narrative}",
            "available": list(NARRATIVE_BASKETS.keys()),
        }
    return generate_twak_payload(narrative, amount_usd, verdict)


@mcp.tool()
def list_narratives() -> dict[str, Any]:
    """List all supported narratives and their BSC basket compositions."""
    return {
        "narratives": {
            n: {
                "tokens": NARRATIVE_BASKETS[n]["tokens"],
                "bsc_addresses": NARRATIVE_BASKETS[n]["bsc_addresses"],
            }
            for n in NARRATIVE_BASKETS
        },
        "execution_limits": EXECUTION_LIMITS,
        "auto_execute": AUTO_EXECUTE,
    }


@mcp.tool()
def get_skill_info() -> dict[str, Any]:
    """Get skill metadata: version, scoring model, integrations."""
    return {
        "skill": "narrative-rotation-index",
        "version": "8.1",
        "author": "ASBESTOS19",
        "chain": "bsc",
        "scoring_model": "0.30*Momentum + 0.25*Liquidity + 0.20*Attention + 0.15*Fundamental + 0.10*Risk",
        "supported_narratives": list(NARRATIVE_BASKETS.keys()),
        "regimes": ["RISK_ON", "TRANSITION", "RISK_OFF"],
        "regime_caps": REGIME_CONVICTION_CAP,
        "integrations": [
            "CoinMarketCap AI Agent Hub",
            "Trust Wallet Agent Kit (TWAK)",
            "BNBAgent SDK",
            "Kaito (SoFi) social intelligence",
            "x402 tiered pricing",
        ],
        "tools": [
            "run_skill",
            "global_scan",
            "detect_regime",
            "get_twak_payload",
            "list_narratives",
            "get_skill_info",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="NRI MCP server")
    parser.add_argument("--http", action="store_true", help="Use streamable HTTP transport")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    args = parser.parse_args()

    if args.http:
        mcp.settings.port = args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
