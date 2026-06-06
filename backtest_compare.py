#!/usr/bin/env python3
"""Multi-window backtest comparison.

Runs the same engine across 30, 90, and 365 day windows so you can see
how the strategy's edge emerges over longer holding periods. Same seed
(42), same baskets, only the window length changes.

Usage:
    python backtest_compare.py
"""

from backtest import NARRATIVE_BASKETS, run_backtest, build_regime_sequence
import random


def fmt_row(label: str, r: dict) -> str:
    return (
        f"  {label:<14} | "
        f"{r['total_return_pct']:>+7.2f}% | "
        f"{r['sharpe_ratio']:>6.2f} | "
        f"{r['sortino_ratio']:>7.2f} | "
        f"{r['max_drawdown_pct']:>5.2f}% | "
        f"{r['win_rate_pct']:>5.1f}% | "
        f"{r['total_trades']:>4d} | "
        f"${r['total_fees_paid']:>6.2f}"
    )


def regime_mix(days: int, seed: int = 42) -> dict[str, int]:
    random.seed(seed)
    seq = build_regime_sequence(days, "TRANSITION")
    return {
        "RISK_ON": sum(1 for r in seq if r == "RISK_ON"),
        "TRANSITION": sum(1 for r in seq if r == "TRANSITION"),
        "RISK_OFF": sum(1 for r in seq if r == "RISK_OFF"),
    }


def run_window(days: int) -> None:
    mix = regime_mix(days)
    total = sum(mix.values())
    print(f"  ── {days}-day window ──")
    print(
        f"  Regime mix: "
        f"RISK_ON={mix['RISK_ON']}d ({mix['RISK_ON']/total:.0%})  "
        f"TRANSITION={mix['TRANSITION']}d ({mix['TRANSITION']/total:.0%})  "
        f"RISK_OFF={mix['RISK_OFF']}d ({mix['RISK_OFF']/total:.0%})"
    )
    print(
        f"  {'Narrative':<14} | {'Return':>7} | {'Sharpe':>6} | "
        f"{'Sortino':>7} | {'MaxDD':>6} | {'WinRt':>5} | "
        f"{'Trd':>4} | {'Fees':>6}"
    )
    print(f"  {'-' * 95}")

    avg_returns: list[float] = []
    avg_sharpes: list[float] = []
    total_fees = 0.0
    total_trades = 0

    for narrative in NARRATIVE_BASKETS:
        r = run_backtest(narrative, days=days)
        print(fmt_row(narrative, r))
        avg_returns.append(r["total_return_pct"])
        avg_sharpes.append(r["sharpe_ratio"])
        total_fees += r["total_fees_paid"]
        total_trades += r["total_trades"]

    eq_return = sum(avg_returns) / len(avg_returns)
    avg_sharpe = sum(avg_sharpes) / len(avg_sharpes)
    print(f"  {'-' * 95}")
    print(
        f"  Equal-weight return: {eq_return:+.2f}%   "
        f"avg Sharpe: {avg_sharpe:+.2f}   "
        f"trades: {total_trades}   fees: ${total_fees:.2f}"
    )
    print()


def main() -> None:
    print("\n  CMC Narrative Rotation Index — Multi-window comparison (seed=42)")
    print(f"  {'=' * 100}\n")

    for window in (30, 90, 365):
        run_window(window)

    print("  Notes:")
    print("    • Same engine, same seed, same baskets across all windows.")
    print("    • 30d: too few trades to overcome holding-period drift noise.")
    print("    • 90d: trade alpha begins to express itself.")
    print("    • 365d: realistic regime mix; strategy's job is survival in")
    print("      RISK_OFF stretches and participation when macro improves.")
    print()


if __name__ == "__main__":
    main()
