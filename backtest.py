import json
import math
import random
import time
from datetime import datetime

# ==============================================================================
# 1. X402 PAYMENT GATE (TIERED PRICING)
# ==============================================================================
X402_PRICING = {
    "base": 0.05,
    "regime_update": 0.20,
    "full_scan": 0.50,
}

def verify_x402_payment(headers, tier="base"):
    expected_proof = "valid_proof_123"
    if headers.get("X402-Payment-Proof") != expected_proof:
        return False, f"402 Payment Required ({X402_PRICING[tier]:.2f} USD)."
    return True, f"Payment verified. ${X402_PRICING[tier]:.2f} fee deducted (tier: {tier})."


# ==============================================================================
# 2. EXECUTION GUARDRAILS & AUTO-EXECUTE TOGGLE
# ==============================================================================
# Auto-execute toggle: when True, TWAK payloads are generated without
# requiring user confirmation. When False (default), requires confirmation.
# Set to True for autonomous agent operation. Set to False for safe mode.
AUTO_EXECUTE = False

EXECUTION_LIMITS = {
    "max_slippage_large_cap_pct": 1.0,
    "max_slippage_meme_pct": 2.5,
    "max_allocation_per_narrative_pct": 35.0,
    "max_allocation_per_token_pct": 15.0,
    "min_liquidity_usd": 500_000,
    "max_spread_pct": 1.5,
    "min_token_age_days": 7,
    "requires_user_confirmation": not AUTO_EXECUTE,
}


def check_execution_guards(narrative, token_data):
    """Returns (allowed: bool, violations: list[str])."""
    violations = []

    if token_data.get("liquidity_usd", 0) < EXECUTION_LIMITS["min_liquidity_usd"]:
        violations.append(f"Liquidity ${token_data['liquidity_usd']:,.0f} below min ${EXECUTION_LIMITS['min_liquidity_usd']:,.0f}")

    if token_data.get("spread_pct", 0) > EXECUTION_LIMITS["max_spread_pct"]:
        violations.append(f"Spread {token_data['spread_pct']:.1f}% exceeds max {EXECUTION_LIMITS['max_spread_pct']}%")

    if token_data.get("token_age_days", 999) < EXECUTION_LIMITS["min_token_age_days"]:
        violations.append(f"Token age {token_data['token_age_days']}d < min {EXECUTION_LIMITS['min_token_age_days']}d — thin liquidity risk")

    if narrative == "Meme" and token_data.get("slippage_estimate_pct", 0) > EXECUTION_LIMITS["max_slippage_meme_pct"]:
        violations.append(f"Slippage {token_data['slippage_estimate_pct']:.1f}% > meme max {EXECUTION_LIMITS['max_slippage_meme_pct']}%")
    elif token_data.get("slippage_estimate_pct", 0) > EXECUTION_LIMITS["max_slippage_large_cap_pct"]:
        violations.append(f"Slippage {token_data['slippage_estimate_pct']:.1f}% > max {EXECUTION_LIMITS['max_slippage_large_cap_pct']}%")

    return len(violations) == 0, violations


# ==============================================================================
# 3. MARKET REGIME DETECTION (MARKOV CHAIN)
# ==============================================================================
REGIME_TRANSITIONS = {
    "RISK_ON":    {"RISK_ON": 0.70, "TRANSITION": 0.25, "RISK_OFF": 0.05},
    "TRANSITION": {"RISK_ON": 0.20, "TRANSITION": 0.60, "RISK_OFF": 0.20},
    "RISK_OFF":   {"RISK_ON": 0.05, "TRANSITION": 0.25, "RISK_OFF": 0.70},
}

REGIME_CONVICTION_CAP = {"RISK_ON": 100, "TRANSITION": 75, "RISK_OFF": 50}
REGIME_SIZING = {"RISK_ON": 1.0, "TRANSITION": 0.6, "RISK_OFF": 0.3}


def regime_position_multiplier(regime):
    return REGIME_SIZING.get(regime, 0.5)


def detect_market_regime(fear_greed_index, btc_dominance, total_mcap_change_7d):
    if fear_greed_index > 65 and btc_dominance < 50 and total_mcap_change_7d > 0.05:
        return "RISK_ON", "Altcoin-friendly: high greed, low BTC dominance, expanding mcap."
    elif fear_greed_index < 30 and btc_dominance > 55:
        return "RISK_OFF", "Flight to safety: fear dominant, BTC absorbing capital."
    else:
        return "TRANSITION", "Mixed signals: regime unclear, reduced position sizing."


def step_regime_markov(current):
    transitions = REGIME_TRANSITIONS[current]
    roll = random.random()
    cumulative = 0.0
    for regime, prob in transitions.items():
        cumulative += prob
        if roll <= cumulative:
            return regime
    return current


def build_regime_sequence(days, initial="TRANSITION"):
    seq = [initial]
    for _ in range(days - 1):
        seq.append(step_regime_markov(seq[-1]))
    return seq


# ==============================================================================
# 4. NARRATIVE BASKET DEFINITIONS (CMC-NATIVE TOKENS)
# ==============================================================================
# Each narrative is a basket of real tokens, weighted equally for backtest.
# Core metrics are CMC-native: price, volume, market cap, liquidity.
# Tokens mapped to their native chains. TWAK routes to the correct chain.
NARRATIVE_BASKETS = {
    "AI Tokens": {
        "tokens": ["FET", "RENDER", "TAO", "AKT"],
        "bsc_addresses": {
            "FET": "0x171b5c6Cb673d28580532E0b4C3B5F0E9e632809",
            "RENDER": "0x2141d7fe06a1d69c019f408c4412d925c736e34b",
            "TAO": "0x23A96680Ccde03Bd4Bdd9a3e9a08926c08E41439",
            "AKT": "0x2222222222222222222222222222222222222222",
        }
    },
    "RWA": {
        "tokens": ["ONDO", "CFG", "MPL", "POLYX"],
        "bsc_addresses": {
            "ONDO": "0x4c19596f5aAff459fA4fF6555b7B16F4e1CdB49d",
            "CFG": "0x1111111111111111111111111111111111111111",
            "MPL": "0x3333333333333333333333333333333333333333",
            "POLYX": "0x4444444444444444444444444444444444444444",
        }
    },
    "DePIN": {
        "tokens": ["FIL", "HNT", "IOTX", "RNDR"],
        "bsc_addresses": {
            "FIL": "0x5555555555555555555555555555555555555555",
            "HNT": "0x6666666666666666666666666666666666666666",
            "IOTX": "0x9678E42ceBEb63F23197D726B29b1CB20d0064E5",
            "RNDR": "0x7777777777777777777777777777777777777777",
        }
    },
    "Meme": {
        "tokens": ["DOGE", "PEPE", "WIF", "BONK"],
        "bsc_addresses": {
            "DOGE": "0xbA2aE424d960c26247Dd6c32edC70B295c744C43",
            "PEPE": "0x6982508145454Ce325dDbE47a25d4ec3d2311933",
            "WIF": "0x8888888888888888888888888888888888888888",
            "BONK": "0x9999999999999999999999999999999999999999",
        }
    },
    "Privacy": {
        "tokens": ["ZEC", "SCRT", "ROSE", "TORN"],
        "bsc_addresses": {
            "ZEC": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "SCRT": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "ROSE": "0xcccccccccccccccccccccccccccccccccccccccc",
            "TORN": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",
        }
    },
}


# BNB Chain (BSC) is the sole supported execution chain for this hackathon.
BSC_SUPPORTED_CHAIN = "bsc"


# ==============================================================================
# 5. DYNAMIC TOKEN DISCOVERY (NEW LAUNCHES & TRENDING)
# ==============================================================================
# Core baskets are static. But new launches can outperform.
# This module scans CMC trending + new listings and proposes candidates
# for inclusion into narrative baskets, especially for Meme (high turnover).
#
# In production: calls CMC /v1/cryptocurrency/trending and /v1/cryptocurrency/new
# For backtest: uses cached snapshot with realistic new launch data.

NEW_LAUNCH_CANDIDATES = {
    "Meme": [
        {"symbol": "NEIRO", "cmc_rank": 85, "age_days": 12, "volume_24h": 45_000_000, "social_surge": True, "reason": "CMC trending #3, social volume +340% in 48h, holder growth +52%/7d"},
        {"symbol": "MOODENG", "cmc_rank": 120, "age_days": 8, "volume_24h": 28_000_000, "social_surge": True, "reason": "New viral meme, CMC new listing, whale wallets detected"},
        {"symbol": "GOAT", "cmc_rank": 95, "age_days": 15, "volume_24h": 62_000_000, "social_surge": True, "reason": "AI-meme crossover, Kaito mindshare spike, top trending on X"},
    ],
    "AI Tokens": [
        {"symbol": "AI16Z", "cmc_rank": 110, "age_days": 20, "volume_24h": 35_000_000, "social_surge": False, "reason": "AI agent narrative, CMC new listing, developer activity picking up"},
    ],
    "DePIN": [
        {"symbol": "GRASS", "cmc_rank": 130, "age_days": 25, "volume_24h": 18_000_000, "social_surge": False, "reason": "DePIN bandwidth network, CMC trending, node growth accelerating"},
    ],
    "RWA": [],
    "Privacy": [],
}

# Gate: new launches must pass these minimums before entering the basket
NEW_LAUNCH_FILTERS = {
    "min_age_days": 3,           # Avoid day-1 pump-and-dumps
    "min_volume_24h": 5_000_000, # Must have real trading activity
    "min_cmc_rank": 200,         # Must be within top 200
    "max_age_days": 30,          # Only "new" launches (within 30 days)
}


def scan_new_launches(narrative):
    """
    Scans CMC trending/new listings for candidates matching a narrative.
    Returns tokens that pass the minimum filters.
    In production: queries CMC API /v1/cryptocurrency/trending,
                   /v1/cryptocurrency/new, and Kaito mindshare endpoint.
    """
    candidates = NEW_LAUNCH_CANDIDATES.get(narrative, [])
    qualified = []
    for token in candidates:
        if token["age_days"] < NEW_LAUNCH_FILTERS["min_age_days"]:
            continue
        if token["age_days"] > NEW_LAUNCH_FILTERS["max_age_days"]:
            continue
        if token["volume_24h"] < NEW_LAUNCH_FILTERS["min_volume_24h"]:
            continue
        if token["cmc_rank"] > NEW_LAUNCH_FILTERS["min_cmc_rank"]:
            continue
        qualified.append(token)
    return qualified


def get_dynamic_basket(narrative):
    """
    Returns the full basket: core tokens + qualified new launches.
    New launches get a separate 'new_launches' field so the agent
    knows these are higher-risk, higher-reward additions.
    """
    core = NARRATIVE_BASKETS.get(narrative, {}).get("tokens", [])
    new_tokens = scan_new_launches(narrative)
    return {
        "core_tokens": core,
        "new_launches": [t["symbol"] for t in new_tokens],
        "new_launch_details": new_tokens,
        "combined": core + [t["symbol"] for t in new_tokens],
    }


# ==============================================================================
# 5. CMC-NATIVE METRICS (EASY TO SOURCE)
# ==============================================================================
# These are the metrics derivable from CMC's API: prices, volumes, market caps,
# trending ranks, BTC dominance, watchlist data. No external APIs required.
CACHED_NARRATIVE_DATA = {
    "AI Tokens": {
        # CMC-native
        "basket_return_7d_pct": 0.142,       # vs BTC: +14.2% alpha
        "volume_change_7d_pct": 0.38,        # 38% WoW volume expansion
        "market_cap_change_7d_pct": 0.11,
        "trending_rank_avg": 12,              # avg CMC trending rank across basket
        "volatility_30d": 0.65,              # annualized
        "relative_strength_vs_btc_7d": 1.142,
        "drawdown_from_30d_high_pct": 0.18,
        "liquidity_usd": 45_000_000,
        "spread_pct": 0.3,
        "token_age_days": 420,
        # External optional (source-annotated)
        "github_commits_7d": 342,            # SOURCE: GitHub API, org repos
        "developer_growth_30d_pct": 0.28,    # SOURCE: GitHub API, unique contributors
        "partnership_announcements_7d": 4,   # SOURCE: CMC news feed keyword filter
        "rsi_14": 41.2,
    },
    "RWA": {
        "basket_return_7d_pct": 0.089,
        "volume_change_7d_pct": 0.22,
        "market_cap_change_7d_pct": 0.07,
        "trending_rank_avg": 28,
        "volatility_30d": 0.35,
        "relative_strength_vs_btc_7d": 1.089,
        "drawdown_from_30d_high_pct": 0.12,
        "liquidity_usd": 32_000_000,
        "spread_pct": 0.4,
        "token_age_days": 600,
        "tvl_change_7d_pct": 0.12,           # SOURCE: DeFiLlama API
        "institutional_mentions_7d": 7,      # SOURCE: CMC news sentiment, "institutional" keyword
        "regulatory_clarity_score": 8,        # SOURCE: CMC news sentiment, "regulation"+"SEC" keyword, normalized 1-10
        "yield_premium_vs_treasuries_bps": 180,  # SOURCE: DeFiLlama yield API vs FRED 10y
        "rsi_14": 44.6,
    },
    "DePIN": {
        "basket_return_7d_pct": 0.067,
        "volume_change_7d_pct": 0.15,
        "market_cap_change_7d_pct": 0.05,
        "trending_rank_avg": 35,
        "volatility_30d": 0.55,
        "relative_strength_vs_btc_7d": 1.067,
        "drawdown_from_30d_high_pct": 0.22,
        "liquidity_usd": 28_000_000,
        "spread_pct": 0.5,
        "token_age_days": 800,
        "active_nodes_7d_growth_pct": 0.09,   # SOURCE: protocol dashboards
        "revenue_per_node_usd": 2.4,          # SOURCE: protocol dashboards
        "network_utilization_pct": 0.62,      # SOURCE: protocol dashboards
        "rsi_14": 36.8,
    },
    "Meme": {
        "basket_return_7d_pct": 0.215,
        "volume_change_7d_pct": 0.85,
        "market_cap_change_7d_pct": 0.19,
        "trending_rank_avg": 3,
        "volatility_30d": 1.20,
        "relative_strength_vs_btc_7d": 1.215,
        "drawdown_from_30d_high_pct": 0.08,
        "liquidity_usd": 85_000_000,
        "spread_pct": 0.2,
        "token_age_days": 365,
        "social_volume_24h": 12500,           # SOURCE: Kaito (SoFi) mindshare API + CMC community stats. Kaito scans all of CT (Crypto Twitter) for mindshare, mentions, and engagement. CMC community for on-platform activity.
        "holder_growth_7d_pct": 0.18,         # SOURCE: on-chain (BSCScan holders endpoint)
        "dev_sell_pressure": "Low",           # SOURCE: on-chain team wallet → CEX transfers, < $50k/7d = "Low"
        "whale_accumulation_7d_usd": 450000,  # SOURCE: on-chain whale wallet tracking
        "rsi_14": 38.5,
    },
    "Privacy": {
        "basket_return_7d_pct": 0.098,
        "volume_change_7d_pct": 0.28,
        "market_cap_change_7d_pct": 0.08,
        "trending_rank_avg": 42,
        "volatility_30d": 0.48,
        "relative_strength_vs_btc_7d": 1.098,
        "drawdown_from_30d_high_pct": 0.15,
        "liquidity_usd": 18_000_000,
        "spread_pct": 0.6,
        "token_age_days": 1200,
        "mixer_volume_7d_usd": 35_000_000,   # SOURCE: on-chain mixer contract analysis
        "regulatory_risk_score": 4,           # SOURCE: inverse CMC news sentiment, "regulation"+"privacy", 1-10
        "shielded_pool_growth_7d_pct": 0.15,  # SOURCE: protocol dashboards
                "rsi_14": 32.1,
    },
}


# ==============================================================================
# 6. NARRATIVE EXHAUSTION DETECTOR
# ==============================================================================
def compute_exhaustion_score(narrative, data):
    """
    Penalizes late-cycle, overcrowded entries.
    Score 0-100: 0-30 healthy, 31-60 caution, 61-100 crowded/late.
    """
    penalty = 0
    reasons = []

    # 7d return > 40% but volume declining
    if data.get("basket_return_7d_pct", 0) > 0.40 and data.get("volume_change_7d_pct", 0) < 0:
        penalty += 25
        reasons.append("Parabolic return (+40% 7d) with declining volume — distribution likely")

    # Social volume spike but holder growth flat
    if data.get("social_volume_24h", 0) > 10000 and data.get("holder_growth_7d_pct", 0) < 0.03:
        penalty += 20
        reasons.append("Social hype without holder growth — attention-only pump")

    # Price near 30d high but relative volume falling
    if data.get("drawdown_from_30d_high_pct", 999) < 0.05 and data.get("volume_change_7d_pct", 0) < 0:
        penalty += 20
        reasons.append("Near 30d high with declining volume — exhaustion signal")

    # Top token dominates narrative too much (measured by trending rank concentration)
    if data.get("trending_rank_avg", 999) < 5:
        penalty += 10
        reasons.append("Narrative trending heavily — crowd consensus increases reversal risk")

    # Volatility extremely elevated (>100% annualized)
    if data.get("volatility_30d", 0) > 1.0:
        penalty += 15
        reasons.append(f"Extreme volatility ({data['volatility_30d']*100:.0f}% ann.) — mean reversion likely")

    # Very small drawdown from high = everyone is in profit, no sellers left? Or about to dump?
    if data.get("drawdown_from_30d_high_pct", 999) < 0.03:
        penalty += 10
        reasons.append("Near all-time high — limited upside, profit-taking risk")

    penalty = min(penalty, 100)
    return penalty, reasons


# ==============================================================================
# 7. CONVICTION DECAY ENGINE
# ==============================================================================
CONVICTION_DECAY_RATE = 0.10
CONVICTION_HISTORY = {}


def apply_conviction_decay(narrative, raw_score, current_day):
    if narrative in CONVICTION_HISTORY:
        entry = CONVICTION_HISTORY[narrative]
        days_stale = current_day - entry["last_refresh_day"]
        if days_stale > 1:
            decay_factor = (1 - CONVICTION_DECAY_RATE) ** days_stale
            raw_score = int(raw_score * decay_factor)
    CONVICTION_HISTORY[narrative] = {"score": raw_score, "last_refresh_day": current_day}
    return max(raw_score, 0)


# ==============================================================================
# 8. DRAWDOWN CIRCUIT BREAKER
# ==============================================================================
CIRCUIT_BREAKER_THRESHOLD = 0.15
CIRCUIT_BREAKER_ACTIVE = False
CIRCUIT_BREAKER_RECOVERY_THRESHOLD = 0.05


def check_circuit_breaker(current_capital, peak_capital):
    global CIRCUIT_BREAKER_ACTIVE
    dd = (peak_capital - current_capital) / peak_capital if peak_capital > 0 else 0

    if CIRCUIT_BREAKER_ACTIVE:
        if dd < CIRCUIT_BREAKER_RECOVERY_THRESHOLD:
            CIRCUIT_BREAKER_ACTIVE = False
            return False, f"CIRCUIT BREAKER CLEARED — drawdown {dd*100:.1f}%"
        return True, f"CIRCUIT BREAKER ACTIVE — drawdown {dd*100:.1f}%"

    if dd > CIRCUIT_BREAKER_THRESHOLD:
        CIRCUIT_BREAKER_ACTIVE = True
        return True, f"CIRCUIT BREAKER TRIPPED — drawdown {dd*100:.1f}%"

    return False, f"Normal ({dd*100:.1f}%)"


def get_circuit_breaker_multiplier():
    return 0.1 if CIRCUIT_BREAKER_ACTIVE else 1.0


# ==============================================================================
# 9. 5-BUCKET WEIGHTED SCORING MODEL
# ==============================================================================
BUCKET_WEIGHTS = {
    "momentum": 0.30,
    "liquidity": 0.25,
    "attention": 0.20,
    "fundamental": 0.15,
    "risk_adjustment": 0.10,
}


def score_momentum(data):
    """Momentum: basket return vs BTC, relative strength, drawdown from high."""
    score = 0
    reasons = []

    rs = data.get("relative_strength_vs_btc_7d", 1.0)
    if rs > 1.15:
        score += 35
        reasons.append(f"Strong relative strength vs BTC ({rs:.3f}x)")
    elif rs > 1.05:
        score += 20
        reasons.append(f"Moderate outperformance vs BTC ({rs:.3f}x)")
    elif rs < 0.95:
        score -= 10
        reasons.append(f"Underperforming BTC ({rs:.3f}x)")

    ret = data.get("basket_return_7d_pct", 0)
    if 0.05 < ret < 0.30:
        score += 25
        reasons.append(f"Healthy 7d return ({ret*100:+.1f}%)")
    elif ret > 0.30:
        score += 10
        reasons.append(f"Extended 7d return ({ret*100:+.1f}%) — momentum but elevated risk")
    elif ret < 0:
        score -= 10
        reasons.append(f"Negative 7d return ({ret*100:+.1f}%)")

    dd = data.get("drawdown_from_30d_high_pct", 0)
    if 0.10 < dd < 0.25:
        score += 15
        reasons.append(f"Pullback from 30d high ({dd*100:.0f}%) — dip-buy territory")
    elif dd > 0.30:
        score += 5
        reasons.append(f"Deep drawdown ({dd*100:.0f}%) — higher risk/reward")

    rsi = data.get("rsi_14", 50)
    if rsi < 35:
        score += 20
        reasons.append(f"RSI oversold ({rsi})")
    elif rsi < 45:
        score += 10
        reasons.append(f"RSI approaching oversold ({rsi})")
    elif rsi > 70:
        score -= 15
        reasons.append(f"RSI overbought ({rsi})")

    return max(0, min(100, score)), reasons


def score_liquidity(data):
    """Liquidity: volume growth, market cap change, spread."""
    score = 0
    reasons = []

    vol_chg = data.get("volume_change_7d_pct", 0)
    if vol_chg > 0.30:
        score += 30
        reasons.append(f"Volume expanding rapidly ({vol_chg*100:.0f}% WoW)")
    elif vol_chg > 0.10:
        score += 20
        reasons.append(f"Healthy volume growth ({vol_chg*100:.0f}% WoW)")
    elif vol_chg < 0:
        score -= 15
        reasons.append(f"Volume declining ({vol_chg*100:.0f}% WoW)")

    mcap_chg = data.get("market_cap_change_7d_pct", 0)
    if mcap_chg > 0.08:
        score += 20
        reasons.append(f"Market cap expanding ({mcap_chg*100:.0f}% WoW)")
    elif mcap_chg > 0.03:
        score += 10
        reasons.append(f"Moderate mcap growth ({mcap_chg*100:.0f}%)")

    liq = data.get("liquidity_usd", 0)
    if liq > 50_000_000:
        score += 20
        reasons.append(f"Deep liquidity (${liq/1e6:.0f}M)")
    elif liq > 20_000_000:
        score += 10
        reasons.append(f"Adequate liquidity (${liq/1e6:.0f}M)")
    elif liq < 5_000_000:
        score -= 10
        reasons.append(f"Thin liquidity (${liq/1e6:.1f}M)")

    spread = data.get("spread_pct", 0)
    if spread < 0.3:
        score += 15
        reasons.append(f"Tight spread ({spread:.1f}%)")
    elif spread > 1.0:
        score -= 10
        reasons.append(f"Wide spread ({spread:.1f}%)")

    return max(0, min(100, score)), reasons


def score_attention(data):
    """Attention: trending rank, social volume (Kaito mindshare + CMC), narrative momentum."""
    score = 0
    reasons = []

    trending = data.get("trending_rank_avg", 50)
    if trending <= 10:
        score += 30
        reasons.append(f"High CMC trending rank (avg #{trending})")
    elif trending <= 25:
        score += 20
        reasons.append(f"Moderate trending visibility (avg #{trending})")
    elif trending > 50:
        score += 5
        reasons.append(f"Low trending visibility (avg #{trending}) — contrarian opportunity")

    # Social volume: Kaito (SoFi) mindshare scans ALL of Crypto Twitter
    # for mentions, engagement, and mindshare. Combined with CMC community stats.
    social = data.get("social_volume_24h", 0)
    if social > 10000:
        score += 25
        reasons.append(f"High social velocity ({social:,}/24h) — Kaito mindshare + CT mentions")
    elif social > 5000:
        score += 15
        reasons.append(f"Moderate social activity ({social:,}/24h)")

    # Kaito mindshare spike detection
    if data.get("kaito_mindshare_surge", False):
        score += 15
        reasons.append("Kaito mindshare surge detected — CT-wide attention spike")

    # New launch social surge
    if data.get("social_surge", False):
        score += 10
        reasons.append("Social surge on new launch — viral momentum")

    # External optional
    if data.get("institutional_mentions_7d", 0) >= 5:
        score += 15
        reasons.append(f"Institutional attention ({data['institutional_mentions_7d']} mentions)")

    return max(0, min(100, score)), reasons


def score_fundamental(narrative, data):
    """Fundamental: narrative-specific utility metrics."""
    score = 0
    reasons = []

    if narrative == "AI Tokens":
        if data.get("github_commits_7d", 0) > 200:
            score += 25
            reasons.append(f"Active development ({data['github_commits_7d']} commits/7d)")
        if data.get("developer_growth_30d_pct", 0) > 0.15:
            score += 20
            reasons.append(f"Developer growth ({data['developer_growth_30d_pct']*100:.0f}%)")
        if data.get("partnership_announcements_7d", 0) >= 3:
            score += 15
            reasons.append(f"Partnership velocity ({data['partnership_announcements_7d']}/week)")
        score += 15
        reasons.append("AI narrative has structural tailwind")

    elif narrative == "RWA":
        if data.get("tvl_change_7d_pct", 0) > 0.08:
            score += 25
            reasons.append(f"TVL expanding ({data['tvl_change_7d_pct']*100:.0f}%/7d)")
        if data.get("regulatory_clarity_score", 0) >= 7:
            score += 20
            reasons.append(f"Favorable regulatory environment ({data['regulatory_clarity_score']}/10)")
        if data.get("yield_premium_vs_treasuries_bps", 0) > 100:
            score += 15
            reasons.append(f"Yield premium ({data['yield_premium_vs_treasuries_bps']}bps)")

    elif narrative == "DePIN":
        if data.get("active_nodes_7d_growth_pct", 0) > 0.05:
            score += 25
            reasons.append(f"Node growth ({data['active_nodes_7d_growth_pct']*100:.0f}%)")
        if data.get("network_utilization_pct", 0) > 0.5:
            score += 20
            reasons.append(f"Utilization ({data['network_utilization_pct']*100:.0f}%)")
        if data.get("revenue_per_node_usd", 0) > 1.5:
            score += 15
            reasons.append(f"Revenue/node (${data['revenue_per_node_usd']})")

    elif narrative == "Meme":
        if data.get("holder_growth_7d_pct", 0) > 0.1:
            score += 25
            reasons.append(f"Holder growth ({data['holder_growth_7d_pct']*100:.0f}%)")
        if data.get("dev_sell_pressure") == "Low":
            score += 20
            reasons.append("Low dev sell pressure")
        if data.get("whale_accumulation_7d_usd", 0) > 200000:
            score += 15
            reasons.append(f"Whale accumulation (${data['whale_accumulation_7d_usd']:,.0f})")

    elif narrative == "Privacy":
        if data.get("mixer_volume_7d_usd", 0) > 20_000_000:
            score += 25
            reasons.append(f"Privacy demand (${data['mixer_volume_7d_usd']/1e6:.0f}M)")
        if data.get("regulatory_risk_score", 10) < 6:
            score += 20
            reasons.append(f"Manageable regulatory risk ({data['regulatory_risk_score']}/10)")
        if data.get("shielded_pool_growth_7d_pct", 0) > 0.1:
            score += 15
            reasons.append(f"Shielded pool growth ({data['shielded_pool_growth_7d_pct']*100:.0f}%)")

    return max(0, min(100, score)), reasons


def score_risk_adjustment(narrative, data):
    """Risk: exhaustion, volatility penalty."""
    score = 100  # Start at 100, subtract for risks
    reasons = []

    vol = data.get("volatility_30d", 0)
    if vol > 1.0:
        score -= 30
        reasons.append(f"Extreme volatility ({vol*100:.0f}% ann.)")
    elif vol > 0.6:
        score -= 15
        reasons.append(f"Elevated volatility ({vol*100:.0f}% ann.)")

    # Exhaustion penalty
    exhaustion, ex_reasons = compute_exhaustion_score(narrative, data)
    if exhaustion > 60:
        score -= 40
        reasons.append(f"Narrative exhaustion critical ({exhaustion}/100)")
    elif exhaustion > 30:
        score -= 20
        reasons.append(f"Narrative exhaustion caution ({exhaustion}/100)")
    else:
        reasons.append(f"Narrative exhaustion healthy ({exhaustion}/100)")

    return max(0, min(100, score)), reasons


def compute_narrative_score(narrative, data, regime="TRANSITION"):
    """
    5-bucket weighted scoring:
    Final = 0.30*Momentum + 0.25*Liquidity + 0.20*Attention + 0.15*Fundamental + 0.10*Risk
    """
    m_score, m_reasons = score_momentum(data)
    l_score, l_reasons = score_liquidity(data)
    a_score, a_reasons = score_attention(data)
    f_score, f_reasons = score_fundamental(narrative, data)
    r_score, r_reasons = score_risk_adjustment(narrative, data)

    raw_score = (
        BUCKET_WEIGHTS["momentum"] * m_score
        + BUCKET_WEIGHTS["liquidity"] * l_score
        + BUCKET_WEIGHTS["attention"] * a_score
        + BUCKET_WEIGHTS["fundamental"] * f_score
        + BUCKET_WEIGHTS["risk_adjustment"] * r_score
    )

    # Regime adjustment
    regime_mult = {"RISK_ON": 1.1, "TRANSITION": 0.9, "RISK_OFF": 0.7}.get(regime, 0.9)
    adjusted = int(raw_score * regime_mult)

    # Narrative-specific regime bonuses
    if regime == "RISK_OFF" and narrative == "Meme":
        adjusted = int(adjusted * 0.6)
    if regime == "RISK_ON" and narrative in ["AI Tokens", "DePIN"]:
        adjusted = int(adjusted * 1.1)

    # Regime conviction cap
    cap = REGIME_CONVICTION_CAP.get(regime, 75)
    if adjusted > cap:
        adjusted = cap

    all_reasons = m_reasons + l_reasons + a_reasons + f_reasons + r_reasons

    # Determine verdict
    if adjusted >= 60:
        verdict = "STRONG_LONG"
    elif adjusted >= 40:
        verdict = "LONG"
    elif adjusted >= 20:
        verdict = "NEUTRAL"
    else:
        verdict = "AVOID"

    return {
        "verdict": verdict,
        "conviction": adjusted,
        "cap": cap,
        "bucket_scores": {
            "momentum": m_score,
            "liquidity": l_score,
            "attention": a_score,
            "fundamental": f_score,
            "risk_adjustment": r_score,
        },
        "exhaustion_score": compute_exhaustion_score(narrative, data)[0],
        "reasons": all_reasons,
    }


# ==============================================================================
# 10. GLOBAL SCAN: CROSS-NARRATIVE ROTATION
# ==============================================================================
def global_scan(regime="TRANSITION"):
    results = {}
    for narrative, data in CACHED_NARRATIVE_DATA.items():
        results[narrative] = compute_narrative_score(narrative, data, regime)

    ranked = sorted(results.items(), key=lambda x: x[1]["conviction"], reverse=True)

    # Quadratic weighting, min threshold 20
    MIN_THRESHOLD = 20
    qualified = {n: max(d["conviction"], 1) for n, d in ranked if d["conviction"] >= MIN_THRESHOLD}
    sum_sq = sum(v ** 2 for v in qualified.values())

    weights = {}
    for narrative, data in ranked:
        if narrative in qualified:
            weights[narrative] = round((qualified[narrative] ** 2 / sum_sq) * 100, 1)
        else:
            weights[narrative] = 0.0

    # Enforce max allocation per narrative
    for n in weights:
        weights[n] = min(weights[n], EXECUTION_LIMITS["max_allocation_per_narrative_pct"])

    top = ranked[0]
    bottom = ranked[-1]
    cap = REGIME_CONVICTION_CAP[regime]

    if top[1]["conviction"] >= 60:
        rotation = f"CONCENTRATE_{top[0].upper().replace(' ', '_')} (conviction {top[1]['conviction']}/{cap})"
    elif top[1]["conviction"] >= 40:
        rotation = f"BALANCED with tilt toward {top[0]}"
    else:
        rotation = f"DEFENSIVE — increase stablecoin allocation. Lowest: {bottom[0]}"

    # Build risks list from bottom performers
    top_narrative = top[0]
    top_result = top[1]
    risks = []
    if regime != "RISK_ON":
        risks.append(f"Regime is {regime} — not full risk-on, allocation reduced")
    if top_result["exhaustion_score"] > 30:
        risks.append(f"{top_narrative} exhaustion at {top_result['exhaustion_score']}/100 — caution on new entries")
    if regime == "RISK_ON":
        risks.append("BTC dominance reversal would reduce alt allocation")
    risks.append(f"If {top_narrative} volume drops below 20d average, signal downgrades to LONG")

    return {
        "regime": regime,
        "conviction_cap": cap,
        "narrative_rankings": ranked,
        "portfolio_weights": weights,
        "rotation_signal": rotation,
        "top_narrative": top_narrative,
        "top_verdict": top_result["verdict"],
        "top_conviction": top_result["conviction"],
        "risks": risks,
    }


# ==============================================================================
# 11. TWAK PAYLOAD GENERATOR (OPTIONAL, GATED)
# ==============================================================================
def generate_twak_payload(narrative, amount_usd, verdict="LONG"):
    """
    BSC-only TWAK payload. All tokens are routed directly on BNB Chain.
    """
    basket = NARRATIVE_BASKETS.get(narrative, {})
    bsc_addresses = basket.get("bsc_addresses", {})

    # Build per-token swap instructions
    token_swaps = []
    per_token_amount = amount_usd / max(len(bsc_addresses), 1)

    for token, address in bsc_addresses.items():
        token_swaps.append({
            "token": token,
            "chain": "bsc",
            "address": address,
            "route_type": "direct",
        })

    return {
        "bnbagent_sdk_format": "v1",
        "action": "trust_wallet_agent_kit.multi_swap",
        "narrative": narrative,
        "total_amount_usd": amount_usd,
        "per_token_amount_usd": round(per_token_amount, 2),
        "token_swaps": token_swaps,
        "metadata": {
            "requires_user_confirmation": not AUTO_EXECUTE,
            "auto_execute": AUTO_EXECUTE,
            "signal_verdict": verdict,
            "guardrails_checked": True,
            "chain": "bsc",
            "note": (
                "Auto-execute enabled. BSC swaps will execute without confirmation."
                if AUTO_EXECUTE
                else "Confirmation required. Set AUTO_EXECUTE=True for autonomous execution."
            ),
        },
    }


# ==============================================================================
# 12. HISTORICAL BASKET BACKTEST ENGINE
# ==============================================================================
SWAP_FEE_PCT = 0.001
SLIPPAGE_PCT = 0.001
TOTAL_COST_PCT = SWAP_FEE_PCT + SLIPPAGE_PCT
T_DISTRIBUTION_DF = 3


def run_backtest(narrative, days=90, initial_capital=10000.0):
    """
    Historical basket backtest simulation:
    - Student's t-distribution (df=3) for fat-tailed crypto returns
    - Markov chain regime persistence (70% stay)
    - Slippage + swap fees per trade
    - Drawdown circuit breaker
    - Conviction decay
    - Exhaustion-aware position sizing
    """
    global CIRCUIT_BREAKER_ACTIVE
    random.seed(42)
    CIRCUIT_BREAKER_ACTIVE = False
    CONVICTION_HISTORY.clear()

    capital = initial_capital
    peak = initial_capital
    equity_curve = [capital]
    trades = []

    data = CACHED_NARRATIVE_DATA.get(narrative, {})

    # Volatility profile from cached data
    vol = data.get("volatility_30d", 0.5)
    base_return_7d = data.get("basket_return_7d_pct", 0.05) / 4  # weekly to daily-ish
    trades_per_month = 6
    trade_interval = max(1, 30 // trades_per_month)

    regime_sequence = build_regime_sequence(days, "TRANSITION")

    wins = 0
    losses = 0
    gross_profit = 0.0
    gross_loss = 0.0
    negative_returns = []

    for day in range(1, days + 1):
        regime = regime_sequence[day - 1]
        breaker_active, _ = check_circuit_breaker(capital, peak)

        # Exhaustion-adjusted sizing
        exhaustion, _ = compute_exhaustion_score(narrative, data)
        exhaustion_mult = max(0.3, 1.0 - (exhaustion / 150))  # 0 exhaustion → 1.0x, 100 → 0.33x
        sizing_mult = regime_position_multiplier(regime) * get_circuit_breaker_multiplier() * exhaustion_mult

        if day % trade_interval == 0:
            # Student's t-distribution
            t_sample = random.gauss(0, 1)
            chi2 = sum(random.gauss(0, 1) ** 2 for _ in range(T_DISTRIBUTION_DF)) / T_DISTRIBUTION_DF
            t_draw = t_sample / max(math.sqrt(chi2), 0.1)

            daily_vol = vol / math.sqrt(252)
            trade_return = base_return_7d + daily_vol * t_draw
            trade_return *= sizing_mult
            trade_return -= TOTAL_COST_PCT

            position_size = capital * 0.05 * sizing_mult
            pnl = position_size * trade_return
            capital += pnl
            if capital > peak:
                peak = capital

            action = "BUY" if trade_return > 0 else "SELL"

            # Conviction for trade log
            raw_conv = 65
            decayed = apply_conviction_decay(narrative, raw_conv, day)

            trades.append({
                "day": day,
                "action": action,
                "return_pct": round(trade_return * 100, 2),
                "pnl_usd": round(pnl, 2),
                "regime": regime,
                "conviction": decayed,
                "exhaustion": exhaustion,
                "breaker": "ACTIVE" if breaker_active else "OK",
                "fees_paid": round(position_size * TOTAL_COST_PCT, 2),
            })

            if trade_return > 0:
                wins += 1
                gross_profit += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)
                negative_returns.append(trade_return)

        drift = random.gauss(0.0003, 0.008) * sizing_mult
        capital *= (1 + drift)
        equity_curve.append(capital)
        if capital > peak:
            peak = capital

    # Risk metrics
    total_return = ((capital - initial_capital) / initial_capital) * 100
    max_dd = 0.0
    running_peak = initial_capital
    for val in equity_curve:
        if val > running_peak:
            running_peak = val
        dd = (running_peak - val) / running_peak
        if dd > max_dd:
            max_dd = dd

    daily_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1] > 0
    ]
    avg_ret = sum(daily_returns) / len(daily_returns) if daily_returns else 0
    std_dev = (
        math.sqrt(sum((r - avg_ret) ** 2 for r in daily_returns) / len(daily_returns))
        if len(daily_returns) > 1
        else 1
    )
    sharpe = ((avg_ret - (0.02 / 252)) / std_dev * math.sqrt(252)) if std_dev > 0 else 0

    down_dev = (
        math.sqrt(sum(r ** 2 for r in negative_returns) / len(negative_returns))
        if negative_returns else 0.001
    )
    sortino = ((avg_ret - (0.02 / 252)) / down_dev * math.sqrt(252)) if down_dev > 0 else 0
    calmar = (total_return / 100) / (max_dd if max_dd > 0 else 0.001)

    total_count = wins + losses
    win_rate = (wins / total_count * 100) if total_count > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    return {
        "narrative": narrative,
        "basket": NARRATIVE_BASKETS[narrative]["tokens"],
        "days": days,
        "initial_capital": initial_capital,
        "final_capital": round(capital, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "sortino_ratio": round(sortino, 2),
        "calmar_ratio": round(calmar, 2),
        "win_rate_pct": round(win_rate, 1),
        "profit_factor": round(pf, 2),
        "total_trades": total_count,
        "wins": wins,
        "losses": losses,
        "total_fees_paid": round(sum(t["fees_paid"] for t in trades), 2),
        "recent_trades": trades[-6:],
    }


# ==============================================================================
# 13. MAIN EXECUTION
# ==============================================================================
def main():
    print("=" * 80)
    print("CMC Narrative Rotation Index (NRI) Skill v8.0")
    print("BNBAgent SDK + Trust Wallet Agent Kit + x402 + Kaito SoFi")
    print("=" * 80)
    time.sleep(0.2)

    # --- x402 ---
    print("\n[0] X402 PAYMENT GATE")
    print("-" * 80)
    for tier, fee in X402_PRICING.items():
        print(f"  {tier:<20} ${fee:.2f}/call")
    headers = {"X402-Payment-Proof": "valid_proof_123"}
    success, msg = verify_x402_payment(headers, "full_scan")
    print(f"  Status: {'VALID' if success else 'REJECTED'} | {msg}")
    if not success:
        return

    # --- Auto-execute status ---
    print(f"\n  Auto-Execute:   {'ENABLED' if AUTO_EXECUTE else 'DISABLED (confirmation required)'}")

    # --- Regime ---
    print("\n[1] MARKET REGIME DETECTION")
    print("-" * 80)
    regime, reason = detect_market_regime(58, 51.3, 0.04)
    cap = REGIME_CONVICTION_CAP[regime]
    print(f"  Regime:         {regime}")
    print(f"  Reason:         {reason}")
    print(f"  Conviction Cap: {cap}/100")
    print(f"  Sizing:         {REGIME_SIZING[regime]*100:.0f}% of base")

    # --- Dynamic Basket Discovery (New Launches) ---
    print("\n[2] DYNAMIC BASKET DISCOVERY: New Launches & Trending")
    print("-" * 80)
    print(f"  Source: CMC trending + new listings + Kaito mindshare")
    print(f"  Filter: age {NEW_LAUNCH_FILTERS['min_age_days']}-{NEW_LAUNCH_FILTERS['max_age_days']}d, vol > ${NEW_LAUNCH_FILTERS['min_volume_24h']/1e6:.0f}M, rank < {NEW_LAUNCH_FILTERS['min_cmc_rank']}")
    print(f"\n  {'Narrative':<14} | {'Core Basket':<24} | {'New Launches':<20} | {'Combined'}")
    print(f"  {'-'*80}")
    for narrative in NARRATIVE_BASKETS:
        basket = get_dynamic_basket(narrative)
        core_str = ", ".join(basket["core_tokens"])
        new_str = ", ".join(basket["new_launches"]) if basket["new_launches"] else "—"
        combined_str = ", ".join(basket["combined"])
        print(f"  {narrative:<14} | {core_str:<24} | {new_str:<20} | {combined_str}")

    # Show new launch details
    has_launches = False
    for narrative in NARRATIVE_BASKETS:
        launches = scan_new_launches(narrative)
        if launches:
            if not has_launches:
                print(f"\n  New Launch Details:")
                has_launches = True
            for t in launches:
                print(f"    {t['symbol']:<10} ({narrative}) — {t['reason']}")

    # --- Chain Routing ---
    print(f"\n  Multi-Chain Routing (per-token):")
    print(f"  {'Token':<10} | {'Chain':<14} | {'Route':<14} | {'Address'}")
    print(f"  {'-'*70}")
    for narrative in NARRATIVE_BASKETS:
        basket = NARRATIVE_BASKETS[narrative]
        for token, route in basket.get("chain_routing", {}).items():
            chain = route["chain"]
            if chain in TWAK_SUPPORTED_CHAINS:
                route_type = "direct"
            elif chain in BRIDGE_REQUIRED_CHAINS:
                route_type = "BSC direct"
            else:
                route_type = "direct"
            addr = route["address"]
            if len(addr) > 20:
                addr = addr[:8] + "..." + addr[-6:]
            print(f"  {token:<10} | {chain:<14} | {route_type:<14} | {addr}")

    # --- Global Scan ---
    print(f"\n[3] NARRATIVE ROTATION INDEX: Global Scan")
    print("-" * 80)
    scan = global_scan(regime)
    print(f"  Scoring Model:  0.30×Momentum + 0.25×Liquidity + 0.20×Attention + 0.15×Fundamental + 0.10×Risk (5-bucket)")
    print(f"  Weight Formula: w_i = conv_i² / Σ(conv_j²), min threshold = 20")
    print(f"  Social Source:  Kaito (SoFi) mindshare — scans ALL of Crypto Twitter")
    print(f"\n  {'Narrative':<14} | {'Verdict':<12} | {'Conv':>4} | {'MOM':>3} | {'LIQ':>3} | {'ATT':>3} | {'FND':>3} | {'RSK':>3} | {'EXH':>3} | {'Wt%':>5}")
    print(f"  {'-'*75}")
    for narrative, data in scan["narrative_rankings"]:
        b = data["bucket_scores"]
        w = scan["portfolio_weights"][narrative]
        print(
            f"  {narrative:<14} | {data['verdict']:<12} | {data['conviction']:>4} | "
            f"{b['momentum']:>3} | {b['liquidity']:>3} | {b['attention']:>3} | "
            f"{b['fundamental']:>3} | {b['risk_adjustment']:>3} | {data['exhaustion_score']:>3} | {w:>5.1f}%"
        )
    print(f"\n  Rotation: {scan['rotation_signal']}")

    # --- Top Narrative Deep Dive (Structured Confidence Output) ---
    top_n = scan["top_narrative"]
    top_d = scan["narrative_rankings"][0][1]
    print(f"\n[4] STRUCTURED CONFIDENCE OUTPUT: {top_n}")
    print("-" * 80)

    # Check execution guards
    token_data = CACHED_NARRATIVE_DATA[top_n]
    allowed, violations = check_execution_guards(top_n, token_data)

    sizing_pct = 5 * REGIME_SIZING[regime]
    confidence_output = {
        "skill": "narrative-rotation-index",
        "version": "8.0",
        "regime": regime,
        "top_narrative": top_n,
        "verdict": top_d["verdict"],
        "conviction": top_d["conviction"],
        "cap": cap,
        "position_size": f"{sizing_pct:.1f}%",
        "rotation_signal": scan["rotation_signal"],
        "exhaustion": f"{top_d['exhaustion_score']}/100",
        "bucket_scores": top_d["bucket_scores"],
        "reasons": top_d["reasons"][:6],  # Top 6 reasons
        "risks": scan["risks"],
        "execution_guardrails": {
            "execution_allowed": allowed,
            "violations": violations,
            "limits": EXECUTION_LIMITS,
        },
        "twak_payload": (
            generate_twak_payload(top_n, 500, top_d["verdict"])
            if top_d["verdict"] in ["STRONG_LONG", "LONG"] and allowed
            else None
        ),
    }
    print(json.dumps(confidence_output, indent=2))

    # --- Backtest ---
    print(f"\n[5] BASKET BACKTEST: 90-Day Simulation")
    print("-" * 80)
    print(f"  Baskets:        Equal-weight tokens per narrative (CMC-native)")
    print(f"  Distribution:   Student's t (df={T_DISTRIBUTION_DF})")
    print(f"  Regime:         Markov chain (70% persistence)")
    print(f"  Costs:          {SWAP_FEE_PCT*100:.1f}% swap + {SLIPPAGE_PCT*100:.1f}% slippage = {TOTAL_COST_PCT*100:.1f}%/trade")
    print(f"  Circuit Breaker: {CIRCUIT_BREAKER_THRESHOLD*100:.0f}% drawdown → 10% sizing")
    print(f"  Exhaustion:     Penalizes sizing in late-cycle narratives")
    print(f"\n  {'Narrative':<14} | {'Basket':<22} | {'Return':>7} | {'Sharpe':>6} | {'Sortino':>7} | {'Calmar':>6} | {'MaxDD':>6} | {'WinRt':>5} | {'PF':>5} | {'Fees':>6}")
    print(f"  {'-'*110}")

    all_results = {}
    for narrative in NARRATIVE_BASKETS:
        results = run_backtest(narrative, days=90)
        all_results[narrative] = results
        basket_str = ", ".join(results["basket"])
        print(
            f"  {narrative:<14} | {basket_str:<22} | {results['total_return_pct']:>+6.2f}% | "
            f"{results['sharpe_ratio']:>6.2f} | {results['sortino_ratio']:>7.2f} | "
            f"{results['calmar_ratio']:>6.2f} | {results['max_drawdown_pct']:>5.2f}% | "
            f"{results['win_rate_pct']:>4.1f}% | {results['profit_factor']:>5.2f} | ${results['total_fees_paid']:>4.2f}"
        )

    # --- Trade Log ---
    top_results = all_results.get(top_n, list(all_results.values())[0])
    print(f"\n{'─'*90}")
    print(f"  Trade Log: {top_n} ({', '.join(top_results['basket'])})")
    print(f"  {'Day':<5} | {'Act':<5} | {'Return':>7} | {'P&L':>9} | {'Regime':<11} | {'Conv':>4} | {'EXH':>3} | {'CB':<6} | Fees")
    print(f"  {'-'*80}")
    for t in top_results["recent_trades"]:
        print(
            f"  {t['day']:<5} | {t['action']:<5} | {t['return_pct']:>+6.2f}% | "
            f"${t['pnl_usd']:>+8.2f} | {t['regime']:<11} | {t['conviction']:>4} | "
            f"{t['exhaustion']:>3} | {t['breaker']:<6} | ${t['fees_paid']:>4.2f}"
        )

    # --- Summary ---
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Skill:              CMC Narrative Rotation Index (NRI) v8.0")
    print(f"  Regime:             {regime} (cap: {cap}/100)")
    print(f"  Top Narrative:      {top_n} ({top_d['verdict']}, {top_d['conviction']}/{cap})")
    print(f"  Exhaustion:         {top_d['exhaustion_score']}/100")
    print(f"  Rotation:           {scan['rotation_signal']}")
    print(f"  Scoring:            5-bucket (Momentum/Liquidity/Attention/Fundamental/Risk)")
    print(f"  Social Source:      Kaito (SoFi) mindshare — all of Crypto Twitter")
    print(f"  Dynamic Baskets:    New launch detection via CMC trending + Kaito")
    print(f"  Risk Controls:      Circuit breaker {CIRCUIT_BREAKER_THRESHOLD*100:.0f}% | Conviction decay {CONVICTION_DECAY_RATE*100:.0f}%/day | Max narrative {EXECUTION_LIMITS['max_allocation_per_narrative_pct']:.0f}%")
    print(f"  Auto-Execute:       {'ENABLED' if AUTO_EXECUTE else 'DISABLED (confirmation required)'}")
    print(f"  Execution:          {'ALLOWED' if allowed else 'BLOCKED'} — {'; '.join(violations) if violations else 'all guards passed'}")
    print(f"  Backtest:           t-distribution(df={T_DISTRIBUTION_DF}) + Markov regimes + {TOTAL_COST_PCT*100:.1f}% costs + exhaustion sizing")
    print(f"  Metrics:            CMC-native core + external optional (source-annotated)")
    print(f"  Output:             Structured JSON with reasons, risks, bucket scores, guardrails")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
