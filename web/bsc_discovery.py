#!/usr/bin/env python3
"""BSC narrative discovery via CMC category endpoint.

Queries CMC categories for AI / RWA / DePIN / Meme / Privacy, filters tokens
that have a BNB platform contract, and returns top-N per narrative ranked by
market cap. Used by the dashboard refresh to surface "BSC Top Movers" beyond
the curated 3-token static baskets in backtest.NARRATIVE_BASKETS.

This is DISCOVERY ONLY. Execution still uses NARRATIVE_BASKETS[*].bsc_addresses
because those addresses are manually verified.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

CMC_BASE = "https://pro-api.coinmarketcap.com"
TIMEOUT = 20

# Narrative → list of CMC category ids (multi-cat union, deduped by symbol)
NARRATIVE_CATS: dict[str, list[str]] = {
    "AI Tokens":     ["6051a81a66fc1b42617d6db7", "67250af2622a021a2592cba5"],   # AI & Big Data + AI Agents
    "RWA":           ["6400b58c1701313dc2e853a9", "68638d58358e0763b448b3ca"],   # RWA Protocols + Tokenized Assets
    "DePIN":         ["65f23191e6c934565751ce16"],                                # DePIN
    "Meme":          ["6051a82566fc1b42617d6dc6", "60bdcb4acd44627a464e36c5"],   # Memes + Doggone Doggerel
    "Privacy":       ["604f273debccdd50cd175fb0", "692b0302c0b341673d681a27"],   # Privacy + Privacy Coins
    "Binance Alpha": ["6762acaeb5d1b043d3342f44"],                                # Binance Alpha
    "Four.Meme":     ["67c97fa33b601d44b3562b52"],                                # Four.Meme Ecosystem
    "AI Agents":     ["67250af2622a021a2592cba5", "67755b776bd44718911c2570"],   # AI Agents + AI Agent Launchpad
    "DeFAI":         ["677d0fc06bd44718911d7781"],                                # DeFAI
}

# Filter to keep dust out of the dashboard
MIN_MCAP_USD = 1_000_000
MIN_VOL_24H_USD = 100_000
TOP_N = 10


def _get(path: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    url = f"{CMC_BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"X-CMC_PRO_API_KEY": api_key, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def fetch_bsc_tokens(cat_id: str, api_key: str) -> list[dict[str, Any]]:
    data = _get(
        "/v1/cryptocurrency/category",
        {"id": cat_id, "start": 1, "limit": 500},
        api_key,
    )
    coins = data.get("data", {}).get("coins", []) or []
    out: list[dict[str, Any]] = []
    for c in coins:
        platform = c.get("platform") or {}
        if platform.get("symbol") != "BNB":
            continue
        addr = platform.get("token_address")
        if not addr:
            continue
        q = (c.get("quote") or {}).get("USD") or {}
        mcap = q.get("market_cap") or 0
        vol = q.get("volume_24h") or 0
        if mcap < MIN_MCAP_USD or vol < MIN_VOL_24H_USD:
            continue
        out.append({
            "symbol": c.get("symbol", "?"),
            "name": c.get("name", ""),
            "address": addr,
            "cmc_rank": c.get("cmc_rank") or 0,
            "market_cap": mcap,
            "volume_24h": vol,
            "change_24h": q.get("percent_change_24h") or 0,
            "change_7d": q.get("percent_change_7d") or 0,
            "change_30d": q.get("percent_change_30d") or 0,
            "price": q.get("price") or 0,
        })
    return out


def fetch_narrative(narrative: str, cat_ids: list[str], api_key: str) -> list[dict[str, Any]]:
    """Union multiple categories, dedupe by address, sort by mcap, top N."""
    seen: dict[str, dict[str, Any]] = {}
    for cid in cat_ids:
        try:
            for tok in fetch_bsc_tokens(cid, api_key):
                addr = tok["address"].lower()
                if addr not in seen or tok["market_cap"] > seen[addr]["market_cap"]:
                    seen[addr] = tok
        except Exception as e:
            print(f"[discovery] {narrative} cat {cid} failed: {e}", file=sys.stderr)
    merged = sorted(seen.values(), key=lambda x: -x["market_cap"])
    return merged[:TOP_N]


def discover(api_key: str) -> dict[str, Any]:
    started = time.time()
    result: dict[str, Any] = {}
    errors: list[str] = []
    for narr, cat_ids in NARRATIVE_CATS.items():
        try:
            result[narr] = fetch_narrative(narr, cat_ids, api_key)
        except Exception as e:
            errors.append(f"{narr}: {e}")
            result[narr] = []
    return {
        "discovered_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - started, 2),
        "errors": errors,
        "narratives": result,
    }


def _load_env() -> dict[str, str]:
    env = os.environ.copy()
    f = Path("/home/ubuntu/bnb-hack-track2/.env")
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> int:
    env = _load_env()
    api_key = env.get("CMC_API_KEY")
    if not api_key:
        print("CMC_API_KEY missing", file=sys.stderr)
        return 2
    out = discover(api_key)
    out_path = Path("/home/ubuntu/nri-web/data/bsc_discovery.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"[discovery] wrote {out_path}")
    for narr, toks in out["narratives"].items():
        print(f"  {narr}: {len(toks)} BSC tokens")
    if out["errors"]:
        print("errors:", out["errors"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
