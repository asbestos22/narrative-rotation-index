# Narrative Exhaustion Detector

The originality moat of the Narrative Rotation Index. Every quant skill says "buy the breakout"; this one says **"don't buy the breakout that's already over."**

## Why it matters

Crypto narratives die from exhaustion, not bad fundamentals. By the time price tops, the data has already shouted *"this is over"* for two weeks:

- Volume falls while price climbs (distribution).
- Social attention spikes while holders flatline (last-bag pump).
- Volatility expands but realized return shrinks (whipsaw).
- The trend is the consensus and there are no more buyers left.

Most strategy skills score *signal*. NRI scores **signal minus exhaustion**. A 70/100 momentum reading with 70/100 exhaustion is worth less than a 50/100 momentum reading with 0/100 exhaustion.

## Five exhaustion penalties

```python
# Penalty 1: Parabolic with declining volume
if return_7d > 40% AND volume_change_7d < 0:
    penalty += 25  # "distribution likely"

# Penalty 2: Social hype without holder growth
if social_volume > 10_000 AND holder_growth_7d < 3%:
    penalty += 20  # "attention-only pump"

# Penalty 3: Near 30d high but volume falling
if drawdown_from_high < 5% AND volume_change_7d < 0:
    penalty += 20  # "exhaustion at the top"

# Penalty 4: Crowd consensus
if trending_rank_avg < 5:
    penalty += 10  # "everyone is in"

# Penalty 5: Extreme volatility (>100% annualized)
if volatility_30d > 1.0:
    penalty += 15  # "mean reversion likely"
```

Sum, clamp to 0–100, subtract from final conviction. **Same data → different sizing depending on whether the move has legs left.**

## Score bands

| Score | Band | Sizing |
|-------|------|--------|
| 0–30 | Healthy | full conviction allowed |
| 31–60 | Caution | sizing reduced 30–50% |
| 61–100 | Crowded / late-cycle | strong penalty, sizing heavily reduced |

The detector does not say *avoid*. It says *size down*. A late-cycle move can still rip — but you bring less powder.

## Case studies

### LUNA — May 2022 collapse
- Last week of bull: price flat near ATH, basket return 7d **+2%**, volume change 7d **−40%**, holder growth **+0.2%**.
- Trending rank in top 5 for 3 weeks straight.
- Volatility 30d > 100% annualized.

Detector reading: **penalty ≈ 55** (drawdown<5% + volume<0 → +20, holder growth flat with social spike → +20, crowd consensus trending<5 → +10, vol > 1.0 → +15, capped at 100). Conviction would have been clamped, sizing reduced to 30–50% of base. The skill would not have called *short LUNA* — but it would not have been heavy long it on the way to zero.

### FTT — November 2022 (CZ tweet → CoinDesk balance sheet)
- Pre-tweet: FTT held high near $25, volume gradually declining 7d, price within 8% of 30d high, social mostly flat.
- Detector would not have flagged catastrophic risk — exhaustion is about *crowding*, not solvency. **This is honest.** Exhaustion is a tactical filter, not a fundamentals replacement. The README notes this: external `regulatory_clarity_score` and `dev_sell_pressure` cover counterparty risk; exhaustion covers crowded trades.

### BLUR — March 2023 airdrop pump
- Two days before peak: 7d return +110%, volume change 7d **−15%** (peak volume was day 0 of airdrop, 7d-back was higher), drawdown from high <2%, social_volume >> 10k, holder growth +1.5% (most airdrop recipients were dumping, not accumulating).
- Detector: parabolic+declining volume → +25, social-without-holders → +20, near-30d-high+declining-vol → +20, crowd consensus → +10, vol > 1 → +15. **Penalty hit cap at 100.** Sizing dropped to floor.
- Outcome: BLUR fell 60% in 14 days from that peak. The detector caught it.

### PEPE — May 2023 first parabolic top
- 7d return +180%, vol change −20% from prior week (volume dropped from $4B to $3.2B), drawdown from high <3%, kaito mindshare surge true, holder growth +25% but rate decelerating, trending rank #1 globally.
- Detector: ~60–80 penalty depending on holder-growth threshold tuning. Conviction reduced from STRONG_LONG to LONG.
- Outcome: PEPE fell 70% in the next month before rebuilding.

### DOGE — January 2021 (pre-Musk-tweet baseline)
- 7d return +15%, volume change +200%, drawdown from high 25% (still mid-rally), holder growth +18%, trending rank in 20–30, social moderate.
- Detector: **~10 penalty.** Healthy band. Conviction allowed near full.
- Outcome: DOGE rallied another 4x over the next 4 months. Detector did not get in the way of a real trend.

## Why this is the moat

Most "buy strong narratives" skills are momentum chasers in a bull and lag indicators in a top. NRI's exhaustion score is **path-dependent and asymmetric**: it lets you ride healthy moves and reduces conviction precisely when the move is most likely to reverse.

Three properties competitors won't replicate quickly:

1. **Volume vs. price divergence weighting** — the signal that calls distribution before price tops. Most quant skills treat volume as a confirmation indicator. We treat *declining* volume as a contradiction signal.
2. **Social-without-holders detection** — separates organic narrative growth from "last bag pump" speculation. Requires reading both attention metrics (CMC trending + Kaito mindshare) and on-chain holder count. Few skills wire both.
3. **Volatility-adjusted conviction cap** — a 100% annualized move signals mean reversion is ahead, regardless of momentum strength. We size down even when the trend is technically intact.

## Live integration

The same detector runs in two modes:

- **Backtest** — historical data fed to `compute_exhaustion_score(narrative, data)`, returns `(score, reasons[])`.
- **Live** — real-time CMC + Kaito metrics streamed in, scored on the same code path. See `live_demo.py`.

No re-implementation between the two. The skill is the same code in both contexts — important for trustworthiness.

## When the detector is wrong

It will undersize during the early breakout phase of a real new narrative (e.g. AI tokens late 2023, early DePIN early 2024). The cost: missed gains on legitimate trends.

This is the deliberate trade. **Missing the first 20% of a move is acceptable. Holding the last 30% on the way down is not.** Exhaustion-aware sizing is built for survival, not maximum upside.

## Related code

- `backtest.py` — `compute_exhaustion_score()` at line 332
- `tests/test_backtest.py` — covers the underlying scoring pipeline
- `compare_regime_scenarios.py` — shows how exhaustion interacts with regime sizing
- `skill.yaml` — `exhaustion_detector` schema block
