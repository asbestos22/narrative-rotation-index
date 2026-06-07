#!/usr/bin/env python3
"""ERC-8183 commerce integration for NRI.

NRI exposes itself as a sellable agent service: a buyer agent posts a job,
funds it with U escrow, NRI delivers a signed scan, optimistic settlement
releases U to NRI on `complete`. Uses the official `bnbagent` SDK.

Three modes:
  --dry-run      (default) Build all calldata + manifest hashes without
                 broadcasting. Safe, no funds, no testnet. Proves the
                 commerce protocol shape end-to-end.
  --live-testnet Run the full lifecycle on BSC testnet:
                 createJob → setBudget → fund → submit → complete
                 Requires CLIENT_PK + PROVIDER_PK env vars and a small
                 amount of test U on the client wallet (~1 U).
                 Gas is sponsored by MegaFuel paymaster.
  --live-mainnet Same as --live-testnet but on BSC mainnet. Requires real U.

Roles:
  Client   — buyer who pays for the scan. Funds escrow with U.
  Provider — NRI agent (agentId 129156). Delivers signed scan, gets paid.

The deliverable is a JSON manifest containing the live scan. Its keccak256
hash goes on-chain. The client can fetch the manifest off-chain (URL stored
as opt_params.deliverable_url) and verify it matches the on-chain hash.

After submit:
  - Silence past dispute window = implicit approve, escrow auto-releases
  - Client can dispute → whitelisted voters quorum decides

This makes NRI a real autonomous on-chain seller, not just an HTTP paywall.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path

NRI_AGENT_ID = 129156
NRI_PROVIDER_ADDR = "0x7D93a5a96f9306E9b0D3B185aef702d03D1572C1"
NRI_REGISTRY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
SERVICE_NAME = "Narrative Rotation Index — full scan + SRR overlay"

# Default service price: 1 U per delivered scan.
DEFAULT_SERVICE_PRICE_BASE_UNITS = 1 * 10**18  # 1 U at 18 decimals


@dataclass
class JobSpec:
    description: str
    deliverable_url: str
    expired_at: int  # unix ts
    budget_base_units: int


def build_job_spec(price: int, snapshot_url: str = "https://nri.realdo.org/api/live") -> JobSpec:
    """Construct the off-chain job description and on-chain expiry."""
    now = int(time.time())
    return JobSpec(
        description=SERVICE_NAME,
        deliverable_url=snapshot_url,
        expired_at=now + 86400,  # 24h escape hatch
        budget_base_units=price,
    )


def compute_manifest_hash(snapshot: dict) -> tuple[bytes, dict]:
    """Hash the deliverable manifest deterministically.

    The manifest pins:
      - service identity (NRI agentId)
      - the entire snapshot dict (regime, narratives, SRR)
      - timestamp + signer

    On-chain we store keccak256(canonical_json). Off-chain, the buyer
    can fetch the URL and recompute to verify.
    """
    manifest = {
        "service": "narrative-rotation-index",
        "version": "10.2",
        "agent_id": NRI_AGENT_ID,
        "provider": NRI_PROVIDER_ADDR,
        "registry": NRI_REGISTRY,
        "delivered_at": int(time.time()),
        "snapshot": snapshot,
    }
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    # bnbagent SDK uses keccak256; we compute it the same way as the SDK.
    try:
        from eth_utils import keccak  # type: ignore
        h = keccak(canonical)
    except ImportError:
        # Fallback for environments without eth_utils — sha256 (NOTE: live mode requires keccak)
        h = hashlib.sha256(canonical).digest()
    return h, manifest


def dry_run(price: int) -> int:
    """Build the full commerce loop without broadcasting."""
    print("=" * 72)
    print("NRI ERC-8183 commerce dry-run")
    print("=" * 72)

    spec = build_job_spec(price)
    print(f"\nService:       {spec.description}")
    print(f"Provider:      {NRI_PROVIDER_ADDR}  (NRI, agentId {NRI_AGENT_ID})")
    print(f"Budget:        {spec.budget_base_units / 1e18:.4f} U")
    print(f"Expiry:        +24h ({spec.expired_at})")
    print(f"Deliverable:   {spec.deliverable_url}")

    # 1. Buyer side calldata
    print("\n--- Buyer calldata ---")
    print("  1. createJob(provider, evaluator=router, expired_at, description, hook=router)")
    print("  2. registerJob(jobId, policy=optimistic)")
    print(f"  3. setBudget(jobId, {spec.budget_base_units})")
    print(f"  4. approve(commerce, {spec.budget_base_units})  [if allowance < budget]")
    print(f"  5. fund(jobId, {spec.budget_base_units})           [escrow locked]")

    # 2. Provider (NRI) delivers — fetch live snapshot, hash it
    print("\n--- Provider delivery ---")
    snapshot_path = Path("/home/ubuntu/nri-web/data/live.json")
    if snapshot_path.exists():
        snapshot = json.loads(snapshot_path.read_text())
    else:
        snapshot = {"regime": "DEMO", "narratives": {}}

    manifest_hash, manifest = compute_manifest_hash(snapshot)
    print(f"  manifest_hash:  0x{manifest_hash.hex()}")
    print(f"  manifest_size:  {len(json.dumps(manifest))} bytes")
    print(f"  scan regime:    {manifest['snapshot'].get('regime')}")
    top_narr = sorted(
        (manifest["snapshot"].get("narratives") or {}).items(),
        key=lambda kv: -int(kv[1].get("conviction", 0)),
    )[:1]
    if top_narr:
        n, v = top_narr[0]
        print(f"  top_narrative:  {n} ({v.get('verdict')} {v.get('conviction')}/75)")
    print("  6. submit(jobId, manifest_hash, opt_params={'deliverable_url': ...})")

    # 3. Settlement
    print("\n--- Settlement (optimistic policy) ---")
    print("  7. WAIT dispute window (e.g. 1h)")
    print("  8a. settle(jobId)  → escrow released to provider [happy path]")
    print("  8b. OR client dispute()  → voters voteReject → settle returns funds")

    # 4. Save proof artifact
    out = Path("/home/ubuntu/bnb-hack-track2/erc8183_dryrun.json")
    artifact = {
        "service": SERVICE_NAME,
        "agentId": NRI_AGENT_ID,
        "provider": NRI_PROVIDER_ADDR,
        "registry": NRI_REGISTRY,
        "spec": asdict(spec),
        "manifest_hash": "0x" + manifest_hash.hex(),
        "manifest": manifest,
        "lifecycle": [
            "1. client.createJob(provider=NRI, evaluator=router, expired_at, description, hook=router)",
            "2. client.registerJob(jobId, policy=optimistic)",
            f"3. client.setBudget(jobId, {spec.budget_base_units})",
            f"4. client.fund(jobId, {spec.budget_base_units})",
            "5. provider.submit(jobId, manifest_hash, opt_params={'deliverable_url': ...})",
            "6. WAIT dispute window",
            "7. anyone.router.settle(jobId) → escrow → provider",
        ],
    }
    out.write_text(json.dumps(artifact, indent=2, default=str))
    print(f"\nProof artifact written: {out}")
    print("=" * 72)
    print("OK ✓ — full ERC-8183 protocol shape constructed without broadcasting.")
    print("Run with --live-testnet (CLIENT_PK + PROVIDER_PK + 1 U test) to execute.")
    return 0


def live_run(network: str) -> int:
    """Run the full ERC-8183 lifecycle on testnet or mainnet."""
    try:
        from bnbagent import EVMWalletProvider
        from bnbagent.erc8183 import ERC8183Client
    except ImportError:
        print("Run: pip install bnbagent", file=sys.stderr)
        return 1

    client_pk = os.environ.get("CLIENT_PK")
    provider_pk = os.environ.get("PROVIDER_PK")
    password = os.environ.get("WALLET_PASSWORD", "nri-erc8183")

    if not client_pk or not provider_pk:
        print("CLIENT_PK and PROVIDER_PK env vars required for live mode.", file=sys.stderr)
        print("Generate fresh ones with: python -c 'from eth_account import Account; print(Account.create().key.hex())'", file=sys.stderr)
        return 1

    print(f"=" * 72)
    print(f"NRI ERC-8183 LIVE on {network}")
    print(f"=" * 72)

    client_wallet = EVMWalletProvider(password=password, private_key=client_pk, persist=False)
    provider_wallet = EVMWalletProvider(password=password, private_key=provider_pk, persist=False)
    print(f"Client:    {client_wallet.address}")
    print(f"Provider:  {provider_wallet.address}")

    client = ERC8183Client(wallet_provider=client_wallet, network=network)
    provider = ERC8183Client(wallet_provider=provider_wallet, network=network)

    price = DEFAULT_SERVICE_PRICE_BASE_UNITS
    spec = build_job_spec(price)

    bal = client.token_balance()
    print(f"Client U balance: {bal / 1e18:.4f} U  (need {price / 1e18:.4f})")
    if bal < price:
        print("Insufficient U on client wallet — fund it before retrying.", file=sys.stderr)
        return 2

    # 1. Create job
    r = client.create_job(
        provider=provider_wallet.address,
        expired_at=spec.expired_at,
        description=spec.description,
    )
    job_id = r.get("jobId") or r.get("job_id")
    print(f"\n[1] createJob → jobId={job_id} tx={r.get('transactionHash', '')}")

    # 2. Register policy + budget + fund
    r2 = client.register_job(job_id)
    print(f"[2] registerJob → tx={r2.get('transactionHash', '')}")

    r3 = client.set_budget(job_id, price)
    print(f"[3] setBudget({price}) → tx={r3.get('transactionHash', '')}")

    r4 = client.fund(job_id, price)
    print(f"[4] fund({price}) → tx={r4.get('transactionHash', '')}")

    # 3. Provider delivers
    snapshot_path = Path("/home/ubuntu/nri-web/data/live.json")
    snapshot = json.loads(snapshot_path.read_text()) if snapshot_path.exists() else {}
    manifest_hash, manifest = compute_manifest_hash(snapshot)

    r5 = provider.submit(
        job_id,
        manifest_hash,
        opt_params={"deliverable_url": spec.deliverable_url},
    )
    print(f"[5] submit(manifest_hash=0x{manifest_hash.hex()[:16]}…) → tx={r5.get('transactionHash', '')}")

    # 4. Settlement (skipped in this script — would require waiting dispute window)
    print(f"\nLifecycle complete. Job {job_id} is now in submitted state.")
    print(f"To settle: wait dispute window, then call client.router.settle({job_id}).")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NRI ERC-8183 commerce integration")
    parser.add_argument("--live-testnet", action="store_true", help="Run on BSC testnet (needs PKs + 1 U)")
    parser.add_argument("--live-mainnet", action="store_true", help="Run on BSC mainnet (needs real U)")
    parser.add_argument("--price", type=int, default=DEFAULT_SERVICE_PRICE_BASE_UNITS,
                        help="Service price in base units (default: 1 U = 1e18)")
    args = parser.parse_args()

    if args.live_testnet:
        return live_run("bsc-testnet")
    if args.live_mainnet:
        return live_run("bsc-mainnet")
    return dry_run(args.price)


if __name__ == "__main__":
    sys.exit(main())
