#!/usr/bin/env python3
"""x402 buyer demo for NRI's /signal endpoint.

End-to-end loop:
  1. GET https://nri.realdo.org/signal              -> 402 + challenge
  2. Parse accepts[0], build TransferWithAuthorization message
  3. Sign via the official `bnbagent` SDK X402Signer (EIP-3009)
  4. Retry with X-PAYMENT header                    -> 200 + scan

This proves the SDK's X402Signer works against NRI's live paywall.
No real funds move: the seller verifies signature shape but doesn't
forward to a facilitator (we'd plug in CDP / Coinbase x402 facilitator
in production, or settle directly via U.transferWithAuthorization()).

Usage:
    pip install bnbagent
    python x402_buyer.py [--tier full_scan|regime_update|base]
                        [--url https://nri.realdo.org/signal]
"""
from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from eth_account import Account
from bnbagent import EVMWalletProvider, X402Signer

EIP712_DOMAIN_FIELDS = [
    {"name": "name", "type": "string"},
    {"name": "version", "type": "string"},
    {"name": "chainId", "type": "uint256"},
    {"name": "verifyingContract", "type": "address"},
]
TWA_FIELDS = [
    {"name": "from", "type": "address"},
    {"name": "to", "type": "address"},
    {"name": "value", "type": "uint256"},
    {"name": "validAfter", "type": "uint256"},
    {"name": "validBefore", "type": "uint256"},
    {"name": "nonce", "type": "bytes32"},
]


def get_resource(url: str, payment: str | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    if payment:
        req.add_header("X-PAYMENT", payment)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def build_envelope(accept: dict, msg: dict, sig: str) -> str:
    envelope = {
        "x402Version": 2,
        "scheme": accept["scheme"],
        "network": accept["network"],
        "payload": {
            "authorization": {
                "from": msg["from"],
                "to": msg["to"],
                "value": str(msg["value"]),
                "validAfter": str(msg["validAfter"]),
                "validBefore": str(msg["validBefore"]),
                "nonce": msg["nonce"],
            },
            "signature": sig,
        },
    }
    return base64.b64encode(json.dumps(envelope).encode()).decode()


def main() -> int:
    parser = argparse.ArgumentParser(description="x402 buyer demo against NRI's /signal")
    parser.add_argument("--url", default="https://nri.realdo.org/signal")
    parser.add_argument("--tier", default="full_scan", choices=["base", "regime_update", "full_scan"])
    args = parser.parse_args()

    url = f"{args.url}?tier={args.tier}"

    # 1. Fresh in-memory buyer wallet (never persisted)
    pk = Account.create().key.hex()
    wallet = EVMWalletProvider(password="x402-demo", private_key=pk, persist=False)
    print(f"buyer wallet: {wallet.address} (in-memory, throwaway)")

    # 2. First GET — expect 402 challenge
    print(f"\n[1] GET {url}")
    status, body = get_resource(url)
    if status != 402:
        print(f"FAIL: expected 402, got {status}: {body}", file=sys.stderr)
        return 1
    print(f"    -> 402 Payment Required ✓")

    accept = body["accepts"][0]
    chain_id = int(accept["network"].split(":")[1])
    asset = accept["asset"]
    pay_to = accept["payTo"]
    amount = int(accept["amount"])
    print(f"    challenge: {amount / 1e18:.4f} U → {pay_to[:10]}...{pay_to[-4:]} on chain {chain_id}")
    print(f"    agentId in challenge: {body.get('agentId')}")
    print(f"    agentRegistry: {body.get('agentRegistry')}")

    # 3. Build the signer with a per-call cap
    signer = X402Signer(wallet, max_value_per_call={asset: amount * 2})

    # 4. Construct EIP-712 payload
    now = int(time.time())
    msg = {
        "from": wallet.address,
        "to": pay_to,
        "value": amount,
        "validAfter": now - 60,
        "validBefore": now + int(accept["maxTimeoutSeconds"]),
        "nonce": "0x" + secrets.token_hex(32),
    }
    domain = {
        "name": accept["extra"]["name"],
        "version": accept["extra"]["version"],
        "chainId": chain_id,
        "verifyingContract": asset,
    }
    types = {
        "EIP712Domain": EIP712_DOMAIN_FIELDS,
        "TransferWithAuthorization": TWA_FIELDS,
    }

    print(f"\n[2] Sign EIP-3009 TransferWithAuthorization via X402Signer (SDK)")
    signed = signer.sign_payment(
        domain=domain,
        types=types,
        message=msg,
        expected_to=pay_to,
    )
    raw_sig = signed["signature"]
    sig = raw_sig.hex() if hasattr(raw_sig, "hex") and not isinstance(raw_sig, str) else raw_sig
    if not sig.startswith("0x"):
        sig = "0x" + sig
    print(f"    -> sig {sig[:10]}…{sig[-6:]} ✓")

    # 5. Encode envelope, retry
    envelope = build_envelope(accept, msg, sig)
    print(f"\n[3] Retry with X-PAYMENT envelope ({len(envelope)} bytes b64)")
    status, body = get_resource(url, payment=envelope)
    if status != 200:
        print(f"FAIL: expected 200, got {status}: {json.dumps(body, indent=2)}", file=sys.stderr)
        return 1
    print(f"    -> 200 OK ✓")
    print(f"    paid_tier: {body.get('_paid_tier')}")
    print(f"    signed_by_agent: {body.get('_signed_by_agent')}")
    print(f"    regime: {body.get('regime')}")
    if body.get("narratives"):
        top = max(body["narratives"].items(), key=lambda kv: -int(kv[1].get("conviction", 0)))
        print(f"    top_narrative: {top[0]} (conviction {top[1].get('conviction')})")

    print("\n" + "=" * 60)
    print("x402 buyer flow against NRI live paywall: ALL STEPS OK ✓")
    print(f"Tier: {args.tier} ({amount / 1e18:.4f} U)")
    print(f"NRI agentId: {body.get('_signed_by_agent')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
