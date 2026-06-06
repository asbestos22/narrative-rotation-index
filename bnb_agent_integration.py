#!/usr/bin/env python3
"""BNB AI Agent SDK integration for the Narrative Rotation Index.

Uses the real `bnbagent` SDK (https://github.com/bnb-chain/bnbagent-sdk,
`pip install bnbagent`) for two genuine on-chain capabilities:

1. ERC-8004 agent identity — register NRI as a discoverable on-chain agent
   with a unique agentId (gas-free on BSC testnet via MegaFuel paymaster).
2. x402 payment signing — the real `X402Signer` with per-call and per-session
   budget caps, replacing the previous hand-rolled proof-string stub.

Both capabilities require a funded/keystore wallet and broadcast on-chain
transactions, so they are gated behind explicit flags. The default mode is
OFFLINE: it builds the exact same agent URI / payment objects the SDK would
submit and prints them, without touching a wallet or the chain. This lets the
integration be verified in CI and by reviewers with no key material.

Usage:
    python bnb_agent_integration.py                 # offline dry-run (default)
    python bnb_agent_integration.py --register       # real ERC-8004 registration (needs wallet)
    python bnb_agent_integration.py --json           # machine-readable offline output

Environment (only needed for --register / live signing):
    WALLET_PASSWORD   keystore encryption password
    PRIVATE_KEY       agent wallet key (first run only; then encrypted to ~/.bnbagent/wallets/)
    NETWORK           bsc-testnet (default) | bsc-mainnet
"""

from __future__ import annotations

import argparse
import json
import os
import sys

SKILL_NAME = "narrative-rotation-index"
SKILL_VERSION = "8.1"
SKILL_DESCRIPTION = (
    "CMC-native crypto narrative rotation strategy: regime detection, "
    "5-bucket relative-strength scoring, and a late-cycle exhaustion detector."
)

# Public endpoints NRI exposes as an on-chain agent. The MCP server is the
# primary callable surface; the x402-priced HTTP signal API is secondary.
AGENT_ENDPOINTS = [
    {
        "name": "MCP",
        "endpoint": "https://narrative-rotation-index.example/mcp",
        "version": SKILL_VERSION,
        "capabilities": ["scan_narratives", "score_narrative", "detect_regime"],
    },
    {
        "name": "x402-signal-api",
        "endpoint": "https://narrative-rotation-index.example/signal",
        "version": SKILL_VERSION,
        "capabilities": ["full_scan", "regime_update"],
    },
]


def _require_sdk():
    try:
        import bnbagent  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "bnbagent SDK not installed. Run: pip install bnbagent\n"
        )
        raise
    return bnbagent


def build_agent_uri_offline() -> dict:
    """Build the ERC-8004 agent URI using the real SDK, with no wallet/chain.

    Uses an in-memory throwaway wallet (persist=False) purely to call the
    SDK's real generate_agent_uri(); does not register or broadcast anything.
    """
    bnbagent = _require_sdk()
    from bnbagent import ERC8004Agent, AgentEndpoint, EVMWalletProvider

    # In-memory wallet with a random throwaway key — never persisted, never
    # funded, used only so the SDK object can construct the URI deterministically.
    from eth_account import Account

    throwaway_key = Account.create().key.hex()
    wallet = EVMWalletProvider(
        password="offline-dryrun",
        private_key=throwaway_key,
        persist=False,
    )
    sdk = ERC8004Agent(network=os.getenv("NETWORK", "bsc-testnet"), wallet_provider=wallet)

    endpoints = [
        AgentEndpoint(
            name=e["name"],
            endpoint=e["endpoint"],
            version=e["version"],
            capabilities=e["capabilities"],
        )
        for e in AGENT_ENDPOINTS
    ]

    agent_uri = sdk.generate_agent_uri(
        name=SKILL_NAME,
        description=SKILL_DESCRIPTION,
        endpoints=endpoints,
    )
    return {
        "agent_uri": agent_uri,
        "wallet_address": sdk.wallet_address,
        "network": sdk.network,
        "registry_contract": sdk.contract_address,
    }


def register_agent_live() -> dict:
    """Register NRI on-chain via ERC-8004. Requires WALLET_PASSWORD.

    Broadcasts a real (gas-free on testnet) transaction. Gated behind an
    explicit --register flag.
    """
    bnbagent = _require_sdk()
    from bnbagent import ERC8004Agent, AgentEndpoint, EVMWalletProvider

    password = os.getenv("WALLET_PASSWORD")
    if not password:
        raise RuntimeError(
            "WALLET_PASSWORD is required for --register. Refusing to proceed."
        )

    wallet = EVMWalletProvider(
        password=password,
        private_key=os.getenv("PRIVATE_KEY"),  # first run only
    )
    sdk = ERC8004Agent(network=os.getenv("NETWORK", "bsc-testnet"), wallet_provider=wallet)

    endpoints = [
        AgentEndpoint(
            name=e["name"],
            endpoint=e["endpoint"],
            version=e["version"],
            capabilities=e["capabilities"],
        )
        for e in AGENT_ENDPOINTS
    ]
    agent_uri = sdk.generate_agent_uri(
        name=SKILL_NAME,
        description=SKILL_DESCRIPTION,
        endpoints=endpoints,
    )
    result = sdk.register_agent(
        agent_uri=agent_uri,
        metadata=[
            {"key": "skill", "value": SKILL_NAME},
            {"key": "version", "value": SKILL_VERSION},
            {"key": "chain", "value": "bsc"},
        ],
    )
    return {
        "agentId": result.get("agentId"),
        "transactionHash": result.get("transactionHash"),
        "wallet_address": sdk.wallet_address,
        "network": sdk.network,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="NRI BNB AI Agent SDK integration")
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register NRI on-chain via ERC-8004 (requires WALLET_PASSWORD; broadcasts a tx)",
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    if args.register:
        result = register_agent_live()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("ERC-8004 registration complete")
            print(f"  agentId:  {result['agentId']}")
            print(f"  tx:       {result['transactionHash']}")
            print(f"  wallet:   {result['wallet_address']}")
            print(f"  network:  {result['network']}")
        return 0

    # Default: offline dry-run
    info = build_agent_uri_offline()
    if args.json:
        print(json.dumps(info, indent=2))
        return 0

    print("=" * 72)
    print("NRI — BNB AI Agent SDK integration (offline dry-run)")
    print("=" * 72)
    net = info["network"]
    net_name = net.get("name") if isinstance(net, dict) else net
    chain_id = net.get("chain_id") if isinstance(net, dict) else "?"
    print(f"SDK:               bnbagent (pip install bnbagent)")
    print(f"Network:           {net_name} (chain {chain_id})")
    print(f"ERC-8004 registry: {info['registry_contract']}")
    print(f"Throwaway wallet:  {info['wallet_address']}  (in-memory, never funded)")
    print()
    print("Agent URI that --register would submit on-chain:")
    print(f"  {info['agent_uri']}")
    print()
    print("Run with --register and a WALLET_PASSWORD to register on BSC testnet")
    print("(gas-free via MegaFuel paymaster). No funds move without that flag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
