# CMC Metric Sourcing

Every metric used by the Narrative Rotation Index, mapped to its source. CMC-native metrics require nothing but a CMC API key. External enrichments are clearly marked.

## CMC-native (no extra APIs)

| Metric | Endpoint | Path |
|--------|----------|------|
| `basket_return_7d_pct` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.quote.USD.percent_change_7d` |
| `basket_return_24h_pct` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.quote.USD.percent_change_24h` |
| `volume_change_7d_pct` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.quote.USD.volume_change_24h` (24h proxy) |
| `volume_24h_usd` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.quote.USD.volume_24h` |
| `market_cap_change_7d_pct` | `/v1/cryptocurrency/quotes/latest` | derived from `percent_change_7d` × current `market_cap` |
| `market_cap_usd` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.quote.USD.market_cap` |
| `cmc_rank` | `/v1/cryptocurrency/quotes/latest` | `data.<SYMBOL>.cmc_rank` |
| `trending_rank_avg` | `/v1/cryptocurrency/trending/latest` | `data[].cmc_rank` (averaged across basket) |
| `relative_strength_vs_btc_7d` | `/v1/cryptocurrency/quotes/latest` | `(1 + basket_7d) / (1 + BTC_7d)` |
| `volatility_30d` | `/v1/cryptocurrency/ohlcv/historical` | computed std-dev of daily returns × √365 |
| `drawdown_from_30d_high_pct` | `/v1/cryptocurrency/ohlcv/historical` | `1 - (current / max(highs[-30:]))` |
| `rsi_14` | `/v1/cryptocurrency/ohlcv/historical` | computed from `close[-15:]` (Wilder's smoothing) |
| `liquidity_usd` | `/v2/exchange/quotes/latest` | aggregate `quote.USD.volume_24h` across top DEXs (or 24h volume as proxy) |
| `spread_pct` | `/v2/exchange/market-pairs/latest` | `(ask - bid) / mid` averaged across top 5 pairs |
| `total_market_cap_change_7d` | `/v1/global-metrics/quotes/latest` | `data.quote.USD.total_market_cap` (snapshot diff) |
| `btc_dominance_pct` | `/v1/global-metrics/quotes/latest` | `data.btc_dominance` |
| `fear_greed_index` | `/v3/fear-and-greed/latest` | `data.value` |

## CMC news / sentiment derived

| Metric | Source | How |
|--------|--------|-----|
| `institutional_mentions_7d` | `/v1/content/posts/top` | keyword filter `(institutional|BlackRock|ETF|bank)` over 7d window, deduplicated |
| `partnership_announcements_7d` | `/v1/content/posts/top` | keyword filter `(partner|integration|launch)` over 7d window |
| `regulatory_clarity_score` | `/v1/content/posts/top` | sentiment analysis over `(regulation|SEC|MiCA|legislation)` keywords, normalized 1–10 |

## External (require separate API)

| Metric | API | Endpoint |
|--------|-----|----------|
| `kaito_mindshare_score` | Kaito (SoFi) | `https://api.kaito.ai/api/v1/mindshare?token=<symbol>` |
| `kaito_mindshare_surge` | Kaito (SoFi) | derived: `mindshare_now / mindshare_48h_ago > 2.0` |
| `social_volume_24h` | Kaito + CMC community | aggregated |
| `holder_growth_7d_pct` | BSCScan / Etherscan | `/api?module=token&action=tokenholderlist&contractaddress=<addr>` snapshot diff |
| `whale_accumulation_7d_usd` | Nansen / Arkham | top wallet net inflow over 7d |
| `dev_sell_pressure` | on-chain | team wallet → CEX transfers, threshold $50k/7d |
| `tvl_change_7d_pct` | DeFiLlama | `https://api.llama.fi/v2/protocol/<slug>` |
| `yield_premium_vs_treasuries_bps` | DeFiLlama + FRED | DeFi yield − 10y treasury yield |
| `github_commits_7d` | GitHub API | `/repos/<org>/<repo>/commits?since=<7d>` per token org |
| `developer_growth_30d_pct` | GitHub API | unique contributors current 30d / prior 30d |
| `mixer_volume_7d_usd` | on-chain | Tornado/Aztec/Penumbra contract logs |
| `active_nodes_7d_growth_pct` | protocol dashboards | per-protocol custom |

## Auth

```bash
export CMC_API_KEY=your_key_here
curl -H "X-CMC_PRO_API_KEY: $CMC_API_KEY" \
     "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol=BTC,ETH&convert=USD"
```

Free tier: 10k credits/month, 30 calls/min. Sufficient for a few hundred backtests + ~20 live signal calls/hour.

## Rate limits

| Tier | Credits/month | Calls/min |
|------|---------------|-----------|
| Basic (free) | 10,000 | 30 |
| Hobbyist | 40,000 | 30 |
| Startup | 120,000 | 60 |
| Standard | 500,000 | 60 |
| Professional | 3M | 90 |

NRI's `live_demo.py` makes ~7 calls per scan (1 global, 1 fear&greed, 1 quotes for all symbols, 4 OHLCV optional). Well within free-tier budgets.

## Caching strategy

The skill is designed for cron-driven recurring calls. To stay within rate limits:

- Cache `quotes/latest` for 60s (CMC updates every minute anyway).
- Cache `global-metrics` for 5 min (BTC dominance moves slowly).
- Cache `trending/latest` for 15 min.
- Cache `OHLCV historical` for 1 hour (only used for volatility / RSI / drawdown).

Conviction decay (10%/day in `backtest.py`) is the upper bound — caching past 24h would degrade signal freshness below the decay floor.

## Related

- `live_demo.py` — reference implementation against the live API
- `backtest.py` — `CACHED_NARRATIVE_DATA` mirrors the same schema for offline testing
- `skill.yaml` — `alpha_metrics_by_narrative` block enumerates external sources per narrative
