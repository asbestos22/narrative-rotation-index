# Narrative Quant Strategist

## Overview
A dual-mode quantitative strategy skill providing macro analysis and narrative-specific signal generation. Integrates with the CMC AI Agent Hub, BNBAgent SDK, and Trust Wallet Agent Kit for end-to-end strategy formulation and execution routing.

## Workflow Architecture

**1. Agent Request** → Triggers `RUN_SKILL`  
**2. x402 Payment Gate**  
   - ❌ **Missing Proof** → Reject (402 Payment Required)  
   - ✅ **Valid Proof** → Deduct $0.05 & Proceed  
**3. Narrative Alpha Analysis** → Evaluates sector-specific metrics (e.g., Meme social volume, Privacy mixer volume)  
**4. Signal Generation** → Outputs LONG/SHORT verdict + TWAK execution payload  
**5. Backtest Validation** → Simulates 30-day performance (Sharpe, Drawdown, Return)  

## Core Actions
### 1. RUN SKILL
Analyzes a specific market narrative (**AI Tokens, RWA, DePIN, Meme, Privacy**) using **narrative-specific alpha metrics** to generate a structured quant strategy spec:
- **Signal Verdict**: LONG / SHORT / NEUTRAL
- **Entry/Exit Logic**: Rule-based triggers tailored to the sector (e.g., Meme social velocity, Privacy mixer volume)
- **Position Sizing**: Risk-adjusted allocation %
- **Invalidation Signals**: Clear conditions to abort the thesis
- **TWAK Execution Payload**: Pre-formatted BNBAgent SDK ToolCall ready for Trust Wallet Agent Kit signing.

### 2. GLOBAL SCAN
Cross-narrative macro analysis outputting:
- **Portfolio Tilt Weights**: Dynamic allocation % across core narratives
- **Rotation Signals**: Actionable sector rotation recommendations
- **Macro Headwinds**: Identified systemic risks

## Architecture & Integrations
| Component | Implementation |
| :--- | :--- |
| **CMC AI Agent Hub** | Core skill definition (`skill.yaml`). Utilizes MCP tools for RSI, volume profile, social delta, and Fear & Greed Index, plus narrative-specific metrics. |
| **BNBAgent SDK** | Output structures are formatted as `bnbagent_sdk_format: v1` ToolCalls for seamless ingestion by BNB Chain agent frameworks. |
| **Trust Wallet Agent Kit** | Generates ready-to-sign `trust_wallet_agent_kit.swap` payloads with optimal routing and slippage parameters upon valid signals. |
| **x402 Protocol** | Enforced pay-per-call verification. Requires `X402-Payment-Proof` header; rejects with 402 status if missing. |

## Advanced Features
1. **Narrative-Specific Alpha**: Moves beyond generic RSI. Evaluates sector-specific fundamentals:
   - **Meme**: Social volume velocity, holder growth %, dev sell pressure.
   - **Privacy**: Mixer volume trends, regulatory risk score.
   - **AI/DePIN/RWA**: GitHub commits, node growth, TradFi yield spreads.
2. **Simulated Backtest Engine**: Includes a built-in event-driven backtester tracking cumulative returns, max drawdown, and Sharpe ratio against synthetic OHLCV data.
3. **Active Payment Gate**: Programmatic enforcement of the x402 monetization layer before strategy execution.

## Project Structure
- `skill.yaml`: Official CMC Agent Hub skill specification with execution routing and x402 metadata.
- `backtest.py`: Executable script simulating MCP tool calls, narrative-specific alpha evaluation, x402 verification, and backtest metrics.
- `requirements.txt`: Python dependencies.

## Usage
```bash
pip install -r requirements.txt
python backtest.py
```

## Production Roadmap
1. Replace mock data functions with live CMC Data API and MCP tool calls.
2. Connect to a robust backtesting engine (e.g., `backtrader` or `vectorbt`) for historical OHLCV validation.
3. Enable direct Trust Wallet Agent Kit integration for autonomous, verified execution.
