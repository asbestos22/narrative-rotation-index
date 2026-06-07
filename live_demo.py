#!/usr/bin/env python3
"""Live CoinMarketCap API integration for the Narrative Rotation Index.

Pulls real-time data from CMC v1 endpoints, transforms it into the schema
expected by `compute_narrative_score`, and runs the live scoring pipeline.

Usage:
    export CMC_API_KEY=your_key
    python live_demo.py                    # scan all 5 narratives
    python live_demo.py --narrative Meme   # single narrative deep-dive
    python live_demo.py --json             # output structured JSON only

If CMC_API_KEY is not set, falls back to cached mock data with a clear
warning so the demo still produces output without a key.
"""

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib import error, parse, request

import backtest
from backtest import (
    CACHED_NARRATIVE_DATA,
    NARRATIVE_BASKETS,
    REGIME_CONVICTION_CAP,
    check_execution_guards,
    compute_narrative_score,
    detect_market_regime,
    generate_twak_payload,
    global_scan,
)

CMC_BASE = "https://pro-api.coinmarketcap.com"
CMC_TIMEOUT = 10


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{CMC_BASE}{path}?{parse.urlencode(params)}"
    req = request.Request(
        url,
        headers={
            "X-CMC_PRO_API_KEY": api_key,
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=CMC_TIMEOUT) as r:
            return json.loads(r.read())
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"CMC API error {e.code}: {body[:200]}") from e
    except (error.URLError, TimeoutError) as e:
        raise RuntimeError(f"CMC API network error: {e}") from e


def fetch_quotes(symbols: list[str], api_key: str) -> dict[str, dict[str, Any]]:
    """Fetch /v1/cryptocurrency/quotes/latest for a list of symbols."""
    data = _get(
        "/v1/cryptocurrency/quotes/latest",
        {"symbol": ",".join(symbols), "convert": "USD"},
        api_key,
    )
    return data.get("data", {})


def fetch_global_metrics(api_key: str) -> dict[str, Any]:
    """Fetch /v1/global-metrics/quotes/latest for BTC dominance and total mcap."""
    data = _get("/v1/global-metrics/quotes/latest", {}, api_key)
    return data.get("data", {})


def fetch_fear_greed(api_key: str) -> int:
    """Fetch /v3/fear-and-greed/latest. Returns 50 (neutral) on failure."""
    try:
        data = _get("/v3/fear-and-greed/latest", {}, api_key)
        return int(data.get("data", {}).get("value", 50))
    except RuntimeError:
        return 50


# ---------------------------------------------------------------------------
# v10: Stablecoin Risk Radar — live metrics from CMC
# ---------------------------------------------------------------------------
STABLES_TO_TRACK = ["USDT", "USDC", "FDUSD", "USDe", "DAI", "FRAX", "TUSD", "USDD", "lisUSD"]


def fetch_stable_metrics(api_key: str) -> list:
    """Fetch live stablecoin metrics, return list[StableMetrics]."""
    from stablecoin_risk import StableMetrics

    try:
        quotes = fetch_quotes(STABLES_TO_TRACK, api_key)
    except RuntimeError:
        return []

    metrics = []
    for sym in STABLES_TO_TRACK:
        if sym not in quotes:
            continue
        v = quotes[sym]
        q = (v[0] if isinstance(v, list) else v).get("quote", {}).get("USD", {})
        price = q.get("price")
        peg_pct = (price - 1.0) * 100 if price else None
        metrics.append(StableMetrics(
            symbol=sym,
            peg_deviation_pct=peg_pct,
            peg_deviation_24h_max_pct=peg_pct,  # CMC doesn't expose intraday max, use spot
            market_cap_usd=q.get("market_cap"),
            market_cap_change_7d_pct=q.get("percent_change_7d"),
            market_cap_change_24h_pct=q.get("percent_change_24h"),
            volume_24h_usd=q.get("volume_24h"),
            volume_change_24h_pct=q.get("volume_change_24h"),
        ))
    return metrics


def transform_to_scoring_schema(
    narrative: str,
    quotes: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    """Transform CMC quote data into the schema expected by compute_narrative_score.

    Falls back to cached mock values for metrics CMC doesn't expose directly
    (Kaito mindshare, on-chain holder growth, etc.) — those are external
    enrichments that require a separate API.
    """
    basket_tokens = NARRATIVE_BASKETS[narrative]["tokens"]
    available = [t for t in basket_tokens if t in quotes]

    if not available:
        return fallback

    # CMC returns either a dict (single match) or list (multi-listing) per symbol.
    def first(sym: str) -> dict[str, Any]:
        v = quotes[sym]
        return v[0] if isinstance(v, list) else v

    usd_quotes = [first(t)["quote"]["USD"] for t in available]

    # Aggregate basket-level metrics from real CMC data
    avg_pct_24h = sum(q.get("percent_change_24h", 0) or 0 for q in usd_quotes) / len(usd_quotes)
    avg_pct_7d = sum(q.get("percent_change_7d", 0) or 0 for q in usd_quotes) / len(usd_quotes)
    avg_pct_30d = sum(q.get("percent_change_30d", 0) or 0 for q in usd_quotes) / len(usd_quotes)
    total_volume = sum(q.get("volume_24h", 0) or 0 for q in usd_quotes)
    total_mcap = sum(q.get("market_cap", 0) or 0 for q in usd_quotes)
    avg_volume_change_24h = sum(
        q.get("volume_change_24h", 0) or 0 for q in usd_quotes
    ) / len(usd_quotes)

    # CMC rank is integer; lower = better. Average across basket.
    avg_rank = sum(first(t).get("cmc_rank", 999) or 999 for t in available) / len(available)

    # Build scoring dict — keep external metrics from fallback for ones CMC can't supply
    live_data = dict(fallback)
    live_data.update(
        {
            "basket_return_7d_pct": avg_pct_7d / 100,
            "volume_change_7d_pct": avg_volume_change_24h / 100,  # 24h proxy
            "market_cap_change_7d_pct": avg_pct_7d / 100,  # mcap tracks price for backtest
            "trending_rank_avg": int(avg_rank / 10),  # rank/10 as proxy for trending
            "liquidity_usd": total_volume,  # 24h volume as liquidity proxy
            "_live_data": True,
            "_basket_tokens_resolved": available,
            "_cmc_metrics": {
                "avg_24h_change_pct": round(avg_pct_24h, 2),
                "avg_7d_change_pct": round(avg_pct_7d, 2),
                "avg_30d_change_pct": round(avg_pct_30d, 2),
                "total_24h_volume_usd": int(total_volume),
                "total_market_cap_usd": int(total_mcap),
                "avg_cmc_rank": int(avg_rank),
            },
        }
    )

    # Relative strength vs BTC: derive if BTC is in quotes
    btc = quotes.get("BTC")
    if btc:
        btc_q = (btc[0] if isinstance(btc, list) else btc)["quote"]["USD"]
        btc_7d = btc_q.get("percent_change_7d", 0) or 0
        if btc_7d != 0:
            live_data["relative_strength_vs_btc_7d"] = (1 + avg_pct_7d / 100) / (
                1 + btc_7d / 100
            )

    return live_data


def fetch_live_dataset():
    """Fetch and transform live CMC data for every narrative.

    Returns (data_by_narrative, regime, source) where source is "CMC v1 API
    (live)" or "cached mock data". Shared by the CLI (cli.py) and any caller
    that wants the scoring-ready dataset without the demo's printing.
    """
    api_key = os.environ.get("CMC_API_KEY")
    using_live = bool(api_key)

    btc_dom, mcap_change, fg = 51.3, 0.04, 58
    quotes: dict[str, Any] = {}

    if using_live:
        assert api_key is not None  # guaranteed by using_live
        try:
            global_data = fetch_global_metrics(api_key)
            btc_dom = global_data.get("btc_dominance", 51.3)
            mcap_change = (
                global_data.get("quote", {}).get("USD", {}).get(
                    "total_market_cap_yesterday_percentage_change", 4.0
                )
                / 100
            )
            fg = fetch_fear_greed(api_key)

            all_symbols = ["BTC"]
            for n_basket in NARRATIVE_BASKETS.values():
                all_symbols.extend(n_basket["tokens"])
            quotes = fetch_quotes(all_symbols, api_key)
        except RuntimeError:
            using_live = False

    regime, _ = detect_market_regime(fg, btc_dom, mcap_change)

    data_by_narrative = {}
    for n in NARRATIVE_BASKETS:
        fallback = CACHED_NARRATIVE_DATA[n]
        data_by_narrative[n] = (
            transform_to_scoring_schema(n, quotes, fallback) if using_live else fallback
        )

    return data_by_narrative, regime, "CMC v1 API (live)" if using_live else "cached mock data"


def run_live(narrative: str | None, output_json: bool) -> int:
    api_key = os.environ.get("CMC_API_KEY")
    using_live = bool(api_key)

    if not using_live:
        print(
            "⚠️  CMC_API_KEY not set — falling back to cached mock data.",
            file=sys.stderr,
        )
        print(
            "   Set CMC_API_KEY in .env to run against live CMC v1 endpoints.\n",
            file=sys.stderr,
        )

    # Step 1: regime detection
    if api_key:
        print("[1/4] Fetching CMC global metrics + Fear & Greed...", file=sys.stderr)
        try:
            global_data = fetch_global_metrics(api_key)
            btc_dom = global_data.get("btc_dominance", 51.3)
            mcap_change = (
                global_data.get("quote", {}).get("USD", {}).get(
                    "total_market_cap_yesterday_percentage_change", 4.0
                )
                / 100
            )
            fg = fetch_fear_greed(api_key)
        except RuntimeError as e:
            print(f"   ⚠️  CMC global fetch failed: {e}", file=sys.stderr)
            btc_dom, mcap_change, fg = 51.3, 0.04, 58
            using_live = False
    else:
        btc_dom, mcap_change, fg = 51.3, 0.04, 58

    regime, regime_reason = detect_market_regime(fg, btc_dom, mcap_change)
    cap = REGIME_CONVICTION_CAP[regime]

    # Step 2: fetch quotes for every basket token
    all_symbols = ["BTC"]
    for n_basket in NARRATIVE_BASKETS.values():
        all_symbols.extend(n_basket["tokens"])

    quotes: dict[str, Any] = {}
    if api_key and using_live:
        print(f"[2/4] Fetching quotes for {len(all_symbols)} tokens...", file=sys.stderr)
        try:
            quotes = fetch_quotes(all_symbols, api_key)
        except RuntimeError as e:
            print(f"   ⚠️  CMC quote fetch failed: {e}", file=sys.stderr)
            using_live = False

    # Step 3: score narratives
    print(f"[3/4] Scoring narratives ({'LIVE' if using_live else 'MOCK'})...", file=sys.stderr)
    target_narratives = [narrative] if narrative else list(NARRATIVE_BASKETS.keys())

    results = {}
    for n in target_narratives:
        if n not in NARRATIVE_BASKETS:
            print(f"❌ Unknown narrative: {n}", file=sys.stderr)
            return 2
        fallback = CACHED_NARRATIVE_DATA[n]
        data = transform_to_scoring_schema(n, quotes, fallback) if using_live else fallback
        score = compute_narrative_score(n, data, regime)
        allowed, violations = check_execution_guards(n, data)
        results[n] = {
            "score": score,
            "data": data,
            "execution_allowed": allowed,
            "violations": violations,
        }

    # Step 4: output
    print("[4/4] Output\n", file=sys.stderr)

    output = {
        "skill": "narrative-rotation-index",
        "version": "8.1",
        "data_source": "CMC v1 API (live)" if using_live else "cached mock data",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "macro": {
            "fear_greed_index": fg,
            "btc_dominance_pct": round(btc_dom, 2),
            "total_mcap_change_7d_pct": round(mcap_change * 100, 2),
        },
        "regime": regime,
        "regime_reason": regime_reason,
        "regime_cap": cap,
        "narratives": {},
    }

    for n, r in results.items():
        s = r["score"]
        cmc_metrics = r["data"].get("_cmc_metrics")
        narrative_out = {
            "verdict": s["verdict"],
            "conviction": s["conviction"],
            "exhaustion_score": s["exhaustion_score"],
            "bucket_scores": s["bucket_scores"],
            "reasons": s["reasons"][:5],
            "execution_allowed": r["execution_allowed"],
            "violations": r["violations"],
        }
        if cmc_metrics:
            narrative_out["cmc_live_metrics"] = cmc_metrics
            narrative_out["resolved_tokens"] = r["data"].get("_basket_tokens_resolved", [])

        if s["verdict"] in ["STRONG_LONG", "LONG"] and r["execution_allowed"]:
            narrative_out["twak_payload"] = generate_twak_payload(n, 500, s["verdict"])

        output["narratives"][n] = narrative_out

    # ---- v10: Stablecoin Risk Radar overlay ----
    try:
        from stablecoin_risk import rank_stables, rotation_target, STABLE_UNIVERSE
        live_stables = fetch_stable_metrics(api_key) if api_key else []
        if live_stables:
            srr_scores = rank_stables(live_stables)
            srr_target = rotation_target(srr_scores)
            output["stablecoin_risk"] = {
                "source": "cmc_live",
                "rankings": [
                    {
                        "symbol": s.symbol,
                        "verdict": s.verdict,
                        "score": s.score,
                        "issuer": s.issuer,
                        "type": s.type,
                        "bucket_scores": s.bucket_scores,
                        "reasons": s.reasons[:3],
                        "risks": s.risks[:3],
                        "bsc_address": STABLE_UNIVERSE.get(s.symbol, {}).get("bsc"),
                    }
                    for s in srr_scores
                ],
                "target": (
                    {
                        "symbol": srr_target.symbol,
                        "verdict": srr_target.verdict,
                        "score": srr_target.score,
                        "bsc_address": STABLE_UNIVERSE.get(srr_target.symbol, {}).get("bsc"),
                    }
                    if srr_target else None
                ),
            }

            # Defensive rotation override on the macro signal
            top_score = max(
                (d["conviction"] for d in output["narratives"].values()),
                default=0,
            )
            if regime == "RISK_OFF" and top_score < 30 and srr_target:
                output["macro"]["defensive_rotation"] = {
                    "trigger": "RISK_OFF + top conviction < 30",
                    "target_symbol": srr_target.symbol,
                    "target_verdict": srr_target.verdict,
                    "target_score": srr_target.score,
                    "target_bsc_address": STABLE_UNIVERSE.get(srr_target.symbol, {}).get("bsc"),
                }
    except Exception as e:
        output["stablecoin_risk"] = {"error": str(e)}

    if output_json:
        print(json.dumps(output, indent=2))
    else:
        _print_human(output)

    return 0


def _print_human(output: dict[str, Any]) -> None:
    print("=" * 80)
    print(f"NARRATIVE ROTATION INDEX — Live Demo")
    print(f"Source: {output['data_source']}")
    print(f"Time:   {output['timestamp_utc']}")
    print("=" * 80)
    macro = output["macro"]
    print(f"\n[Macro] Fear & Greed: {macro['fear_greed_index']}/100  |  "
          f"BTC dominance: {macro['btc_dominance_pct']}%  |  "
          f"Total mcap 24h: {macro['total_mcap_change_7d_pct']:+.2f}%")
    print(f"[Regime] {output['regime']}  (cap: {output['regime_cap']}/100)")
    print(f"         {output['regime_reason']}")
    print()
    print(f"  {'Narrative':<14} | {'Verdict':<12} | {'Conv':>5} | {'EXH':>4} | "
          f"{'MOM':>3} {'LIQ':>3} {'ATT':>3} {'FND':>3} {'RSK':>3} | Exec")
    print(f"  {'-'*90}")
    for n, d in output["narratives"].items():
        b = d["bucket_scores"]
        exec_str = "✓" if d["execution_allowed"] else "✗"
        print(f"  {n:<14} | {d['verdict']:<12} | {d['conviction']:>5} | "
              f"{d['exhaustion_score']:>4} | "
              f"{b['momentum']:>3} {b['liquidity']:>3} {b['attention']:>3} "
              f"{b['fundamental']:>3} {b['risk_adjustment']:>3} | {exec_str}")
    print()
    # Show live CMC metrics for first narrative if available
    first = next(iter(output["narratives"].values()))
    if "cmc_live_metrics" in first:
        print(f"[Sample live metrics — {next(iter(output['narratives']))}]")
        for k, v in first["cmc_live_metrics"].items():
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(description="Live CMC integration demo")
    parser.add_argument("--narrative", help="Single narrative to score")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()
    sys.exit(run_live(args.narrative, args.json))


if __name__ == "__main__":
    main()
