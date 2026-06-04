# Narrative Quant Strategist

A multi-narrative quantitative strategy engine with regime-aware signal generation, cross-narrative rotation, and realistic backtest validation.

Built for the **CMC AI Agent Hub** with native **BNBAgent SDK** and **Trust Wallet Agent Kit** integration.

## Architecture

```
                     ┌─────────────────────────┐
                     │   Market Data Sources    │
                     │  CMC · On-chain · Social │
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │   Regime Detection       │
                     │  RISK_ON · TRANSITION ·  │
                     │  RISK_OFF                │
                     └────────────┬────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
   ┌──────────▼──────┐ ┌─────────▼────────┐ ┌───────▼────────┐
   │  AI Tokens       │ │  RWA             │ │  DePIN          │
   │  Dev activity    │ │  TVL + Yield     │ │  Node growth    │
   │  + Partnerships  │ │  + Regulatory    │ │  + Utilization  │
   └──────────┬──────┘ └─────────┬────────┘ └───────┬────────┘
              │                   │                   │
   ┌──────────▼──────┐ ┌─────────▼────────┐         │
   │  Meme            │ │  Privacy          │         │
   │  Social velocity │ │  Mixer volume    │         │
   │  + Whale accum   │ │  + Shielded pool │         │
   └──────────┬──────┘ └─────────┬────────┘         │
              │                   │                   │
              └───────────────────┼───────────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │   Global Scan Engine     │
                     │  Conviction scoring ·    │
                     │  Portfolio weighting ·   │
                     │  Rotation signals        │
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │  TWAK Payload Generator  │
                     │  BNBAgent SDK v1 format  │
                     │  → Trust Wallet signing  │
                     └────────────┬────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │  x402 Payment Gate       │
                     │  Pay-per-call ($0.05)    │
                     └─────────────────────────┘
```

## Supported Narratives

| Narrative | Lead Alpha Metrics | Signal Logic |
|-----------|-------------------|-------------|
| **AI Tokens** | GitHub commits, developer growth, partnerships, token velocity | Dev ecosystem momentum + oversold RSI |
| **RWA** | TVL change, institutional mentions, regulatory clarity, yield premium | Institutional inflow + regulatory tailwind |
| **DePIN** | Node growth, revenue/node, network utilization | Infrastructure expansion + profitable operators |
| **Meme** | Social velocity, holder growth, whale accumulation, dev sell pressure | Community momentum + smart money accumulation |
| **Privacy** | Mixer volume, regulatory risk, shielded pool growth, bridge count | Demand signal + manageable regulatory exposure |

## Market Regime Detection

The strategy adapts behavior based on three regimes:

- **RISK_ON**: Full position sizing. Tech narratives (AI, DePIN) get a bonus. Memes get reduced regime penalty.
- **TRANSITION**: 60% position sizing. Neutral weighting.
- **RISK_OFF**: 30% position sizing. Memes penalized heavily. Defensive rotation to stablecoins.

## Risk Metrics

The backtest engine tracks institutional-grade metrics:

| Metric | Description |
|--------|-------------|
| **Sharpe Ratio** | Risk-adjusted return (annualized, 2% risk-free) |
| **Sortino Ratio** | Downside-only risk adjustment |
| **Calmar Ratio** | Return / max drawdown |
| **Win Rate** | % of profitable trades |
| **Profit Factor** | Gross profit / gross loss |
| **Max Drawdown** | Largest peak-to-trough decline |

## Usage

```bash
pip install -r requirements.txt
python backtest.py
```

## TWAK Integration

When a narrative signals `STRONG_LONG` or `LONG`, the engine generates a pre-formatted BNBAgent SDK v1 ToolCall payload:

```json
{
  "bnbagent_sdk_format": "v1",
  "action": "trust_wallet_agent_kit.swap",
  "parameters": {
    "chain": "BNB Smart Chain",
    "from_token": "USDT",
    "to_token": "0x...",
    "amount_usd": 500,
    "slippage_tolerance": "0.5%",
    "routing_preference": "optimal"
  },
  "metadata": {
    "requires_user_confirmation": true,
    "signal_verdict": "STRONG_LONG"
  }
}
```

## x402 Payment Gate

All skill invocations require a valid `X402-Payment-Proof` header. Requests without valid proof receive a `402 Payment Required` response. Base fee: $0.05 per call.

## Files

| File | Purpose |
|------|---------|
| `skill.yaml` | CMC Agent Hub skill specification |
| `backtest.py` | Executable strategy engine with backtest |
| `requirements.txt` | Python dependencies |

## License

MIT
