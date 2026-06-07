#!/usr/bin/env python3
"""Refresh NRI live snapshot.

Runs live_demo.py against CMC API, writes JSON to /home/ubuntu/nri-web/data/live.json.
On failure, falls back to cached sample so the dashboard never goes blank.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path("/home/ubuntu/bnb-hack-track2")
WEB = Path("/home/ubuntu/nri-web")
DATA = WEB / "data"
LIVE = DATA / "live.json"
SAMPLE = REPO / "sample_live_output.json"
ENV_FILE = REPO / ".env"


def load_env() -> dict[str, str]:
    env = os.environ.copy()
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    env = load_env()
    py = sys.executable
    cmd = [py, str(REPO / "live_demo.py"), "--json"]
    started = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        print("[refresh] live_demo.py timed out, keeping previous snapshot", file=sys.stderr)
        return 2

    elapsed = time.time() - started

    if result.returncode != 0 or not result.stdout.strip():
        print(f"[refresh] live_demo failed rc={result.returncode} in {elapsed:.1f}s", file=sys.stderr)
        print(result.stderr[-500:], file=sys.stderr)
        if not LIVE.exists() and SAMPLE.exists():
            shutil.copy(SAMPLE, LIVE)
            print("[refresh] seeded with cached sample", file=sys.stderr)
        return 1

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # live_demo prints a banner + JSON. Try to find the JSON body.
        text = result.stdout
        start = text.find("{")
        if start == -1:
            print("[refresh] no JSON in output", file=sys.stderr)
            return 1
        try:
            payload = json.loads(text[start:])
        except json.JSONDecodeError as e:
            print(f"[refresh] JSON parse failed: {e}", file=sys.stderr)
            return 1

    payload["_refreshed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload["_refresh_elapsed_s"] = round(elapsed, 2)

    # Layer in BSC narrative discovery (top BSC-resident tokens per narrative).
    # Discovery is best-effort — if it fails we still write the core snapshot.
    try:
        bsc_path = Path("/home/ubuntu/nri-web/bsc_discovery.py")
        result_d = subprocess.run(
            [py, str(bsc_path)],
            cwd=str(WEB),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        disc_file = WEB / "data" / "bsc_discovery.json"
        if disc_file.exists():
            payload["bsc_discovery"] = json.loads(disc_file.read_text())
        elif result_d.returncode != 0:
            print(f"[refresh] discovery rc={result_d.returncode}: {result_d.stderr[-200:]}", file=sys.stderr)
    except Exception as e:
        print(f"[refresh] discovery skipped: {e}", file=sys.stderr)

    tmp = LIVE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(LIVE)
    print(f"[refresh] wrote {LIVE} in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
