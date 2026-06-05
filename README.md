# Narrative Rotation Index (NRI)

A CMC-native AI-agent skill that ranks crypto narratives by relative strength, liquidity expansion, attention velocity, and macro regime — then outputs backtestable portfolio weights with structured confidence explanations and optional BNB Chain (BSC) Trust Wallet execution payloads.

Built for the **CMC AI Agent Hub** with native **BNBAgent SDK** and **Trust Wallet Agent Kit** integration.

## One-Line Pitch

> A backtestable strategy skill that scans 5 crypto narratives, detects market regime, ranks by relative strength and liquidity expansion, penalizes crowded late-cycle moves, and outputs portfolio weights plus an optional BNB Chain (BSC) Trust Wallet execution payload.

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
  │ FET, RENDER   │  │ ONDO, CFG   │  │ FIL, HNT, RNDR  │
  │ TAO, AKT      │  │ MPL, POLYX  │  │ IOTX             │
  └──┬────────────┘  └──────┬──────┘  └──────────┬──────┘
     │                     │                     │
  ┌──▼────────────┐  ┌─────▼───────┐            │
  │ Meme           │  │ Privacy      │            │
  │ DOGE, PEPE     │  │ ZEC, SCRT   │            │
  │ WIF, BONK      │  │ ROSE, TORN  │            │
  └──┬────────────┘  └─────┬───────┘            │
     │                     │                     │
     └─────────────────────┼─────────────────────┘
                           │
              ┌────────────▼────────────┐
              │  4-Bucket Scoring        │
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

## Narrative Exhaustion Detector

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

## Market Regime Detection

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
  "conviction": 62,
  "bucket_scores": {"momentum": 70, "liquidity": 85, "attention": 55, "fundamental": 60, "risk_adjustment": 70},
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
| `requirements.txt` | Python dependencies |

## License

MIT
