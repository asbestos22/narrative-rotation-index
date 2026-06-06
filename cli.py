#!/usr/bin/env python3
"""nri — command-line interface for the Narrative Rotation Index.

A thin CLI over the NRI engine, powered by live CoinMarketCap data. Designed
for the CoinMarketCap AI Agent Hub CLI surface: a single command that scans
narratives, classifies the macro regime, and prints ranked verdicts.

Commands:
    nri scan                 Scan all narratives (live CMC data if CMC_API_KEY set)
    nri score <narrative>    Score a single narrative
    nri regime               Print the current macro regime only
    nri backtest [--days N]  Run the historical basket backtest

Examples:
    CMC_API_KEY=... nri scan
    CMC_API_KEY=... nri score "AI Tokens" --json
    nri backtest --days 90

Exit codes: 0 success, 1 user/input error, 2 upstream/API error.
"""

from __future__ import annotations

import argparse
import json
import sys

from backtest import (
    NARRATIVE_BASKETS,
    compute_narrative_score,
    run_backtest,
)


def _load_live_or_cached():
    """Return (data_by_narrative, regime, source). Uses live CMC when keyed."""
    import os

    if os.getenv("CMC_API_KEY"):
        try:
            from live_demo import fetch_live_dataset

            return fetch_live_dataset()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"warning: live CMC fetch failed ({exc}); using cached data\n")
    from backtest import CACHED_NARRATIVE_DATA, detect_market_regime

    # Derive a regime from cached macro proxy (neutral TRANSITION default).
    regime, _ = detect_market_regime(50, 52, 0.0)
    return CACHED_NARRATIVE_DATA, regime, "cached"


def cmd_scan(args: argparse.Namespace) -> int:
    data_by_narrative, regime, source = _load_live_or_cached()
    rows = []
    for narrative in NARRATIVE_BASKETS:
        data = data_by_narrative.get(narrative, {})
        result = compute_narrative_score(narrative, data, regime)
        rows.append((narrative, result))

    rows.sort(key=lambda r: r[1]["conviction"], reverse=True)

    if args.json:
        print(json.dumps(
            {"regime": regime, "source": source,
             "narratives": {n: r for n, r in rows}},
            indent=2,
        ))
        return 0

    print(f"NRI scan — regime: {regime}  (data: {source})")
    print(f"  {'Narrative':<14} | {'Verdict':<12} | {'Conv':>4}")
    print(f"  {'-' * 38}")
    for narrative, r in rows:
        print(f"  {narrative:<14} | {r['verdict']:<12} | {r['conviction']:>4}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    if args.narrative not in NARRATIVE_BASKETS:
        sys.stderr.write(
            f"error: unknown narrative '{args.narrative}'. "
            f"Choices: {', '.join(NARRATIVE_BASKETS)}\n"
        )
        return 1
    data_by_narrative, regime, source = _load_live_or_cached()
    data = data_by_narrative.get(args.narrative, {})
    result = compute_narrative_score(args.narrative, data, regime)
    if args.json:
        print(json.dumps({"regime": regime, "source": source, **result}, indent=2))
        return 0
    print(f"{args.narrative} — regime {regime} (data: {source})")
    print(f"  verdict:    {result['verdict']}")
    print(f"  conviction: {result['conviction']}")
    print(f"  buckets:    {result.get('bucket_scores', {})}")
    return 0


def cmd_regime(args: argparse.Namespace) -> int:
    _, regime, source = _load_live_or_cached()
    if args.json:
        print(json.dumps({"regime": regime, "source": source}))
    else:
        print(f"{regime} (data: {source})")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    for narrative in NARRATIVE_BASKETS:
        r = run_backtest(narrative, days=args.days)
        print(
            f"{narrative:<14} return {r['total_return_pct']:+6.2f}%  "
            f"Sharpe {r['sharpe_ratio']:+5.2f}  trades {r['total_trades']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nri", description="Narrative Rotation Index CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan all narratives")
    p_scan.add_argument("--json", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_score = sub.add_parser("score", help="Score a single narrative")
    p_score.add_argument("narrative")
    p_score.add_argument("--json", action="store_true")
    p_score.set_defaults(func=cmd_score)

    p_regime = sub.add_parser("regime", help="Print current macro regime")
    p_regime.add_argument("--json", action="store_true")
    p_regime.set_defaults(func=cmd_regime)

    p_bt = sub.add_parser("backtest", help="Run historical backtest")
    p_bt.add_argument("--days", type=int, default=90)
    p_bt.set_defaults(func=cmd_backtest)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
