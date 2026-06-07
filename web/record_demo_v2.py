#!/usr/bin/env python3
"""Record a demo of the NRI x402 buy flow + on-chain settlement proof.

Segments:
  1. Dashboard scroll (https://nri.realdo.org/ — public, live)
  2. Buy flow on local verify-only instance (127.0.0.1:8019):
     - injected EIP-1193 wallet (throwaway key) so the REAL page code runs
     - connect -> real EIP-3009 signTypedData -> X-PAYMENT -> 200 signal
     - NO funds move (verify-only instance, unfunded throwaway key)
  3. Settlement proof slate citing the REAL mainnet tx that already happened:
     0x6fd6c6073b5d4afe09f8ab12171332177c8c8a90c4a075f98953b0aaa5a1e19b

Output: /home/ubuntu/nri-web/demo/nri-demo.mp4
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

OUT_DIR = Path("/home/ubuntu/nri-web/demo")
DASH_URL = "https://nri.realdo.org/"
BUY_URL = "http://127.0.0.1:8019/buy"
WIDTH, HEIGHT = 1920, 1080

# Throwaway demo key — NEVER funded, used only to produce a real signature
# in front of a verify-only server. Generated fresh, no value at risk.
DEMO_PK = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"  # well-known hardhat key #1
DEMO_ADDR = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

REAL_TX = "0x6fd6c6073b5d4afe09f8ab12171332177c8c8a90c4a075f98953b0aaa5a1e19b"

# Injected EIP-1193 provider. Uses the page's own loaded `ethers` to sign.
INJECT = """
window.__DEMO_PK = "%s";
window.__DEMO_ADDR = "%s";
window.ethereum = {
  isMetaMask: true,
  _acct: window.__DEMO_ADDR,
  async request(args){
    const m = args.method, p = args.params || [];
    if (m === "eth_requestAccounts" || m === "eth_accounts") return [window.__DEMO_ADDR];
    if (m === "eth_chainId") return "0x38";
    if (m === "net_version") return "56";
    if (m === "wallet_switchEthereumChain") return null;
    if (m === "wallet_addEthereumChain") return null;
    if (m === "eth_signTypedData_v4"){
      const data = typeof p[1] === "string" ? JSON.parse(p[1]) : p[1];
      const types = Object.assign({}, data.types);
      delete types.EIP712Domain;            // ethers v6 wants this removed
      const w = new ethers.Wallet(window.__DEMO_PK);
      // brief pause so the "Sign in your wallet…" status is visible on camera
      await new Promise(r=>setTimeout(r, 1400));
      return await w.signTypedData(data.domain, types, data.message);
    }
    throw new Error("unhandled method "+m);
  },
  on(){}, removeListener(){},
};
""" % (DEMO_PK, DEMO_ADDR)


async def record() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT_DIR / "raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
            record_video_dir=str(raw_dir),
            record_video_size={"width": WIDTH, "height": HEIGHT},
        )
        page = await ctx.new_page()

        # ── Segment 1: dashboard scroll ──────────────────────────────────
        await page.goto(DASH_URL, wait_until="networkidle")
        await page.wait_for_selector(".dt", timeout=15000)
        await asyncio.sleep(2)
        height = await page.evaluate("document.body.scrollHeight - window.innerHeight")
        steps = 60
        for i in range(steps + 1):
            await page.evaluate(f"window.scrollTo({{top:{int(height*i/steps)}, behavior:'instant'}})")
            await asyncio.sleep(12 / steps)
        await asyncio.sleep(1)
        await page.evaluate("window.scrollTo({top:0, behavior:'instant'})")
        await asyncio.sleep(1)

        # ── Segment 2: buy flow with injected wallet ─────────────────────
        await page.add_init_script(INJECT)
        await page.goto(BUY_URL, wait_until="networkidle")
        await asyncio.sleep(2)
        # pick base tier (cheapest) for the demo
        await page.click('.tier[data-tier="base"]')
        await asyncio.sleep(1.2)
        await page.click("#btnConnect")
        await asyncio.sleep(2.2)            # connection + step 1
        await page.click("#btnBuy")
        # signing pause + fetch + result render
        await page.wait_for_selector("#resultCard:not(.hide)", timeout=20000)
        await asyncio.sleep(3.5)            # let the summary + result breathe

        # ── Segment 3: settlement proof slate ────────────────────────────
        await page.evaluate(SLATE_JS, REAL_TX)
        await asyncio.sleep(6)

        await page.close()
        await ctx.close()
        await browser.close()

    webms = list(raw_dir.glob("*.webm"))
    if not webms:
        raise RuntimeError("Playwright produced no video")
    src = webms[0]
    print(f"[record] webm: {src} ({src.stat().st_size/1024:.0f} KB)")
    return src


SLATE_JS = """
(tx) => {
  document.body.innerHTML = `
  <div style="position:fixed;inset:0;background:#0b0e11;color:#eaecef;
       font-family:'JetBrains Mono',monospace;display:flex;flex-direction:column;
       justify-content:center;align-items:center;text-align:center;padding:60px">
    <div style="color:#0ecb81;font-size:34px;font-weight:700;margin-bottom:8px">
      &#10003; PAID ON-CHAIN &middot; BSC MAINNET</div>
    <div style="color:#848e9c;font-size:18px;margin-bottom:36px">
      x402 EIP-3009 settlement &mdash; buyer signs gasless, NRI redeems on-chain</div>
    <div style="font-size:16px;line-height:2">
      <div><span style="color:#848e9c">Token&nbsp;&nbsp;&nbsp;</span> 0.01 U &middot; United Stables</div>
      <div><span style="color:#848e9c">To&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span> NRI 0x7D93&hellip;72C1 (agent 129156)</div>
      <div><span style="color:#848e9c">Buyer&nbsp;&nbsp;&nbsp;</span> paid 0 gas &mdash; just a signature</div>
    </div>
    <div style="margin-top:34px;color:#F0B90B;font-size:13px;word-break:break-all;max-width:1100px">
      ${tx}</div>
    <div style="margin-top:10px;color:#848e9c;font-size:13px">bscscan.com/tx/${tx.slice(0,18)}&hellip;</div>
  </div>`;
}
"""


def transcode(webm: Path) -> Path:
    mp4 = OUT_DIR / "nri-demo.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", str(webm),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
        str(mp4),
    ]
    print(f"[ffmpeg] transcoding…")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise RuntimeError("ffmpeg failed")
    print(f"[mp4] {mp4} ({mp4.stat().st_size/1024:.0f} KB)")
    return mp4


def main() -> int:
    t0 = time.time()
    webm = asyncio.run(record())
    mp4 = transcode(webm)
    print(f"[done] {time.time()-t0:.1f}s  ->  {mp4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
