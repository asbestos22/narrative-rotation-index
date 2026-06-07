#!/usr/bin/env python3
"""NRI public dashboard at nri.realdo.org — quant terminal UI."""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).parent))
from x402_paywall import serve_signal, PRICE_TIERS, NRI_AGENT_ID, NRI_PAY_TO, U_MAINNET

WEB = Path("/home/ubuntu/nri-web")
DATA = WEB / "data" / "live.json"
STATIC = WEB / "static"

app = FastAPI(title="Narrative Rotation Index", docs_url=None, redoc_url=None)
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


def load_data() -> dict:
    if not DATA.exists():
        return {"error": "no snapshot yet"}
    try:
        return json.loads(DATA.read_text())
    except Exception as e:
        return {"error": f"snapshot parse error: {e}"}


AGENT_ID_PATH = WEB / "data" / "agent_identity.json"


def load_agent_identity() -> dict:
    if not AGENT_ID_PATH.exists():
        return {}
    try:
        return json.loads(AGENT_ID_PATH.read_text())
    except Exception:
        return {}


def fmt_pct(v) -> str:
    try:
        return f"{float(v):+.2f}"
    except (TypeError, ValueError):
        return "—"


def fmt_usd(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    for u, dv in [("B", 1e9), ("M", 1e6), ("K", 1e3)]:
        if abs(x) >= dv:
            return f"{x/dv:.2f}{u}"
    return f"{x:.0f}"


def conv_color(c: int) -> str:
    if c >= 60: return "#0ECB81"
    if c >= 40: return "#F0B90B"
    if c >= 25: return "#FF9F1A"
    return "#F6465D"


def verdict_text(v: str) -> tuple[str, str]:
    v = (v or "").upper()
    if v in ("STRONG_LONG", "LONG"): return ("LONG", "#0ECB81")
    if v == "NEUTRAL": return ("NEUTRAL", "#848E9C")
    if v == "AVOID": return ("AVOID", "#F6465D")
    if v == "EXIT": return ("EXIT", "#F6465D")
    return (v or "—", "#848E9C")


def regime_decision(regime: str) -> str:
    r = (regime or "").upper()
    if r == "RISK_OFF":
        return "Reduce exposure. Conviction cap 50/75. Skip momentum entries."
    if r == "RISK_ON":
        return "Standard sizing. Follow top-conviction signals. Exits on regime flip."
    if r == "TRANSITION":
        return "Half-size only. Wait for regime confirmation before scaling."
    return "Awaiting regime classification."


def ts_age(iso: str) -> str:
    try:
        ts = time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
        secs = int(time.time() - time.mktime(ts) + time.timezone)
        if secs < 60: return f"{secs}s"
        if secs < 3600: return f"{secs//60}m {secs%60}s"
        return f"{secs//3600}h {(secs%3600)//60}m"
    except Exception:
        return "—"


@app.get("/api/live")
def api_live() -> JSONResponse:
    return JSONResponse(load_data())


@app.get("/api/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


# ─── x402-paywalled signal API (real on-chain payment gate) ───────────────
@app.get("/signal")
def signal_endpoint(request: Request, tier: str = "full_scan") -> JSONResponse:
    """Paywalled signal endpoint.

    GET /signal                 -> 402 Payment Required + EIP-3009 challenge
    GET /signal with X-PAYMENT  -> 200 + protected scan (tier-scoped)

    Tiers: base (0.01 U) / regime_update (0.1 U) / full_scan (0.5 U).
    All payments settle in U on BSC mainnet to the NRI agent wallet.
    """
    payment_header = request.headers.get("X-PAYMENT") or request.headers.get("x-payment")
    snapshot = load_data()
    result = serve_signal(payment_header, tier, snapshot)
    return JSONResponse(
        content=result.body,
        status_code=result.status,
        headers=result.headers,
    )


@app.get("/.well-known/x402", response_class=JSONResponse)
def x402_manifest() -> JSONResponse:
    """x402 service manifest — tells crawlers + clients what's paywalled."""
    return JSONResponse({
        "x402Version": 2,
        "service": "Narrative Rotation Index",
        "agentId": NRI_AGENT_ID,
        "agentRegistry": "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432",
        "network": "eip155:56",
        "asset": U_MAINNET,
        "payTo": NRI_PAY_TO,
        "tiers": {
            tier: {"amount": str(amount), "amount_human": f"{amount / 1e18:.4f} U"}
            for tier, amount in PRICE_TIERS.items()
        },
        "endpoints": {
            "/signal": "GET — full scan (tier=full_scan), regime (tier=regime_update), or single signal (tier=base)",
        },
    })


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    d = load_data()
    if "error" in d:
        return HTMLResponse(f"<pre style='color:#F6465D;background:#0B0E11;padding:32px;font-family:monospace'>{d['error']}</pre>", status_code=503)

    macro = d.get("macro", {})
    regime = d.get("regime", "UNKNOWN")
    regime_reason = d.get("regime_reason", "")
    regime_cap = d.get("regime_cap", 75)
    refreshed = d.get("_refreshed_at_utc", "—")
    age = ts_age(refreshed)
    version = d.get("version", "—")
    agent = load_agent_identity()

    # Status bar values
    fg = macro.get("fear_greed_index", "—")
    btcd = macro.get("btc_dominance_pct", 0)
    mc7d = macro.get("total_mcap_change_7d_pct", 0)

    # ─── Narrative ranking table ────────────────────────────
    narratives = d.get("narratives", {}) or {}
    sorted_narratives = sorted(
        narratives.items(),
        key=lambda kv: -int(kv[1].get("conviction", 0)),
    )

    rank_rows = []
    for idx, (name, n) in enumerate(sorted_narratives, start=1):
        conv = int(n.get("conviction", 0))
        verdict, vcolor = verdict_text(n.get("verdict", ""))
        cmc = n.get("cmc_live_metrics", {}) or {}
        ch24 = cmc.get("avg_24h_change_pct", 0) or 0
        ch7d = cmc.get("avg_7d_change_pct", 0) or 0
        ch30d = cmc.get("avg_30d_change_pct", 0) or 0
        vol = fmt_usd(cmc.get("total_24h_volume_usd", 0))
        mcap = fmt_usd(cmc.get("total_market_cap_usd", 0))
        tokens = " ".join(n.get("resolved_tokens", []) or [])
        guard = "OK" if n.get("execution_allowed") else "BLOCK"
        gcolor = "#0ECB81" if n.get("execution_allowed") else "#F6465D"

        c24 = "#0ECB81" if ch24 > 0 else "#F6465D" if ch24 < 0 else "#848E9C"
        c7d = "#0ECB81" if ch7d > 0 else "#F6465D" if ch7d < 0 else "#848E9C"
        c30d = "#0ECB81" if ch30d > 0 else "#F6465D" if ch30d < 0 else "#848E9C"

        bar_w = min(conv, 100)
        rank_rows.append(f"""
<tr class="row" data-narrative="{name}">
  <td class="rk">{idx:02d}</td>
  <td class="nm">{name}</td>
  <td class="conv">
    <div class="bar"><div style="width:{bar_w}%;background:{conv_color(conv)}"></div></div>
    <span class="num">{conv}</span><span class="den">/75</span>
  </td>
  <td class="num" style="color:{c24}">{fmt_pct(ch24)}</td>
  <td class="num" style="color:{c7d}">{fmt_pct(ch7d)}</td>
  <td class="num" style="color:{c30d}">{fmt_pct(ch30d)}</td>
  <td class="num">{vol}</td>
  <td class="num">{mcap}</td>
  <td class="vd" style="color:{vcolor}">{verdict}</td>
  <td class="gd" style="color:{gcolor}">{guard}</td>
  <td class="tk">{tokens}</td>
</tr>""")

    # ─── Top scored narrative — featured detail ─────────────
    top_name, top_n = sorted_narratives[0] if sorted_narratives else ("—", {})
    top_reasons = (top_n.get("reasons") or [])[:6]
    top_buckets = top_n.get("bucket_scores", {}) or {}
    top_tokens = top_n.get("resolved_tokens", []) or []
    top_verdict, top_vcolor = verdict_text(top_n.get("verdict", ""))
    top_conv = int(top_n.get("conviction", 0))

    bucket_rows = ""
    for k in ["momentum", "liquidity", "attention", "fundamental", "risk_adjustment"]:
        v = int(top_buckets.get(k, 0))
        bucket_rows += f"""
<div class="bk">
  <span class="bk-l">{k.replace('_',' ')}</span>
  <div class="bk-bar"><div style="width:{v}%;background:{conv_color(v)}"></div></div>
  <span class="bk-v">{v}</span>
</div>"""

    reasons_html = "".join(f"<li>{r}</li>" for r in top_reasons)

    # ─── v10: Stablecoin Risk Radar (SRR) panel ─────────────
    srr = d.get("stablecoin_risk", {}) or {}
    srr_rankings = srr.get("rankings", []) or []
    srr_target = srr.get("target") or {}
    defensive = (macro.get("defensive_rotation") or {}) if isinstance(macro, dict) else {}

    def verdict_color(v: str) -> str:
        return {
            "SAFE": "#0ECB81",
            "WATCH": "#F0B90B",
            "EXIT": "#FF7A45",
            "EMERGENCY": "#F6465D",
        }.get(v, "#848E9C")

    srr_rows = []
    for s in srr_rankings:
        v = s.get("verdict", "")
        vc = verdict_color(v)
        bs = s.get("bucket_scores", {}) or {}
        bsc = s.get("bsc_address") or ""
        addr_html = (
            f'<a class="addr" href="https://bscscan.com/token/{bsc}" target="_blank" rel="noopener">{bsc[:6]}…{bsc[-4:]}</a>'
            if bsc else '<span class="dim">—</span>'
        )
        srr_rows.append(f"""
<tr class="srr-row">
  <td class="nm">{s.get('symbol','')}</td>
  <td class="vd" style="color:{vc};font-weight:600">{v}</td>
  <td class="num"><span class="num">{s.get('score',0)}</span><span class="den">/100</span></td>
  <td class="num">{bs.get('peg',0)}</td>
  <td class="num">{bs.get('flow',0)}</td>
  <td class="num">{bs.get('reserves',0)}</td>
  <td class="num">{bs.get('liquidity',0)}</td>
  <td class="num">{bs.get('contagion',0)}</td>
  <td class="dim small">{s.get('issuer','')}</td>
  <td class="mono small">{addr_html}</td>
</tr>""")

    if defensive:
        defensive_banner = f"""
<div class="defensive-banner">
  <span class="db-tag">DEFENSIVE_ROTATION ACTIVE</span>
  <span class="db-body">Trigger: {defensive.get('trigger','')} → rotate to <strong>{defensive.get('target_symbol','—')}</strong> ({defensive.get('target_verdict','')}, SRR {defensive.get('target_score',0)})</span>
</div>"""
    elif srr_target:
        defensive_banner = f"""
<div class="srr-target-banner">
  <span class="db-tag">SRR target</span>
  <span class="db-body">Safest defensive rotation: <strong>{srr_target.get('symbol','—')}</strong> ({srr_target.get('verdict','')}, score {srr_target.get('score',0)}). No defensive trigger active.</span>
</div>"""
    else:
        defensive_banner = """
<div class="srr-target-banner">
  <span class="db-tag dim">SRR</span>
  <span class="db-body dim">No SAFE rotation target. Every stable in WATCH or worse — hold positions and reduce exposure.</span>
</div>"""

    # ─── Discovery panel (compact list) ─────────────────────
    discovery = (d.get("bsc_discovery") or {}).get("narratives") or {}
    SCORED = set(narratives.keys())
    disc_total_tokens = sum(len(v) for k, v in discovery.items() if k not in SCORED)
    disc_total_mcap = sum(
        sum(t.get("market_cap", 0) for t in v)
        for k, v in discovery.items() if k not in SCORED
    )

    disc_groups = []
    for narr, toks in discovery.items():
        if narr in SCORED or not toks:
            continue
        items = []
        for t in toks[:6]:
            ch = t.get("change_24h", 0) or 0
            cc = "#0ECB81" if ch > 0 else "#F6465D" if ch < 0 else "#848E9C"
            items.append(
                f'<a class="dt" href="https://bscscan.com/token/{t["address"]}" '
                f'target="_blank" rel="noopener">'
                f'<span class="dt-s">{t["symbol"]}</span>'
                f'<span class="dt-m">{fmt_usd(t.get("market_cap",0))}</span>'
                f'<span class="dt-c" style="color:{cc}">{fmt_pct(ch)}</span>'
                f'</a>'
            )
        disc_groups.append(f"""
<div class="dgroup">
  <div class="dgroup-h">
    <span class="dgroup-name">{narr}</span>
    <span class="dgroup-meta">{len(toks)} tokens · ${fmt_usd(sum(x.get('market_cap',0) for x in toks))}</span>
  </div>
  <div class="dgroup-body">{''.join(items)}</div>
</div>""")

    # Discovery overlays for SCORED narratives (BSC peers)
    peer_blocks = []
    for narr, n in narratives.items():
        movers = discovery.get(narr) or []
        core = {t.upper() for t in (n.get("resolved_tokens") or [])}
        extra = [m for m in movers if m["symbol"].upper() not in core][:5]
        if not extra:
            continue
        items = []
        for m in extra:
            ch = m.get("change_24h", 0) or 0
            cc = "#0ECB81" if ch > 0 else "#F6465D" if ch < 0 else "#848E9C"
            items.append(
                f'<a class="dt" href="https://bscscan.com/token/{m["address"]}" '
                f'target="_blank" rel="noopener">'
                f'<span class="dt-s">{m["symbol"]}</span>'
                f'<span class="dt-m">{fmt_usd(m.get("market_cap",0))}</span>'
                f'<span class="dt-c" style="color:{cc}">{fmt_pct(ch)}</span>'
                f'</a>'
            )
        peer_blocks.append(f"""
<div class="dgroup">
  <div class="dgroup-h">
    <span class="dgroup-name">{narr}</span>
    <span class="dgroup-meta">peers</span>
  </div>
  <div class="dgroup-body">{''.join(items)}</div>
</div>""")

    # macro values formatting
    btcd_str = f"{btcd:.2f}" if isinstance(btcd, (int, float)) else "—"
    mc7d_str = f"{mc7d:+.2f}" if isinstance(mc7d, (int, float)) else "—"
    mc7d_color = "#0ECB81" if isinstance(mc7d, (int, float)) and mc7d > 0 else "#F6465D"

    # ─── BNB AI Agent SDK on-chain identity (ERC-8004) ───────────────
    if agent.get("agentId"):
        aid = agent["agentId"]
        atx = agent.get("transactionHash", "")
        awl = agent.get("wallet_address", "")
        anet = agent.get("network", "—")
        areg = agent.get("registry_contract", "")
        agent_block = f"""
<div class="agent-id">
  <div class="agent-id-h">
    <span class="agent-id-tag">ERC-8004 ON-CHAIN IDENTITY</span>
    <span class="agent-id-net">BSC MAINNET · LIVE</span>
  </div>
  <div class="agent-id-grid">
    <div class="agent-id-cell">
      <span class="agent-id-lbl">agentId</span>
      <a class="agent-id-val mono gold" href="https://bscscan.com/token/{areg}?a={aid}" target="_blank" rel="noopener">#{aid}</a>
    </div>
    <div class="agent-id-cell">
      <span class="agent-id-lbl">tx hash</span>
      <a class="agent-id-val mono" href="https://bscscan.com/tx/{atx}" target="_blank" rel="noopener">{atx[:10]}…{atx[-8:]}</a>
    </div>
    <div class="agent-id-cell">
      <span class="agent-id-lbl">agent wallet</span>
      <a class="agent-id-val mono" href="https://bscscan.com/address/{awl}" target="_blank" rel="noopener">{awl[:6]}…{awl[-4:]}</a>
    </div>
    <div class="agent-id-cell">
      <span class="agent-id-lbl">network</span>
      <span class="agent-id-val mono">{anet}</span>
    </div>
    <div class="agent-id-cell">
      <span class="agent-id-lbl">gas</span>
      <span class="agent-id-val mono green">0 BNB · MegaFuel sponsored</span>
    </div>
    <div class="agent-id-cell">
      <span class="agent-id-lbl">SDK</span>
      <span class="agent-id-val mono">bnbagent · ERC-8004</span>
    </div>
  </div>
  <div class="agent-id-foot">
    Registered via the official BNB AI Agent SDK (<code>pip install bnbagent</code>).
    NRI is a discoverable on-chain agent — any client can resolve agentId #{aid} to the live MCP and signal endpoints.
  </div>
  <div class="agent-id-protos">
    <div class="agent-id-proto">
      <span class="agent-id-proto-tag">ERC-8004</span>
      <span class="agent-id-proto-desc">on-chain identity · LIVE on mainnet</span>
    </div>
    <div class="agent-id-proto">
      <span class="agent-id-proto-tag">x402</span>
      <span class="agent-id-proto-desc">paywalled <a href="/.well-known/x402">/signal</a> · 0.01–0.5 U per call</span>
    </div>
    <div class="agent-id-proto">
      <span class="agent-id-proto-tag">ERC-8183</span>
      <span class="agent-id-proto-desc">commerce escrow · sells signed scans</span>
    </div>
  </div>
</div>"""
    else:
        agent_block = ""

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NRI · Narrative Rotation Index</title>
<meta name="description" content="Narrative rotation scoring on BNB Chain. Regime-aware relative strength signals.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {{
  --bg:#0B0E11;
  --panel:#11161D;
  --panel-2:#151B23;
  --border:#1E2530;
  --border-soft:#161C24;
  --text:#EAECEF;
  --muted:#848E9C;
  --dim:#5E6873;
  --gold:#F0B90B;
  --green:#0ECB81;
  --red:#F6465D;
  --orange:#FF9F1A;
}}
* {{ box-sizing:border-box; }}
html, body {{ margin:0; padding:0; }}
body {{
  background:var(--bg);
  color:var(--text);
  font-family:'Inter', system-ui, sans-serif;
  font-size:13px;
  font-feature-settings:'cv11','ss01','ss02';
  -webkit-font-smoothing:antialiased;
  line-height:1.4;
}}
.mono {{ font-family:'JetBrains Mono', ui-monospace, monospace; }}
a {{ color:inherit; text-decoration:none; }}

/* ─── Status bar ─── */
.statusbar {{
  display:flex;
  align-items:center;
  gap:0;
  height:36px;
  background:var(--panel);
  border-bottom:1px solid var(--border);
  padding:0 16px;
  font-size:11px;
  letter-spacing:0.3px;
  position:sticky;
  top:0;
  z-index:10;
}}
.sb-brand {{
  display:flex; align-items:center; gap:8px;
  padding-right:16px; margin-right:16px;
  border-right:1px solid var(--border);
  height:100%;
}}
.sb-brand .dot {{ width:6px; height:6px; border-radius:50%; background:var(--green); box-shadow:0 0 6px var(--green); animation:pulse 2s infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.4; }} }}
.sb-brand .nm {{ font-weight:700; letter-spacing:1px; }}
.sb-brand .ver {{ color:var(--muted); font-family:'JetBrains Mono',monospace; }}
.sb-cell {{ display:flex; align-items:center; gap:8px; padding:0 14px; height:100%; border-right:1px solid var(--border-soft); }}
.sb-cell .lbl {{ color:var(--dim); font-size:10px; text-transform:uppercase; }}
.sb-cell .val {{ font-family:'JetBrains Mono',monospace; font-weight:500; }}
.sb-spacer {{ flex:1; }}
.sb-cell.right {{ border-right:none; border-left:1px solid var(--border-soft); }}

/* ─── Layout ─── */
main {{ padding:16px; max-width:1600px; margin:0 auto; }}
.grid-top {{
  display:grid;
  grid-template-columns:1fr 360px;
  gap:16px;
  margin-bottom:16px;
}}
@media (max-width: 1100px) {{
  .grid-top {{ grid-template-columns:1fr; }}
}}

/* ─── Panel ─── */
.panel {{
  background:var(--panel);
  border:1px solid var(--border);
  border-radius:4px;
}}
.panel-h {{
  display:flex;
  justify-content:space-between;
  align-items:center;
  padding:10px 14px;
  border-bottom:1px solid var(--border);
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:1px;
  color:var(--muted);
}}
.panel-h .ttl {{ color:var(--text); font-weight:600; }}
.panel-h .meta {{ font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--dim); }}

/* ─── Regime header ─── */
.regime-bar {{
  padding:14px 18px;
  display:flex;
  align-items:center;
  gap:24px;
  border-bottom:1px solid var(--border);
}}
.regime-bar .rg-tag {{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;
  color:var(--dim);
  text-transform:uppercase;
}}
.regime-bar .rg-name {{
  font-family:'JetBrains Mono',monospace;
  font-size:22px;
  font-weight:600;
  color:var(--gold);
  letter-spacing:1px;
}}
.regime-bar .rg-cap {{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;
  color:var(--muted);
  border:1px solid var(--border);
  padding:3px 8px;
  border-radius:3px;
}}
.regime-bar .rg-decision {{
  flex:1;
  font-size:12px;
  color:var(--text);
  border-left:1px solid var(--border);
  padding-left:24px;
}}
.regime-bar .rg-decision .lbl {{ color:var(--dim); font-size:10px; text-transform:uppercase; letter-spacing:1px; display:block; margin-bottom:2px; }}

/* ─── Ranking table ─── */
table.rank {{ width:100%; border-collapse:collapse; }}
table.rank th {{
  text-align:left;
  font-weight:500;
  font-size:10px;
  color:var(--dim);
  text-transform:uppercase;
  letter-spacing:0.8px;
  padding:8px 12px;
  border-bottom:1px solid var(--border);
  background:var(--panel-2);
}}
table.rank td {{
  padding:11px 12px;
  border-bottom:1px solid var(--border-soft);
  vertical-align:middle;
}}
table.rank tr.row:hover {{ background:#0F141B; }}
table.rank tr.row:last-child td {{ border-bottom:none; }}

td.rk {{ font-family:'JetBrains Mono',monospace; color:var(--dim); width:32px; }}
td.nm {{ font-weight:600; width:120px; }}
td.conv {{ width:200px; }}
td.conv .bar {{
  display:inline-block;
  width:100px;
  height:4px;
  background:#0F141B;
  border-radius:1px;
  overflow:hidden;
  vertical-align:middle;
  margin-right:10px;
}}
td.conv .bar > div {{ height:100%; transition:width 0.3s; }}
td.conv .num {{ font-family:'JetBrains Mono',monospace; font-weight:600; font-size:13px; }}
td.conv .den {{ font-family:'JetBrains Mono',monospace; color:var(--dim); font-size:10px; }}
td.num {{ font-family:'JetBrains Mono',monospace; font-size:12px; text-align:right; width:75px; }}
td.vd {{ font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:600; letter-spacing:0.5px; width:75px; }}
td.gd {{ font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; letter-spacing:0.5px; width:55px; }}
td.tk {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--muted); }}

/* ─── Featured panel ─── */
.fp {{ padding:16px; }}
.fp-head {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; }}
.fp-name {{ font-size:18px; font-weight:600; margin:0 0 4px; }}
.fp-sub {{ font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--dim); text-transform:uppercase; letter-spacing:1px; }}
.fp-conv {{ text-align:right; }}
.fp-conv .v {{ font-family:'JetBrains Mono',monospace; font-size:32px; font-weight:600; line-height:1; }}
.fp-conv .d {{ font-family:'JetBrains Mono',monospace; color:var(--dim); font-size:11px; }}
.fp-vd {{ font-family:'JetBrains Mono',monospace; font-size:11px; font-weight:600; letter-spacing:1px; padding:4px 8px; border:1px solid currentColor; border-radius:2px; display:inline-block; margin-top:4px; }}

.bk {{ display:grid; grid-template-columns:90px 1fr 30px; gap:10px; align-items:center; padding:6px 0; }}
.bk-l {{ font-size:10px; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; }}
.bk-bar {{ height:3px; background:#0F141B; border-radius:1px; overflow:hidden; }}
.bk-bar > div {{ height:100%; }}
.bk-v {{ font-family:'JetBrains Mono',monospace; font-size:11px; text-align:right; color:var(--muted); }}

.fp-section {{ margin-top:18px; padding-top:14px; border-top:1px solid var(--border-soft); }}
.fp-section h4 {{ font-size:10px; text-transform:uppercase; color:var(--dim); letter-spacing:1px; margin:0 0 8px; font-weight:500; }}
.fp-reasons {{ list-style:none; padding:0; margin:0; font-size:12px; color:var(--muted); }}
.fp-reasons li {{ padding:3px 0 3px 14px; position:relative; }}
.fp-reasons li:before {{ content:"→"; position:absolute; left:0; color:var(--gold); font-family:'JetBrains Mono',monospace; }}
.fp-tokens {{ font-family:'JetBrains Mono',monospace; font-size:11px; color:var(--gold); letter-spacing:0.5px; }}

/* ─── Discovery ─── */
.disc-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:1px; background:var(--border); border:1px solid var(--border); border-radius:4px; overflow:hidden; }}
.dgroup {{ background:var(--panel); padding:12px 14px; }}
.dgroup-h {{ display:flex; justify-content:space-between; align-items:baseline; margin-bottom:8px; padding-bottom:6px; border-bottom:1px dashed var(--border); }}
.dgroup-name {{ font-size:12px; font-weight:600; }}
.dgroup-meta {{ font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--dim); }}
.dgroup-body {{ display:flex; flex-direction:column; }}

/* ─── v10: SRR ─── */
.defensive-banner {{ background:linear-gradient(90deg, rgba(246,70,93,0.12), rgba(246,70,93,0.04)); border:1px solid #F6465D; border-radius:4px; padding:10px 14px; margin:8px 0; display:flex; gap:14px; align-items:center; }}
.defensive-banner .db-tag {{ background:#F6465D; color:#0B0E11; padding:3px 8px; border-radius:3px; font-size:10px; font-weight:700; letter-spacing:0.5px; font-family:'JetBrains Mono',monospace; }}
.defensive-banner .db-body {{ font-size:13px; }}
.srr-target-banner {{ background:rgba(240,185,11,0.06); border:1px dashed var(--border); border-radius:4px; padding:8px 14px; margin:8px 0; display:flex; gap:14px; align-items:center; }}
.srr-target-banner .db-tag {{ color:var(--accent); font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600; letter-spacing:0.5px; }}
.srr-target-banner .db-body {{ font-size:12px; color:var(--text); }}
.srr-target-banner .dim {{ color:var(--dim); }}
.srr-wrap {{ background:var(--panel); border:1px solid var(--border); border-radius:4px; padding:0; overflow-x:auto; }}
.srr-table {{ width:100%; border-collapse:collapse; font-family:'JetBrains Mono',monospace; font-size:12px; }}
.srr-table thead th {{ background:rgba(255,255,255,0.02); padding:8px 10px; text-align:left; font-weight:500; color:var(--dim); font-size:10px; letter-spacing:0.5px; text-transform:uppercase; border-bottom:1px solid var(--border); }}
.srr-table thead th.num {{ text-align:right; }}
.srr-table tbody td {{ padding:8px 10px; border-bottom:1px solid var(--border); }}
.srr-table tbody tr:last-child td {{ border-bottom:none; }}
.srr-table tbody tr:hover {{ background:rgba(240,185,11,0.04); }}
.srr-table .nm {{ font-weight:600; color:var(--text); }}
.srr-table .num {{ text-align:right; color:var(--text); }}
.srr-table .dim {{ color:var(--dim); }}
.srr-table .small {{ font-size:11px; }}
.srr-table .addr {{ color:var(--accent); text-decoration:none; }}
.srr-table .addr:hover {{ text-decoration:underline; }}
.dt {{ display:grid; grid-template-columns:60px 1fr 56px; gap:8px; align-items:center; padding:4px 0; font-size:11px; }}
.dt:hover {{ color:var(--gold); }}
.dt-s {{ font-weight:600; }}
.dt-m {{ font-family:'JetBrains Mono',monospace; color:var(--muted); font-size:11px; }}
.dt-c {{ font-family:'JetBrains Mono',monospace; text-align:right; }}

/* ─── Section heads ─── */
.section-head {{ display:flex; justify-content:space-between; align-items:baseline; margin:24px 0 10px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
.section-head h2 {{ font-size:13px; margin:0; font-weight:600; letter-spacing:0.5px; }}
.section-head .sub {{ font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--dim); text-transform:uppercase; letter-spacing:1px; }}

/* ─── BNB AI Agent SDK identity block ─── */
.agent-id {{
  margin:16px 0 8px;
  border:1px solid var(--gold);
  border-radius:6px;
  background:linear-gradient(180deg, rgba(240,185,11,0.06) 0%, rgba(240,185,11,0.02) 100%);
  padding:14px 18px;
}}
.agent-id-h {{
  display:flex; justify-content:space-between; align-items:center;
  margin-bottom:12px; padding-bottom:8px;
  border-bottom:1px solid rgba(240,185,11,0.2);
}}
.agent-id-tag {{
  font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:700;
  letter-spacing:2px; color:var(--gold);
}}
.agent-id-net {{
  font-family:'JetBrains Mono',monospace; font-size:10px; font-weight:600;
  letter-spacing:1.5px; color:var(--green);
  padding:3px 8px; border:1px solid var(--green); border-radius:3px;
  background:rgba(14,203,129,0.05);
}}
.agent-id-grid {{
  display:grid; grid-template-columns:repeat(6, 1fr); gap:14px 20px;
}}
.agent-id-cell {{ display:flex; flex-direction:column; gap:4px; min-width:0; }}
.agent-id-lbl {{
  font-size:9px; font-weight:600; letter-spacing:1.5px;
  text-transform:uppercase; color:var(--dim);
}}
.agent-id-val {{
  font-size:13px; font-weight:500;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.agent-id-val.gold {{ color:var(--gold); font-weight:700; font-size:14px; }}
.agent-id-val.green {{ color:var(--green); }}
.agent-id-val a, a.agent-id-val {{ color:inherit; border-bottom:1px dotted rgba(255,255,255,0.2); padding-bottom:1px; }}
.agent-id-val a:hover, a.agent-id-val:hover {{ border-bottom-color:var(--gold); }}
.agent-id-foot {{
  margin-top:12px; padding-top:10px;
  border-top:1px solid var(--border-soft);
  font-size:11px; color:var(--muted); line-height:1.6;
}}
.agent-id-foot code {{
  font-family:'JetBrains Mono',monospace;
  background:var(--panel-2); padding:1px 5px; border-radius:3px;
  color:var(--gold); font-size:10.5px;
}}
@media (max-width: 1100px) {{
  .agent-id-grid {{ grid-template-columns:repeat(3, 1fr); }}
}}
@media (max-width: 640px) {{
  .agent-id-grid {{ grid-template-columns:repeat(2, 1fr); }}
}}
.agent-id-protos {{
  display:flex; gap:10px; margin-top:12px; padding-top:10px;
  border-top:1px solid var(--border-soft);
  flex-wrap:wrap;
}}
.agent-id-proto {{
  display:flex; align-items:center; gap:8px;
  padding:5px 10px; border:1px solid var(--gold);
  border-radius:3px; background:rgba(240,185,11,0.04);
  font-size:11px;
}}
.agent-id-proto-tag {{
  font-family:'JetBrains Mono',monospace; font-weight:700;
  letter-spacing:0.5px; color:var(--gold);
}}
.agent-id-proto-desc {{ color:var(--muted); }}
.agent-id-proto a {{ color:var(--gold); text-decoration:underline; }}

/* ─── Footer ─── */
footer {{ padding:24px 16px 32px; color:var(--dim); font-size:11px; text-align:center; border-top:1px solid var(--border); margin-top:32px; }}
footer .mono {{ color:var(--muted); }}
footer a {{ color:var(--gold); }}

::selection {{ background:var(--gold); color:var(--bg); }}
::-webkit-scrollbar {{ width:8px; height:8px; }}
::-webkit-scrollbar-track {{ background:var(--bg); }}
::-webkit-scrollbar-thumb {{ background:var(--border); border-radius:4px; }}
::-webkit-scrollbar-thumb:hover {{ background:var(--muted); }}
</style>
</head>
<body>

<div class="statusbar">
  <div class="sb-brand">
    <div class="dot"></div>
    <span class="nm">NRI</span>
    <span class="ver">v{version}</span>
  </div>
  <div class="sb-cell"><span class="lbl">Updated</span><span class="val">{age} ago</span></div>
  <div class="sb-cell"><span class="lbl">Chain</span><span class="val" style="color:var(--gold)">BNB</span></div>
  <div class="sb-cell"><span class="lbl">Source</span><span class="val">CMC v1</span></div>
  <div class="sb-cell"><span class="lbl">Refresh</span><span class="val">15m</span></div>
  <div class="sb-spacer"></div>
  <div class="sb-cell right"><span class="lbl">F&amp;G</span><span class="val">{fg}</span></div>
  <div class="sb-cell right"><span class="lbl">BTC.D</span><span class="val">{btcd_str}%</span></div>
  <div class="sb-cell right"><span class="lbl">Mcap 7d</span><span class="val" style="color:{mc7d_color}">{mc7d_str}%</span></div>
  <div class="sb-cell right"><a class="val" href="/api/live" style="color:var(--muted)">JSON</a></div>
</div>

<main>

  {agent_block}

  <!-- Regime + ranking ─── primary block -->
  <div class="grid-top">
    <div class="panel">
      <div class="regime-bar">
        <div>
          <div class="rg-tag">Regime</div>
          <div class="rg-name">{regime}</div>
        </div>
        <div class="rg-cap mono">cap {regime_cap}/75</div>
        <div class="rg-decision">
          <span class="lbl">Decision</span>
          {regime_decision(regime)}
          <div style="color:var(--muted);font-size:11px;margin-top:4px">{regime_reason}</div>
        </div>
      </div>
      <table class="rank">
        <thead>
          <tr>
            <th>#</th>
            <th>Narrative</th>
            <th>Conviction</th>
            <th style="text-align:right">24h</th>
            <th style="text-align:right">7d</th>
            <th style="text-align:right">30d</th>
            <th style="text-align:right">Vol 24h</th>
            <th style="text-align:right">Mcap</th>
            <th>Verdict</th>
            <th>Guard</th>
            <th>Tokens</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rank_rows)}
        </tbody>
      </table>
    </div>

    <!-- Featured: top conviction -->
    <div class="panel">
      <div class="panel-h">
        <span class="ttl">Top Signal</span>
        <span class="meta">rank 01</span>
      </div>
      <div class="fp">
        <div class="fp-head">
          <div>
            <h3 class="fp-name">{top_name}</h3>
            <div class="fp-sub">5-bucket score</div>
          </div>
          <div class="fp-conv">
            <div class="v" style="color:{conv_color(top_conv)}">{top_conv}</div>
            <div class="d">conviction / 75</div>
            <div class="fp-vd" style="color:{top_vcolor}">{top_verdict}</div>
          </div>
        </div>
        <div class="fp-buckets">
          {bucket_rows}
        </div>
        <div class="fp-section">
          <h4>Signals</h4>
          <ul class="fp-reasons">{reasons_html}</ul>
        </div>
        <div class="fp-section">
          <h4>Execution Basket</h4>
          <div class="fp-tokens">{' · '.join(top_tokens)}</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Peer overlays ─── BSC top movers per scored narrative -->
  <div class="section-head">
    <h2>BSC Peers</h2>
    <span class="sub">By narrative · ranked by mcap</span>
  </div>
  <div class="disc-grid">
    {''.join(peer_blocks)}
  </div>

  <!-- v10: Stablecoin Risk Radar -->
  <div class="section-head">
    <h2>Stablecoin Risk Radar</h2>
    <span class="sub">Defensive rotation overlay · SRR = 0.30×Peg + 0.25×Flow + 0.20×Reserves + 0.15×Liquidity + 0.10×Contagion</span>
  </div>
  {defensive_banner}
  <div class="srr-wrap">
    <table class="srr-table">
      <thead>
        <tr>
          <th class="nm">Stable</th>
          <th>Verdict</th>
          <th class="num">SRR</th>
          <th class="num">Peg</th>
          <th class="num">Flow</th>
          <th class="num">Rsv</th>
          <th class="num">Liq</th>
          <th class="num">Con</th>
          <th class="dim">Issuer</th>
          <th class="dim">BSC</th>
        </tr>
      </thead>
      <tbody>
        {''.join(srr_rows)}
      </tbody>
    </table>
  </div>

  <!-- Discovery ─── unscored BSC narratives -->
  <div class="section-head">
    <h2>Discovery</h2>
    <span class="sub">{disc_total_tokens} BSC tokens · ${fmt_usd(disc_total_mcap)} combined mcap</span>
  </div>
  <div class="disc-grid">
    {''.join(disc_groups)}
  </div>

</main>

<footer>
  <div class="mono">NRI · narrative rotation index · BNB chain hackathon track 2</div>
  <div style="margin-top:6px">
    <a href="/api/live">api/live</a> ·
    <a href="https://github.com/asbestos22/narrative-rotation-index">github</a> ·
    <span class="mono">curated execution + open discovery</span>
  </div>
</footer>

</body>
</html>"""
    return HTMLResponse(body)
