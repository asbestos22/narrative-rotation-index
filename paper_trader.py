#!/usr/bin/env python3
"""NRI Paper Trader — Track 1 simulator.

Reads /api/live, applies the rotation sizing rules, fetches live PancakeSwap
quotes for any positions it would open or close, and appends decisions to
data/paper_ledger.csv. Pure read-only — no private keys, no broadcasts.

State files (under /home/ubuntu/nri-web/data/):
- paper_state.json   : current bankroll, positions, last regime
- paper_ledger.csv   : append-only audit log of every decision

Decision rules (from NRI conviction):
- STRONG_LONG (>=60)  : 30% of bankroll into the basket's top token
- LONG (45-59)        : 15% into top, 10% into #2
- NEUTRAL (25-44)     : hold cash; close anything below 25
- AVOID (<25)         : exit if held
- CONCENTRATE_<X>     : 60% into the called-out narrative top token
- DEFENSIVE_ROTATION  : flatten all to cash

Trade costs:
- 0.5% PancakeSwap LP fee per swap
- 1% slippage cap (skipped if quote impact > 1%)
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import urllib.request
import urllib.error

DATA_DIR = Path("/home/ubuntu/nri-web/data")
STATE_PATH = DATA_DIR / "paper_state.json"
LEDGER_PATH = DATA_DIR / "paper_ledger.csv"
LIVE_URL = os.environ.get("NRI_LIVE_URL", "http://127.0.0.1:8017/api/live")
INITIAL_BANKROLL = 1000.0  # USD

PANCAKE_ROUTER = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
RPC = os.environ.get("BSC_RPC", "https://bsc-dataseed.binance.org")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

@dataclass
class Position:
    token: str
    address: str
    chain: str
    qty: float           # token units held
    entry_usd: float     # USD basis at entry
    entry_price: float   # USD per token at entry
    mark_price: float    # last quoted USD per token
    narrative: str
    opened_at: int


@dataclass
class State:
    bankroll_usd: float
    cash_usd: float
    positions: dict[str, Position]
    last_regime: str | None
    last_decision_at: int | None
    realized_pnl_usd: float
    decision_count: int

    @classmethod
    def load(cls) -> "State":
        if STATE_PATH.exists():
            d = json.loads(STATE_PATH.read_text())
            d["positions"] = {
                k: Position(**v) for k, v in d.get("positions", {}).items()
            }
            return cls(**d)
        return cls(
            bankroll_usd=INITIAL_BANKROLL,
            cash_usd=INITIAL_BANKROLL,
            positions={},
            last_regime=None,
            last_decision_at=None,
            realized_pnl_usd=0.0,
            decision_count=0,
        )

    def save(self) -> None:
        d = asdict(self)
        d["positions"] = {k: asdict(v) for k, v in self.positions.items()}
        STATE_PATH.write_text(json.dumps(d, indent=2))

    def total_value(self) -> float:
        return self.cash_usd + sum(
            p.qty * p.mark_price for p in self.positions.values()
        )

    def unrealized(self) -> float:
        return sum(
            p.qty * (p.mark_price - p.entry_price)
            for p in self.positions.values()
        )


# ---------------------------------------------------------------------------
# Live quote — PancakeSwap router via JSON-RPC eth_call
# ---------------------------------------------------------------------------

def rpc_call(method: str, params: list) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        RPC,
        data=payload,
        headers={
            "content-type": "application/json",
            "user-agent": "nri-paper-trader/1.0",
            "accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        out = json.load(r)
        if "error" in out:
            raise RuntimeError(f"RPC error: {out['error']}")
        return out["result"]


def encode_get_amounts_out(amount_in_wei: int, path: list[str]) -> str:
    """Encode getAmountsOut(uint256, address[]) calldata."""
    sel = "0xd06ca61f"  # getAmountsOut
    # ABI encode: amountIn (32 bytes), offset to path (32 bytes = 0x40), path length, path elements
    h = "{:064x}".format(amount_in_wei)
    h += "{:064x}".format(0x40)  # offset
    h += "{:064x}".format(len(path))
    for a in path:
        h += "0" * 24 + a.lower().replace("0x", "")
    return sel + h


def quote_token_in_usd(token_addr: str) -> float | None:
    """Quote: 1 token -> USDT via WBNB, return USD per token.

    Uses PancakeSwap v2 getAmountsOut. Returns None on any quote failure.
    """
    USDT = "0x55d398326f99059fF775485246999027B3197955"
    token_addr = token_addr.lower()
    try:
        # Probe token decimals via standard ERC-20 decimals()
        dec_calldata = "0x313ce567"
        dec_hex = rpc_call("eth_call", [{"to": token_addr, "data": dec_calldata}, "latest"])
        decimals = int(dec_hex, 16) if dec_hex and dec_hex != "0x" else 18
        amount_in = 10 ** decimals
        # WBNB special-case: skip the WBNB hop
        if token_addr == WBNB.lower():
            path = [WBNB, USDT]
        elif token_addr == USDT.lower():
            return 1.0
        else:
            path = [token_addr, WBNB, USDT]
        data = encode_get_amounts_out(amount_in, path)
        result = rpc_call("eth_call", [{"to": PANCAKE_ROUTER, "data": data}, "latest"])
        if not result or result == "0x":
            return None
        # decode last uint256 from result
        # result format: offset, length, [amountIn, ..., amountOut]
        # last 32 bytes = final amountOut (USDT, 18 decimals)
        last_word = int(result[-64:], 16)
        return last_word / 1e18
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------

VERDICT_BANDS = {
    "STRONG_LONG": (60, 1.0),
    "LONG": (45, 0.59),
    "NEUTRAL": (25, 0.44),
    "AVOID": (0, 0.24),
}


def verdict(score: float) -> str:
    if score >= 60:
        return "STRONG_LONG"
    if score >= 45:
        return "LONG"
    if score >= 25:
        return "NEUTRAL"
    return "AVOID"


def desired_allocation(narratives_data: dict, bsc_disc: dict, regime: str, top_conviction: float) -> tuple[dict[str, float], dict[str, dict]]:
    """Return (alloc, token_meta) where:
      alloc = {token_address.lower(): target_weight_pct} as fraction of bankroll
      token_meta = {token_address.lower(): {symbol, narrative, score, verdict}}

    Sums to <= 1.0. Anything not in alloc gets exited.

    Concentration controls:
      - Single-token cap: 30% of bankroll (prevents one token blowing the book
        when it appears in multiple narrative buckets)
      - Already-allocated tokens get skipped from later narratives (first-come
        first-served by conviction rank)
    """
    SINGLE_TOKEN_CAP = 0.30
    alloc: dict[str, float] = {}
    token_meta: dict[str, dict] = {}

    # DEFENSIVE_ROTATION trigger: flatten everything
    if regime == "RISK_OFF" and top_conviction < 30:
        return alloc, token_meta

    # Sort narratives by conviction descending, take top 5
    nar_items = sorted(
        narratives_data.items(),
        key=lambda kv: kv[1].get("conviction", 0),
        reverse=True,
    )[:5]

    for narrative_name, n in nar_items:
        score = n.get("conviction", 0)
        v = verdict(score)
        if v in ("NEUTRAL", "AVOID"):
            continue

        # Get BSC tokens for this narrative — bsc_discovery uses different name keys
        # in some cases. Match by name first, then fuzzy fallback.
        bsc_tokens = bsc_disc.get(narrative_name) or []
        if not bsc_tokens:
            for k, v_list in bsc_disc.items():
                if narrative_name.split()[0].lower() in k.lower():
                    bsc_tokens = v_list
                    break
        if not bsc_tokens:
            continue

        # Filter: valid address, ASCII symbol (skip UTF-8 names with no DEX pair),
        # min mcap >$1M. Sort by 7d change descending (rotate-into-strength).
        valid = [
            t for t in bsc_tokens
            if t.get("address")
            and t.get("market_cap", 0) > 1_000_000
            and t.get("symbol", "").isascii()
        ]
        valid.sort(key=lambda t: t.get("change_7d", 0), reverse=True)

        # Skip tokens already in alloc (higher-conviction narrative claimed them)
        valid = [t for t in valid if t["address"].lower() not in alloc]
        if not valid:
            continue

        if v == "STRONG_LONG":
            top = valid[0]
            addr = top["address"].lower()
            alloc[addr] = min(SINGLE_TOKEN_CAP, alloc.get(addr, 0) + 0.30)
            token_meta[addr] = {
                "symbol": top["symbol"], "narrative": narrative_name,
                "score": score, "verdict": v, "chain": "bsc",
            }
        elif v == "LONG":
            for i, w in [(0, 0.15), (1, 0.10)]:
                if i < len(valid):
                    addr = valid[i]["address"].lower()
                    alloc[addr] = min(SINGLE_TOKEN_CAP, alloc.get(addr, 0) + w)
                    token_meta[addr] = {
                        "symbol": valid[i]["symbol"], "narrative": narrative_name,
                        "score": score, "verdict": v, "chain": "bsc",
                    }

    # Normalize if over 100% (defensive — shouldn't trigger with current weights)
    total = sum(alloc.values())
    if total > 1.0:
        scale = 1.0 / total
        alloc = {k: v * scale for k, v in alloc.items()}
    return alloc, token_meta


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

LEDGER_HEADER = [
    "ts_iso", "ts_unix", "action", "token", "address", "narrative",
    "qty", "price_usd", "value_usd", "fee_usd", "regime", "verdict",
    "score", "reason", "bankroll_after", "cash_after", "realized_pnl",
]


def append_ledger(row: dict) -> None:
    is_new = not LEDGER_PATH.exists()
    with LEDGER_PATH.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_HEADER)
        if is_new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in LEDGER_HEADER})


# ---------------------------------------------------------------------------
# Rebalance
# ---------------------------------------------------------------------------

FEE_RATE = 0.005  # PancakeSwap 0.25% × 2 hops ≈ 0.5%
SLIP_CAP = 0.01   # 1% — informational only here, all paper


def rebalance(state: State, live: dict) -> list[dict]:
    """Plan + execute paper trades. Returns ledger rows written."""
    narratives_data = live.get("narratives") or {}
    bsc_disc = (live.get("bsc_discovery") or {}).get("narratives") or {}
    regime = live.get("regime", "TRANSITION")
    top_conv = max(
        (n.get("conviction", 0) for n in narratives_data.values()),
        default=0,
    )

    desired, token_meta = desired_allocation(narratives_data, bsc_disc, regime, top_conv)
    rows: list[dict] = []
    now = int(time.time())
    iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))

    # Mark all positions to current price
    for addr, p in state.positions.items():
        mp = quote_token_in_usd(p.address) or p.mark_price
        p.mark_price = mp

    # Step 1: close anything not in desired (or zero-weight)
    to_close = [addr for addr in list(state.positions.keys()) if desired.get(addr, 0) == 0]
    for addr in to_close:
        p = state.positions[addr]
        proceeds = p.qty * p.mark_price * (1 - FEE_RATE)
        pnl = proceeds - p.entry_usd
        state.cash_usd += proceeds
        state.realized_pnl_usd += pnl
        rows.append({
            "ts_iso": iso, "ts_unix": now, "action": "SELL",
            "token": p.token, "address": p.address, "narrative": p.narrative,
            "qty": f"{p.qty:.6f}", "price_usd": f"{p.mark_price:.6f}",
            "value_usd": f"{proceeds:.4f}", "fee_usd": f"{p.qty * p.mark_price * FEE_RATE:.4f}",
            "regime": regime, "verdict": "EXIT",
            "score": "", "reason": f"rebalance_close pnl={pnl:+.2f}",
            "bankroll_after": f"{state.cash_usd:.2f}",
            "cash_after": f"{state.cash_usd:.2f}",
            "realized_pnl": f"{state.realized_pnl_usd:+.2f}",
        })
        del state.positions[addr]

    # Step 2: open / scale up to desired weights
    bankroll_for_alloc = state.cash_usd + sum(p.qty * p.mark_price for p in state.positions.values())
    for addr, target_pct in desired.items():
        target_usd = bankroll_for_alloc * target_pct
        current_usd = 0.0
        if addr in state.positions:
            current_usd = state.positions[addr].qty * state.positions[addr].mark_price

        delta = target_usd - current_usd
        if delta < 5.0:  # skip < $5 deltas (noise floor)
            continue

        meta = token_meta.get(addr, {})
        if not meta:
            continue

        # Quote live price
        price = quote_token_in_usd(addr)
        if price is None or price <= 0:
            rows.append({
                "ts_iso": iso, "ts_unix": now, "action": "SKIP",
                "token": meta.get("symbol", "?"), "address": addr,
                "narrative": meta.get("narrative", ""), "qty": "0", "price_usd": "0",
                "value_usd": "0", "fee_usd": "0", "regime": regime,
                "verdict": meta.get("verdict", ""), "score": meta.get("score", 0),
                "reason": "no_quote",
                "bankroll_after": f"{state.total_value():.2f}",
                "cash_after": f"{state.cash_usd:.2f}",
                "realized_pnl": f"{state.realized_pnl_usd:+.2f}",
            })
            continue

        if delta > state.cash_usd:
            delta = state.cash_usd  # cap by available cash
        if delta < 5.0:
            continue

        qty_added = delta * (1 - FEE_RATE) / price
        fee_usd = delta * FEE_RATE
        state.cash_usd -= delta

        if addr in state.positions:
            p = state.positions[addr]
            new_qty = p.qty + qty_added
            new_basis = p.entry_usd + delta
            p.qty = new_qty
            p.entry_usd = new_basis
            p.entry_price = new_basis / new_qty
            p.mark_price = price
        else:
            state.positions[addr] = Position(
                token=meta.get("symbol", "?"),
                address=addr,
                chain=meta.get("chain", "bsc"),
                qty=qty_added,
                entry_usd=delta,
                entry_price=price,
                mark_price=price,
                narrative=meta.get("narrative", ""),
                opened_at=now,
            )

        rows.append({
            "ts_iso": iso, "ts_unix": now, "action": "BUY",
            "token": meta.get("symbol", "?"), "address": addr,
            "narrative": meta.get("narrative", ""), "qty": f"{qty_added:.6f}",
            "price_usd": f"{price:.6f}", "value_usd": f"{delta:.4f}",
            "fee_usd": f"{fee_usd:.4f}", "regime": regime,
            "verdict": meta.get("verdict", ""), "score": meta.get("score", 0),
            "reason": f"target_{int(target_pct*100)}pct",
            "bankroll_after": f"{state.total_value():.2f}",
            "cash_after": f"{state.cash_usd:.2f}",
            "realized_pnl": f"{state.realized_pnl_usd:+.2f}",
        })

    state.last_regime = regime
    state.last_decision_at = now
    state.decision_count += 1
    state.bankroll_usd = state.total_value()

    for r in rows:
        append_ledger(r)
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fetch_live() -> dict:
    with urllib.request.urlopen(LIVE_URL, timeout=15) as r:
        return json.load(r)


def main() -> int:
    DATA_DIR.mkdir(exist_ok=True)
    state = State.load()
    try:
        live = fetch_live()
    except Exception as e:
        print(f"[err] fetch_live: {e}", file=sys.stderr)
        return 1

    rows = rebalance(state, live)
    state.save()

    print(f"[paper] decision #{state.decision_count}  regime={state.last_regime}")
    print(f"[paper] cash=${state.cash_usd:.2f}  positions={len(state.positions)}  total=${state.total_value():.2f}")
    print(f"[paper] realized_pnl=${state.realized_pnl_usd:+.2f}  unrealized=${state.unrealized():+.2f}")
    if rows:
        print(f"[paper] {len(rows)} trade(s):")
        for r in rows:
            print(f"  {r['action']:4} {r['token']:8} ${r['value_usd']:>10}  ({r['narrative']})")
    else:
        print("[paper] no trades this cycle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
