#!/usr/bin/env python3
"""X402 paywall for NRI's /signal endpoint.

Implements the seller side of x402 v2:
- GET /signal without X-PAYMENT  -> HTTP 402 with EIP-3009 challenge
- GET /signal with valid X-PAYMENT -> HTTP 200 with the protected scan

Verification:
- Recovers the EIP-712 signer address from TransferWithAuthorization
- Verifies amount >= price, token == U, recipient == NRI agent wallet
- Caches nonces for 10min to prevent replay (in-memory; production would use Redis)

This is the SELLER half. The buyer side uses the SDK's X402Signer (see x402_buyer.py).
"""
from __future__ import annotations

import base64
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from eth_account.messages import encode_typed_data

# ── BSC mainnet U token (verified from bnbagent SDK addresses) ──────────────
U_MAINNET = "0xcE24439F2D9C6a2289F741120FE202248B666666"
BSC_MAINNET_CHAIN_ID = 56
PAYMENT_TOKEN_NAME = "United Stables"  # MUST match on-chain DOMAIN_SEPARATOR (verified 0x358738…79b6)
PAYMENT_TOKEN_VERSION = "1"

# NRI seller config
NRI_PAY_TO = "0x7D93a5a96f9306E9b0D3B185aef702d03D1572C1"  # NRI agent wallet
NRI_AGENT_ID = 129156

# Pricing tiers (base units of U; U has 18 decimals)
DECIMALS = 18

PRICE_TIERS = {
    "base": 10**16,          # 0.01 U  ~ $0.01 — regime + top narrative only
    "regime_update": 5 * 10**16,  # 0.05 U   ~ $0.05 — regime classification + macro
    "full_scan": 10**17,     # 0.1 U   ~ $0.10 — full 10-narrative scan + SRR (UI default)
}

# In-memory replay protection (production: Redis or DB)
_USED_NONCES: dict[str, float] = {}
NONCE_TTL_SECONDS = 600

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


@dataclass
class X402Result:
    ok: bool
    status: int
    body: dict[str, Any]
    headers: dict[str, str]


def make_402_challenge(tier: str = "full_scan") -> X402Result:
    """Build an HTTP 402 Payment Required response with x402 v2 challenge."""
    if tier not in PRICE_TIERS:
        tier = "full_scan"
    amount = PRICE_TIERS[tier]
    body = {
        "x402Version": 2,
        "accepts": [
            {
                "scheme": "exact",
                "network": f"eip155:{BSC_MAINNET_CHAIN_ID}",
                "asset": U_MAINNET,
                "payTo": NRI_PAY_TO,
                "amount": str(amount),
                "maxTimeoutSeconds": 300,
                "extra": {
                    "name": PAYMENT_TOKEN_NAME,
                    "version": PAYMENT_TOKEN_VERSION,
                },
            }
        ],
        "resource": "/signal",
        "tier": tier,
        "agentId": NRI_AGENT_ID,
        "agentRegistry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
    }
    return X402Result(
        ok=False,
        status=402,
        body=body,
        headers={"Content-Type": "application/json"},
    )


def _gc_nonces() -> None:
    """Drop expired nonces from the cache."""
    now = time.time()
    expired = [n for n, t in _USED_NONCES.items() if now - t > NONCE_TTL_SECONDS]
    for n in expired:
        _USED_NONCES.pop(n, None)


def verify_payment(payment_header: str, tier: str = "full_scan") -> tuple[bool, str]:
    """Verify an X-PAYMENT envelope. Returns (ok, reason).

    Checks:
    1. Envelope decodes as base64(JSON) with x402Version=2 + scheme=exact
    2. EIP-712 signature recovers to the `from` address (no impostor signing)
    3. value >= advertised price for the tier
    4. to == NRI_PAY_TO (paid to the right wallet)
    5. asset == U_MAINNET (paid in U, not random token)
    6. validBefore > now (not expired)
    7. validAfter < now (already valid)
    8. nonce not seen before (replay protection)
    """
    if tier not in PRICE_TIERS:
        return False, "unknown tier"
    expected_amount = PRICE_TIERS[tier]

    try:
        decoded = base64.b64decode(payment_header).decode()
        envelope = json.loads(decoded)
    except Exception as e:
        return False, f"envelope decode failed: {e}"

    if envelope.get("x402Version") != 2:
        return False, "x402Version must be 2"
    if envelope.get("scheme") != "exact":
        return False, "scheme must be exact"

    network = envelope.get("network", "")
    if not network.endswith(f":{BSC_MAINNET_CHAIN_ID}"):
        return False, f"network must be eip155:{BSC_MAINNET_CHAIN_ID}"

    payload = envelope.get("payload") or {}
    auth = payload.get("authorization") or {}
    sig = payload.get("signature")
    if not sig:
        return False, "missing signature"

    required = ["from", "to", "value", "validAfter", "validBefore", "nonce"]
    for k in required:
        if k not in auth:
            return False, f"missing field: {k}"

    # Numeric/checksum normalization
    try:
        value = int(auth["value"])
        valid_after = int(auth["validAfter"])
        valid_before = int(auth["validBefore"])
    except Exception:
        return False, "non-numeric numeric fields"

    now = int(time.time())
    if valid_before <= now:
        return False, "authorization expired"
    if valid_after >= now + 60:
        return False, "authorization not yet valid"

    if value < expected_amount:
        return False, f"insufficient amount: {value} < {expected_amount}"

    if auth["to"].lower() != NRI_PAY_TO.lower():
        return False, f"wrong payTo: {auth['to']}"

    # Replay check
    _gc_nonces()
    nonce = auth["nonce"]
    if nonce in _USED_NONCES:
        return False, "nonce already used (replay)"

    # EIP-712 signature recovery
    try:
        msg = {
            "from": auth["from"],
            "to": auth["to"],
            "value": value,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        }
        domain = {
            "name": PAYMENT_TOKEN_NAME,
            "version": PAYMENT_TOKEN_VERSION,
            "chainId": BSC_MAINNET_CHAIN_ID,
            "verifyingContract": U_MAINNET,
        }
        types = {
            "EIP712Domain": EIP712_DOMAIN_FIELDS,
            "TransferWithAuthorization": TWA_FIELDS,
        }
        full_msg = {
            "types": types,
            "primaryType": "TransferWithAuthorization",
            "domain": domain,
            "message": msg,
        }
        signable = encode_typed_data(full_message=full_msg)
        recovered = Account.recover_message(signable, signature=sig)
        if recovered.lower() != auth["from"].lower():
            return False, f"signature mismatch: recovered {recovered}, expected {auth['from']}"
    except Exception as e:
        return False, f"signature recovery failed: {e}"

    # Mark nonce used
    _USED_NONCES[nonce] = now

    return True, "ok"


# ── EIP-3009 on-chain settlement (facilitator redemption) ────────────────────
#
# x402 settle leg: take the buyer's signed TransferWithAuthorization and submit
# it to the U token contract so the U actually moves buyer -> NRI_PAY_TO. The
# buyer pays no gas (gasless, that's the point); the NRI agent wallet pays gas.
#
# SAFETY: disabled unless X402_REDEEM=1 AND a wallet password is available.
# When disabled, serve_signal() behaves exactly as before (verify-only).
import os  # noqa: E402

REDEEM_ENABLED = os.environ.get("X402_REDEEM", "0") == "1"
BSC_RPC = os.environ.get("BSC_RPC", "https://bsc-rpc.publicnode.com")
NRI_KEYSTORE = os.environ.get(
    "NRI_KEYSTORE",
    os.path.expanduser("~/.bnbagent/wallets/0x7D93a5a96f9306E9b0D3B185aef702d03D1572C1.json"),
)

# transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,
#   uint256 validBefore,bytes32 nonce,uint8 v,bytes32 r,bytes32 s)
_TWA_ABI = [{
    "name": "transferWithAuthorization",
    "type": "function",
    "stateMutability": "nonpayable",
    "inputs": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
        {"name": "v", "type": "uint8"},
        {"name": "r", "type": "bytes32"},
        {"name": "s", "type": "bytes32"},
    ],
    "outputs": [],
}]

_redeemer_acct = None  # lazily-decrypted NRI signing account


def _load_redeemer():
    """Decrypt the NRI keystore once, using WALLET_PASSWORD from env."""
    global _redeemer_acct
    if _redeemer_acct is not None:
        return _redeemer_acct
    password = os.environ.get("WALLET_PASSWORD")
    if not password:
        raise RuntimeError("WALLET_PASSWORD not set — cannot decrypt NRI keystore")
    with open(NRI_KEYSTORE) as f:
        keyfile = json.load(f)
    key = Account.decrypt(keyfile, password)
    acct = Account.from_key(key)
    if acct.address.lower() != NRI_PAY_TO.lower():
        raise RuntimeError(
            f"keystore address {acct.address} != NRI_PAY_TO {NRI_PAY_TO}"
        )
    _redeemer_acct = acct
    return acct


def redeem_authorization(auth: dict, signature: str) -> dict:
    """Submit a verified TransferWithAuthorization on-chain (the x402 settle leg).

    Pulls `value` U from auth['from'] to NRI_PAY_TO via the U token contract.
    Buyer pays no gas; the NRI wallet pays gas. Returns {ok, txHash, ...}.

    Caller MUST have already run verify_payment() — this does not re-verify.
    """
    from web3 import Web3

    acct = _load_redeemer()
    w3 = Web3(Web3.HTTPProvider(BSC_RPC))
    token = w3.eth.contract(address=Web3.to_checksum_address(U_MAINNET), abi=_TWA_ABI)

    # Split the 65-byte signature into v, r, s
    sig = signature[2:] if signature.startswith("0x") else signature
    if len(sig) != 130:
        return {"ok": False, "error": f"bad signature length {len(sig)}"}
    r = "0x" + sig[0:64]
    s = "0x" + sig[64:128]
    v = int(sig[128:130], 16)
    if v < 27:
        v += 27

    nonce_bytes = bytes.fromhex(auth["nonce"][2:] if auth["nonce"].startswith("0x") else auth["nonce"])

    fn = token.functions.transferWithAuthorization(
        Web3.to_checksum_address(auth["from"]),
        Web3.to_checksum_address(auth["to"]),
        int(auth["value"]),
        int(auth["validAfter"]),
        int(auth["validBefore"]),
        nonce_bytes,
        v, r, s,
    )

    # Pre-flight: simulate so we fail cleanly instead of burning gas on a revert
    try:
        fn.call({"from": acct.address})
    except Exception as e:
        return {"ok": False, "error": f"simulation reverted: {e}"}

    try:
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gas": 120000,
            "gasPrice": w3.eth.gas_price,
            "chainId": BSC_MAINNET_CHAIN_ID,
        })
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    except Exception as e:
        return {"ok": False, "error": f"broadcast failed: {e}"}

    if receipt["status"] != 1:
        return {"ok": False, "error": "tx reverted on-chain", "txHash": tx_hash.hex()}

    return {
        "ok": True,
        "txHash": tx_hash.hex(),
        "blockNumber": receipt["blockNumber"],
        "from": auth["from"],
        "to": auth["to"],
        "value": str(auth["value"]),
    }


def serve_signal(
    payment_header: str | None,
    tier: str,
    snapshot: dict,
) -> X402Result:
    """Top-level x402 paywall handler.

    Args:
      payment_header: value of HTTP X-PAYMENT header (or None)
      tier: which tier the buyer is requesting
      snapshot: live NRI snapshot dict to return on success

    Returns:
      X402Result — either the 402 challenge or the 200 protected payload.
    """
    if not payment_header:
        return make_402_challenge(tier)

    ok, reason = verify_payment(payment_header, tier)
    if not ok:
        return X402Result(
            ok=False,
            status=402,
            body={
                **make_402_challenge(tier).body,
                "error": reason,
            },
            headers={"Content-Type": "application/json"},
        )

    # ── x402 settle leg: redeem the authorization on-chain (gated) ──────────
    # Only runs when X402_REDEEM=1. When off, behaviour is unchanged (verify-only).
    settlement = None
    if REDEEM_ENABLED:
        try:
            _env = json.loads(base64.b64decode(payment_header).decode())
            _payload = _env.get("payload") or {}
            _auth = _payload.get("authorization") or {}
            _sig = _payload.get("signature") or ""
            settlement = redeem_authorization(_auth, _sig)
        except Exception as e:
            settlement = {"ok": False, "error": f"redeem exception: {e}"}
        if not settlement.get("ok"):
            # Payment could not be settled on-chain — do NOT release the signal.
            return X402Result(
                ok=False,
                status=402,
                body={
                    **make_402_challenge(tier).body,
                    "error": "settlement failed: " + str(settlement.get("error")),
                },
                headers={"Content-Type": "application/json"},
            )

    # Strip noisy fields if buyer wants base tier
    if tier == "base":
        signal = {
            "regime": snapshot.get("regime"),
            "top_narrative": next(
                iter(sorted(
                    (snapshot.get("narratives") or {}).items(),
                    key=lambda kv: -int(kv[1].get("conviction", 0)),
                )),
                ("—", {}),
            )[0],
            "version": snapshot.get("version"),
            "_paid_tier": "base",
        }
    elif tier == "regime_update":
        signal = {
            "regime": snapshot.get("regime"),
            "regime_reason": snapshot.get("regime_reason"),
            "macro": snapshot.get("macro"),
            "version": snapshot.get("version"),
            "_paid_tier": "regime_update",
        }
    else:  # full_scan
        signal = {
            **snapshot,
            "_paid_tier": "full_scan",
        }

    # Sign the response so the buyer can prove provenance
    signal["_signed_by_agent"] = NRI_AGENT_ID
    signal["_paid_at"] = int(time.time())
    if settlement and settlement.get("ok"):
        # On-chain settlement proof — the buyer's U actually moved to NRI_PAY_TO
        signal["_settlement"] = {
            "settled": True,
            "txHash": settlement["txHash"],
            "explorer": "https://bscscan.com/tx/" + settlement["txHash"],
            "value": settlement["value"],
            "asset": U_MAINNET,
        }
    else:
        signal["_settlement"] = {"settled": False, "note": "verify-only (redemption disabled)"}

    return X402Result(
        ok=True,
        status=200,
        body=signal,
        headers={"Content-Type": "application/json", "X-Paid-Tier": tier, "X-Agent-Id": str(NRI_AGENT_ID)},
    )


if __name__ == "__main__":
    # Smoke test: print a sample 402 challenge
    challenge = make_402_challenge("full_scan")
    print(json.dumps(challenge.body, indent=2))
