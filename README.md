# Narrative Rotation Index (NRI)

[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![chain](https://img.shields.io/badge/chain-BNB%20Chain%20(BSC)-F0B90B.svg)](https://www.bnbchain.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![mcp](https://img.shields.io/badge/MCP-compatible-purple.svg)](https://modelcontextprotocol.io/)
[![tests](https://img.shields.io/badge/tests-15%20passing-success.svg)](tests/test_backtest.py)

A CMC-native AI-agent skill that ranks crypto narratives by relative strength, liquidity expansion, attention velocity, and macro regime — then outputs backtestable portfolio weights with structured confidence explanations and optional BNB Chain (BSC) Trust Wallet execution payloads.

Built for the **CMC AI Agent Hub** with native **BNBAgent SDK** and **Trust Wallet Agent Kit** integration. Exposed as an **MCP server** so any MCP-aware client can call it.

## Demo

![Demo](demo.svg)

```bash
$ python live_demo.py            # live CMC scoring
$ python mcp_server.py           # MCP stdio server (Claude Desktop, CMC Hub, agents)
$ python backtest.py             # 90-day historical basket simulation
$ python -m unittest tests       # 15 unit tests
```

## Table of Contents

- [Quick Start](#quick-start)
- [What is NRI](#what-is-nri)
- [Narrative Exhaustion Detector](#narrative-exhaustion-detector--the-original-moat) — the moat
- [Architecture](#architecture)
- [MCP Server](#mcp-server)
- [Live CMC Integration](#live-cmc-integration)
- [Scoring Model](#scoring-model)
- [Narrative Baskets (BSC)](#narrative-baskets-bsc)
- [Risk Controls & Guardrails](#execution-guardrails)
- [Files](#files)
- [Testing](#testing)
- [CHANGELOG](#changelog-v1--v8-evolution)

## Quick Start

```bash
git clone https://github.com/asbestos22/narrative-rotation-index.git
cd narrative-rotation-index
pip install -r requirements.txt

# Run the 90-day backtest with cached mock data (no API key needed)
python backtest.py

# Run the live demo against real CMC data
cp .env.example .env
# add your CMC_API_KEY
python live_demo.py
```

## What is NRI

> A backtestable strategy skill that scans 5 crypto narratives, detects market regime, ranks by relative strength and liquidity expansion, penalizes crowded late-cycle moves, and outputs portfolio weights plus an optional BNB Chain (BSC) Trust Wallet execution payload.

## Narrative Exhaustion Detector — The Original Moat

> 📖 **[Read the full Exhaustion Detector deep-dive](EXHAUSTION_DETECTOR.md)** — case studies (LUNA, FTT, BLUR, PEPE, DOGE) showing how the detector catches late-cycle moves before they reverse.

Prevents late-cycle entries by penalizing:
- Parabolic returns (+40% 7d) with declining volume
- Social hype without holder growth  
- Price near 30d high with falling relative volume
- Extreme volatility (>100% annualized)
- Crowd consensus crowding (trending rank < 5)

Score ranges:
- **0-30**: Healthy trend — full conviction
- **31-60**: Caution — sizing reduced
- **61-100**: Crowded/late-cycle — strong penalty

## MCP Server

NRI runs as a Model Context Protocol server so any MCP-aware client (Claude Desktop, CMC AI Agent Hub, BNBAgent SDK, custom agents) can call it natively over stdio or HTTP.

```bash
# stdio mode (default — for Claude Desktop / local clients)
python mcp_server.py

# streamable HTTP mode (for remote agents)
python mcp_server.py --http --port 8765
```

Tools exposed:

| Tool | Purpose |
|------|---------|
| `run_skill(narrative)` | Single-narrative deep dive with verdict, conviction, bucket scores, exhaustion, TWAK payload |
| `global_scan(regime?)` | Cross-narrative rotation engine with quadratic portfolio weighting |
| `detect_regime(fg, btc_dom, mcap_chg)` | Classify market regime from macro inputs |
| `get_twak_payload(narrative, amount, verdict)` | Generate BSC swap payload (BNBAgent SDK v1 ToolCall format) |
| `list_narratives()` | List supported narratives + BSC basket compositions |
| `get_skill_info()` | Skill metadata, scoring model, integrations |

**Claude Desktop config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "narrative-rotation-index": {
      "command": "python3",
      "args": ["/path/to/narrative-rotation-index/mcp_server.py"]
    }
  }
}
```

## Live CMC Integration

`live_demo.py` pulls real-time data from CMC v1 endpoints, transforms it into the scoring schema, and runs the full pipeline.

```bash
export CMC_API_KEY=your_key
python live_demo.py                     # scan all 5 narratives
python live_demo.py --narrative Meme    # single narrative
python live_demo.py --json              # structured JSON output
```

**Endpoints used:**
- `/v1/global-metrics/quotes/latest` — BTC dominance, total mcap change
- `/v1/cryptocurrency/quotes/latest` — basket token quotes (price, volume, mcap, % changes)
- `/v3/fear-and-greed/latest` — Fear & Greed index for regime detection

If `CMC_API_KEY` is not set, falls back to cached mock data with a clear warning so the demo still produces output.

📖 **[Full CMC metric → endpoint mapping](docs/cmc_metric_sources.md)** — every metric documented with its source, including external enrichments (Kaito, DeFiLlama, GitHub, BSCScan).

## Architecture

```
  ┌─────────────────────────────────────────────────────────┐
  │                  CMC Data Layer (Native)                │
  │  Prices · Volumes · Market Cap · Trending · Watchlists  │
  └────────────────────────┬────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │   Regime Detection       │
              │  RISK_ON · TRANSITION ·  │  Markov chain (70% stay)
              │  RISK_OFF               │  Conviction cap per regime
              └────────────┬────────────┘
                           │
     ┌─────────────────────┼─────────────────────┐
     │                     │                     │
  ┌──▼───────────┐  ┌──────▼──────┐  ┌──────────▼──────┐
  │ AI Tokens     │  │ RWA         │  │ DePIN            │
  │ FET, AGIX,    │  │ ONDO,       │  │ IOTX, FIL, NFP  │
  │ OCEAN         │  │ PENDLE, TRU │  │                  │
  └──┬────────────┘  └──────┬──────┘  └──────────┬──────┘
     │                     │                     │
  ┌──▼────────────┐  ┌─────▼───────┐            │
  │ Meme           │  │ Privacy      │            │
  │ DOGE, FLOKI,   │  │ TORN, SCRT, │            │
  │ BABYDOGE       │  │ ROSE        │            │
  └──┬────────────┘  └─────┬───────┘            │
     │                     │                     │
     └─────────────────────┼─────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  5-Bucket Scoring        │
              │  30% Momentum            │
              │  25% Liquidity           │  Quadratic weighting
              │  20% Attention           │  w_i = conv²/Σ(conv²)
              │  15% Fundamental         │  Min threshold = 20
              │  10% Risk Adjustment     │  Max allocation = 35%
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Exhaustion Detector     │
              │  0-30: Healthy           │
              │  31-60: Caution          │  Penalizes late entries
              │  61-100: Crowded         │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Risk Controls           │
              │  Circuit breaker (15%)   │
              │  Conviction decay (10%/d)│
              │  Execution guardrails    │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │  Structured Output       │
              │  Verdict · Conviction    │
              │  Reasons · Risks         │
              │  Bucket scores · Weights │
              │  BSC TWAK payload (optional) │
              └─────────────────────────┘
```

## Narrative Baskets (BSC)

| Narrative | Tokens (BEP-20 on BSC) |
|-----------|------------------------|
| AI Tokens | FET, AGIX, OCEAN¹ |
| RWA | ONDO, PENDLE, TRU |
| DePIN | IOTX, FIL, NFP |
| Meme | DOGE, FLOKI, BABYDOGE |
| Privacy | TORN, SCRT, ROSE |

¹ *AGIX and OCEAN merged into FET (ASI Alliance, Apr 2024). Standalone tokens are scheduled for deprecation. The basket is preserved for backtest reproducibility on historical 2024 data; live deployment should migrate to FET-only or substitute RENDER/TAO/AKT (currently bridge-required, not BSC-native).*

## Scoring Model

Final Narrative Score =
- **0.30 × Momentum**: basket return vs BTC, relative strength, RSI, drawdown from 30d high
- **0.25 × Liquidity**: volume growth, market cap change, depth, spread
- **0.20 × Attention**: CMC trending rank, social velocity, institutional mentions
- **0.15 × Fundamental**: narrative-specific utility (dev activity, TVL, node growth, etc.)
- **0.10 × Risk Adjustment**: volatility penalty + exhaustion detector

## Metric Sourcing

All core metrics are **CMC-native** (prices, volumes, market cap, trending, volatility). No external APIs required for the strategy to function.

Optional external enrichments are clearly source-annotated:
- GitHub commits → GitHub API
- TVL changes → DeFiLlama
- Regulatory sentiment → CMC news keyword filter
- Whale tracking → on-chain wallet analysis
- Social volume → LunarCrush / CMC community

## Why BNB Chain (BSC)?

This skill targets BSC for execution because:
- **Lower fees**: ~$0.01-0.10 per transaction vs Ethereum's $1-10+
- **Trust Wallet native**: Official BNB Chain wallet with 100M+ users
- **BNBAgent SDK alignment**: Native support for agentic operations
- **High liquidity**: Major DEXs (PancakeSwap) with deep pools
- **Fast confirmation**: 3-second block time vs Ethereum's 12 seconds

While the scoring logic is chain-agnostic, execution routing defaults to BSC for cost efficiency and Trust Wallet Agent Kit compatibility.

Three regimes with Markov chain persistence (70% stay probability):

| Regime | Conviction Cap | Position Sizing | Behavior |
|--------|---------------|-----------------|----------|
| **RISK_ON** | 100 | 100% | Full conviction, tech narratives get bonus |
| **TRANSITION** | 75 | 60% | Reduced sizing, STRONG_LONG still possible |
| **RISK_OFF** | 50 | 30% | STRONG_LONG mathematically impossible (cap < 60 threshold) |

## Execution Guardrails

| Guardrail | Limit |
|-----------|-------|
| Max slippage (large cap) | 1.0% |
| Max slippage (meme) | 2.5% |
| Max allocation per narrative | 35% |
| Max allocation per token | 15% |
| Minimum liquidity | $500,000 |
| Maximum spread | 1.5% |
| Minimum token age | 7 days |
| User confirmation | Always required |

## Risk Controls

- **Circuit Breaker**: 15% drawdown → all signals flip to NEUTRAL, sizing drops to 10% until recovery to 5%
- **Conviction Decay**: 10%/day without signal refresh — requires recurring x402 calls to keep signals fresh
- **Conviction Hard Cap**: Regime-specific ceiling prevents overconfidence in bear markets

## Output Format

Every signal includes structured confidence explanation:

```json
{
  "skill": "narrative-rotation-index",
  "regime": "TRANSITION",
  "top_narrative": "Meme",
  "verdict": "STRONG_LONG",
  "conviction": 65,
  "bucket_scores": {"momentum": 70, "liquidity": 85, "attention": 70, "fundamental": 60, "risk_adjustment": 70},
  "exhaustion": "25/100",
  "reasons": ["Strong relative strength vs BTC", "Volume expanding 85% WoW", ...],
  "risks": ["Regime is TRANSITION — allocation reduced", ...],
  "execution_guardrails": {"execution_allowed": true, "violations": []},
  "twak_payload": {"bnbagent_sdk_format": "v1", ...}
}
```

## Setup & Environment

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Add your CoinMarketCap API key to `.env` (required for live data fetching).
   - Get a free/pro key at [pro.coinmarketcap.com](https://pro.coinmarketcap.com/)
   - *Note: The `backtest.py` script runs out-of-the-box using cached mock data for demonstration. Live mode requires the API key.*

## Usage

```bash
pip install -r requirements.txt
python backtest.py
```

## Files

| File | Purpose |
|------|---------|
| `.env.example` | Environment variable template |
| `skill.yaml` | CMC Agent Hub skill specification |
| `backtest.py` | Executable NRI engine with basket backtest |
| `mcp_server.py` | Model Context Protocol server (stdio + HTTP) |
| `live_demo.py` | Live CMC API integration with mock fallback |
| `compare_regime_scenarios.py` | Demo: regime cap and position sizing across RISK_ON/TRANSITION/RISK_OFF |
| `sample_output.txt` | Reference terminal output from `python backtest.py` |
| `tests/test_backtest.py` | Unit tests for circuit breaker, t-distribution, conviction decay |
| `EXHAUSTION_DETECTOR.md` | Case studies showing the originality moat |
| `docs/cmc_metric_sources.md` | Every metric mapped to its CMC endpoint |
| `requirements.txt` | Python dependencies |

## Testing

15 unit tests cover the three v8.1 bug fixes (circuit breaker recovery, Student's t-distribution, conviction decay) plus regime scoring guarantees.

```bash
python -m unittest tests.test_backtest -v
```

Tested on Python 3.10, 3.11, and 3.12.

## CHANGELOG: v1 → v8 Evolution

**v8.0** (Current)
- Fixed circuit breaker recovery logic (trough-based recovery)
- Corrected t-distribution implementation (proper χ²/df scaling)
- Made conviction decay stateless (thread-safe for live agents)
- Added compare_regime_scenarios.py demo script
- Highlighted Narrative Exhaustion Detector as key innovation

**v7.0**
- Added Kaito (SoFi) social intelligence integration
- Enhanced dynamic token discovery with new launch filtering
- Implemented quadratic portfolio weighting (w_i = conv_i² / Σconv_j²)

**v6.0**
- Added Markov chain regime detection (70% persistence)
- Implemented regime-specific conviction caps
- Added exhaustion-aware position sizing

**v5.0**
- Added 5-bucket scoring model (Momentum/Liquidity/Attention/Fundamental/Risk)
- Implemented narrative exhaustion detector
- Added circuit breaker (15% drawdown → 10% sizing)

**v4.0**
- Added structured confidence output with reasons + risks
- Implemented execution guardrails (slippage, liquidity, token age)
- Added BNBAgent SDK v1 ToolCall format

**v3.0**
- Added x402 payment gate with tiered pricing
- Implemented auto-execute toggle for autonomous agents
- Added Trust Wallet Agent Kit integration

**v2.0**
- Added dynamic basket discovery (CMC trending + new listings)
- Implemented conviction decay (10%/day without refresh)
- Added backtest engine with Student's t-distribution

**v1.0**
- Initial release: 5-narrative rotation engine
- CMC-native metrics with external enrichments
- Basic scoring + portfolio weighting

## License

MIT
