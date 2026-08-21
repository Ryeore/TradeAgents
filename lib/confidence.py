"""
Confidence scoring system for the stock-skills screener.

Separates "how attractive is this stock?" (raw_score) from
"how strong is the evidence?" (confidence_score).

Architecture
------------
confidence = f(completeness, historical_depth, freshness, quality, source_reliability)

Each pillar gets its own confidence decomposed into:
  - pillar_completeness:   weighted % of expected fields present
  - pillar_historical:     saturation of historical observations
  - pillar_freshness:      decay-weighted by data age
  - pillar_quality:        consistency & source corroboration
  - pillar_source:         reliability multiplier per data origin

Stock-level confidence is a weighted blend of pillar confidences,
with critical-data overrides that can independently cap confidence.
"""
from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Default configuration — all tunable via CONFIDENCE_CONFIG overrides
# ---------------------------------------------------------------------------

CONFIDENCE_CONFIG: dict[str, Any] = {
    # --- Completeness ---
    # Exponent for the nonlinear missing-data penalty (default > 1.0 makes
    # multiple gaps increasingly painful). Lower = gentler, higher = harsher.
    "missing_data_exponent": 1.8,

    # --- Historical depth ---
    # k parameter for saturation: confidence_component = 1 - exp(-k * observations)
    # Smaller k = more observations needed to reach ceiling.
    "historical_k": 0.12,
    # Target observations for full historical confidence (used for scaling).
    "target_observations": {
        "financials": 40,   # 10 years of quarterly data
        "price": 252,        # 1 year of daily data
        "analyst": 8,        # quarters of analyst coverage
    },

    # --- Freshness ---
    # Half-life in days: after this many days, freshness decays to 0.5.
    "freshness_half_life_days": {
        "price": 1,          # price data is stale after a day
        "technical": 5,      # technicals decay in ~a week
        "quarterly": 90,     # quarterly data good for ~3 months
        "annual": 365,       # annual data good for ~1 year
        "analyst": 30,       # analyst estimates ~1 month
        "macro": 30,         # macro data ~1 month
        "ownership": 90,     # institutional holdings ~quarterly
    },

    # --- Weights for overall confidence blend ---
    "completeness_weight": 0.35,
    "historical_weight": 0.25,
    "freshness_weight": 0.15,
    "quality_weight": 0.15,
    "source_weight": 0.10,

    # --- Source reliability (0-1) ---
    "source_reliability": {
        "yfinance": 0.80,        # good but can lag / have gaps
        "biznesradar": 0.75,     # WSE specialist but scraped HTML
        "yahoo_analyst": 0.75,   # consensus can be stale
        "derived": 0.60,         # computed from raw data
    },

    # --- Critical data penalty ---
    # If any critical field is missing, confidence is multiplied by this cap.
    # Each additional missing critical field compounds.
    "critical_data_penalty": 0.75,
    # Fields whose absence triggers the critical penalty.
    "critical_fields": [
        "pe_forward",
        "revenue_growth_pct",
        "return_12m_pct",
        "rsi14",
        "ma200",
        "atr_pct_of_price",
    ],

    # --- How confidence adjusts the final score ---
    # adjusted_score = raw_score * (confidence_weight * confidence + (1-confidence_weight) * 1.0)
    # 0.0 = confidence has no effect; 1.0 = full confidence scaling
    "confidence_weight": 0.55,
}

# Pillar definitions: maps each scoring pillar to the feature keys that
# contribute to it, with importance weights.
PILLAR_FIELDS: dict[str, dict[str, float]] = {
    "value": {
        "analyst_upside_pct": 0.25,
        "pe_forward": 0.30,
        "price_to_book": 0.20,
        "dividend_yield_pct": 0.10,
        "fcf_yield_pct": 0.15,
    },
    "quality": {
        "roe_pct": 0.30,
        "revenue_growth_pct": 0.25,
        "operating_margin_pct": 0.25,
        "gross_margin_pct": 0.20,
        # piotroski_f_score is optional (WSE only) — not required
    },
    "trend": {
        "return_3m_pct": 0.15,
        "return_6m_pct": 0.15,
        "return_12m_pct": 0.15,
        "price_vs_ma200_pct": 0.10,
        "ma50_vs_ma200_pct": 0.10,
        "ma200_slope_3m_pct": 0.10,
        "rsi14": 0.10,
        "ma20": 0.05,
        "ma50": 0.05,
        "ma200": 0.05,
        "proximity_52w_high_pct": 0.05,
    },
    "sentiment": {
        "recommendation_mean": 0.35,
        "analyst_opinions": 0.30,
        "short_interest_pct_float": 0.35,
    },
    "risk": {
        "atr_pct_of_price": 0.35,
        "max_drawdown_6m_pct": 0.35,
        "beta": 0.30,
        # altman_health_score is optional (WSE only) — not required
    },
}

# Data age categories for each field (used by freshness calculation).
# None means "no freshness data available — use default".
FIELD_DATA_CATEGORY: dict[str, str | None] = {
    "analyst_upside_pct": "analyst",
    "pe_forward": "quarterly",
    "price_to_book": "quarterly",
    "dividend_yield_pct": "quarterly",
    "fcf_yield_pct": "quarterly",
    "roe_pct": "quarterly",
    "revenue_growth_pct": "quarterly",
    "operating_margin_pct": "quarterly",
    "gross_margin_pct": "quarterly",
    "return_3m_pct": "technical",
    "return_6m_pct": "technical",
    "return_12m_pct": "technical",
    "price_vs_ma200_pct": "technical",
    "ma50_vs_ma200_pct": "technical",
    "ma200_slope_3m_pct": "technical",
    "rsi14": "technical",
    "ma20": "technical",
    "ma50": "technical",
    "ma200": "technical",
    "proximity_52w_high_pct": "technical",
    "atr14": "technical",
    "atr_pct_of_price": "technical",
    "max_drawdown_6m_pct": "technical",
    "beta": "quarterly",
    "recommendation_mean": "analyst",
    "analyst_opinions": "analyst",
    "short_interest_pct_float": "analyst",
    "avg_volume": "technical",
    "avg_dollar_volume": "technical",
    "above_ma50": "technical",
    "above_ma200": "technical",
    "piotroski_f_score": "annual",
    "altman_health_score": "annual",
}

# Source provenance for each field.
FIELD_SOURCE: dict[str, str] = {
    # All yfinance info-dict fields default to "yfinance"
    # biznesradar-enriched fields override below
    "piotroski_f_score": "biznesradar",
    "altman_health_score": "biznesradar",
}
# Default source for fields not listed:
DEFAULT_FIELD_SOURCE = "yfinance"


# ---------------------------------------------------------------------------
# Validation helper — treat NaN same as None
# ---------------------------------------------------------------------------
def _is_valid(value: Any) -> bool:
    """Return True if value is a usable, non-NaN, non-None data point."""
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    return True


# ---------------------------------------------------------------------------
# Confidence calculation functions
# ---------------------------------------------------------------------------

def pillar_completeness(
    features: dict[str, Any],
    pillar: str,
    is_us: bool = True,
    config: dict | None = None,
) -> float:
    """Weighted completeness for one scoring pillar.

    Returns a value in [0, 1] where 1.0 = all expected fields present.
    Non-required fields (e.g. short_interest for non-US, piotroski for US)
    are excluded from the denominator.
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    exponent = cfg.get("missing_data_exponent", 1.8)
    field_weights = PILLAR_FIELDS.get(pillar, {})

    total_weight = 0.0
    present_weight = 0.0

    for field, weight in field_weights.items():
        # Skip US-only fields for non-US listings (short interest)
        if field == "short_interest_pct_float" and not is_us:
            continue
        # Skip WSE-only fields for US listings
        if field == "piotroski_f_score" and is_us:
            continue
        if field == "altman_health_score" and is_us:
            continue

        total_weight += weight
        if _is_valid(features.get(field)):
            present_weight += weight

    if total_weight == 0:
        return 0.0

    # Weighted completeness ratio
    completeness = present_weight / total_weight

    # Apply nonlinear penalty: confidence = base_completeness ^ exponent
    # This makes sparse data increasingly painful
    return completeness ** exponent


def pillar_historical_depth(
    features: dict[str, Any],
    pillar: str,
    config: dict | None = None,
) -> float:
    """Estimate historical data depth for a pillar using available signals.

    Uses saturation:  confidence = 1 - exp(-k * effective_observations)
    where effective_observations is estimated from available data indicators.

    Returns a value in [0, 1].
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    k = cfg.get("historical_k", 0.12)
    targets = cfg.get("target_observations", {})

    # Estimate observations based on pillar type
    if pillar == "trend":
        # Count how many of the multi-period returns are available
        count = 0
        for field in ["return_3m_pct", "return_6m_pct", "return_12m_pct"]:
            if _is_valid(features.get(field)):
                count += 1
        # Also check if MAs exist (implies sufficient price history)
        if _is_valid(features.get("ma200")):
            count += 1  # MA200 implies >= 200 days of history
        if _is_valid(features.get("ma50")):
            count += 0.5
        effective = count * (targets.get("price", 252) / 4)
    elif pillar == "risk":
        count = 0
        if _is_valid(features.get("atr14")):
            count += 1
        if _is_valid(features.get("max_drawdown_6m_pct")):
            count += 1
        if _is_valid(features.get("beta")):
            count += 0.5
        effective = count * (targets.get("price", 252) / 3)
    elif pillar in ("value", "quality"):
        # Count fundamental fields present
        count = 0
        for field in PILLAR_FIELDS.get(pillar, {}):
            if _is_valid(features.get(field)):
                count += 1
        # Scale: each fundamental field ~ 4 quarters of data
        effective = count * (targets.get("financials", 40) / max(len(PILLAR_FIELDS.get(pillar, {})), 1))
    elif pillar == "sentiment":
        count = 0
        if _is_valid(features.get("analyst_opinions")):
            count += 1
        if _is_valid(features.get("recommendation_mean")):
            count += 1
        effective = count * (targets.get("analyst", 8) / 2)
    else:
        effective = 0

    # Saturation function: approaches 1.0 asymptotically
    return 1.0 - math.exp(-k * effective)


def pillar_freshness(
    features: dict[str, Any],
    pillar: str,
    config: dict | None = None,
) -> float:
    """Estimate data freshness for a pillar.

    Uses configured half-lives per data category. Since we don't track
    exact timestamps for each yfinance field, we use a best-effort
    estimate based on the most freshness-sensitive fields in the pillar.

    Returns a value in [0, 1].
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    half_lives = cfg.get("freshness_half_life_days", {})
    field_weights = PILLAR_FIELDS.get(pillar, {})

    if not field_weights:
        return 0.5  # neutral for unknown pillars

    total_weight = 0.0
    weighted_freshness = 0.0

    for field, weight in field_weights.items():
        if not _is_valid(features.get(field)):
            continue

        category = FIELD_DATA_CATEGORY.get(field, "quarterly")
        half_life = half_lives.get(category, 90)

        # Since we don't have per-field timestamps from yfinance info dict,
        # we estimate: if the field is present, it's at most half_life old.
        # Default: assume data is ~half_life/2 old (midpoint freshness).
        # This is a conservative estimate that rewards fields from categories
        # with shorter half-lives (price, technical) more.
        estimated_age_days = half_life * 0.3  # assume 30% of half-life age
        freshness = 2 ** (-estimated_age_days / half_life)  # ~0.8 for midpoint

        total_weight += weight
        weighted_freshness += freshness * weight

    if total_weight == 0:
        return 0.3  # low freshness if no data

    return weighted_freshness / total_weight


def pillar_quality(
    features: dict[str, Any],
    pillar: str,
    biznesradar_enriched: bool = False,
    biznesradar_sourced: list[str] | None = None,
    config: dict | None = None,
) -> float:
    """Estimate data quality for a pillar.

    Considers: source corroboration (biznesradar + yfinance = higher quality
    when values agree), absence of suspicious zero-values, and source diversity.

    Returns a value in [0, 1].
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    field_weights = PILLAR_FIELDS.get(pillar, {})

    if not field_weights:
        return 0.5

    total_weight = 0.0
    weighted_quality = 0.0

    for field, weight in field_weights.items():
        val = features.get(field)
        if not _is_valid(val):
            total_weight += weight
            weighted_quality += 0.0 * weight  # missing = no quality
            continue

        base_quality = 0.85  # yfinance default quality

        # Penalize suspiciously round zero values (NaN already filtered above)
        if isinstance(val, (int, float)) and abs(val) < 1e-9:
            base_quality = 0.3

        # Bonus for biznesradar corroboration (independent source)
        sourced = biznesradar_sourced or []
        if biznesradar_enriched and field in ("roe_pct", "price_to_book") and field in sourced:
            # Two independent sources agree — quality boost
            base_quality = min(1.0, base_quality + 0.10)

        total_weight += weight
        weighted_quality += base_quality * weight

    if total_weight == 0:
        return 0.0

    return weighted_quality / total_weight


def pillar_source_reliability(
    features: dict[str, Any],
    pillar: str,
    biznesradar_enriched: bool = False,
    config: dict | None = None,
) -> float:
    """Estimate source reliability for a pillar's data.

    Weighted average of source reliability per field.

    Returns a value in [0, 1].
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    source_rels = cfg.get("source_reliability", {})
    field_weights = PILLAR_FIELDS.get(pillar, {})

    if not field_weights:
        return 0.5

    total_weight = 0.0
    weighted_rel = 0.0

    for field, weight in field_weights.items():
        source = FIELD_SOURCE.get(field, DEFAULT_FIELD_SOURCE)
        rel = source_rels.get(source, 0.7)

        # Boost slightly if biznesradar enrichment is active (dual source)
        if biznesradar_enriched and source == "biznesradar":
            rel = min(1.0, rel + 0.05)

        total_weight += weight
        # If field is missing, source reliability is irrelevant (no data to trust)
        if _is_valid(features.get(field)):
            weighted_rel += rel * weight
        # Missing fields don't contribute to source reliability

    if total_weight == 0:
        return 0.5

    return weighted_rel / total_weight


def pillar_confidence(
    features: dict[str, Any],
    pillar: str,
    is_us: bool = True,
    biznesradar_enriched: bool = False,
    biznesradar_sourced: list[str] | None = None,
    config: dict | None = None,
) -> dict[str, float]:
    """Compute per-pillar confidence with all sub-components.

    Returns dict with decomposed confidence and overall pillar confidence.
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}

    completeness = pillar_completeness(features, pillar, is_us, cfg)
    historical = pillar_historical_depth(features, pillar, cfg)
    freshness = pillar_freshness(features, pillar, cfg)
    quality = pillar_quality(features, pillar, biznesradar_enriched, biznesradar_sourced, cfg)
    source = pillar_source_reliability(features, pillar, biznesradar_enriched, cfg)

    # Weighted blend
    w_comp = cfg.get("completeness_weight", 0.35)
    w_hist = cfg.get("historical_weight", 0.25)
    w_fresh = cfg.get("freshness_weight", 0.15)
    w_qual = cfg.get("quality_weight", 0.15)
    w_src = cfg.get("source_weight", 0.10)

    overall = (
        completeness * w_comp
        + historical * w_hist
        + freshness * w_fresh
        + quality * w_qual
        + source * w_src
    )

    return {
        "completeness": round(completeness, 3),
        "historical_depth": round(historical, 3),
        "freshness": round(freshness, 3),
        "quality": round(quality, 3),
        "source_reliability": round(source, 3),
        "overall": round(overall, 3),
    }


def compute_confidence(
    features: dict[str, Any],
    is_us: bool = True,
    biznesradar_enriched: bool = False,
    biznesradar_sourced: list[str] | None = None,
    config: dict | None = None,
) -> dict[str, Any]:
    """Compute full multi-dimensional confidence for a stock.

    Parameters
    ----------
    features : dict
        Flat feature dict from collect_features().
    is_us : bool
        Whether the stock is US-listed (affects which fields are required).
    biznesradar_enriched : bool
        Whether biznesradar data was used.
    biznesradar_sourced : list[str] or None
        Fields backfilled from biznesradar.
    config : dict or None
        Overrides for CONFIDENCE_CONFIG.

    Returns
    -------
    dict with:
        - confidence_score: 0-100 overall confidence
        - confidence_level: "Very High" / "High" / "Moderate" / "Low" / "Very Low"
        - pillar_confidence: per-pillar breakdown
        - data_confidence: decomposed sub-scores
        - critical_penalty_applied: bool
        - missing_critical: list of missing critical field names
        - missing_data: list of all missing required field names
        - confidence_explanations: human-readable reasons
    """
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    pillars = ["value", "quality", "trend", "sentiment", "risk"]

    pillar_confs = {}
    for p in pillars:
        pillar_confs[p] = pillar_confidence(
            features, p, is_us, biznesradar_enriched, biznesradar_sourced, cfg
        )

    # Overall confidence = average of pillar confidences
    # This prevents one data-rich pillar from hiding a data-poor one
    pillar_overalls = [pillar_confs[p]["overall"] for p in pillars]
    base_confidence = sum(pillar_overalls) / len(pillar_overalls)

    # Critical data check
    critical_fields = cfg.get("critical_fields", [])
    critical_penalty = cfg.get("critical_data_penalty", 0.75)
    missing_critical = [f for f in critical_fields if not _is_valid(features.get(f))]
    critical_mult = critical_penalty ** len(missing_critical) if missing_critical else 1.0

    overall_confidence = base_confidence * critical_mult

    # Collect all missing fields across pillars
    all_missing = []
    for p in pillars:
        for field in PILLAR_FIELDS.get(p, {}):
            if field == "short_interest_pct_float" and not is_us:
                continue
            if not _is_valid(features.get(field)):
                all_missing.append(f"{p}:{field}")

    # Build explanations
    explanations = []
    if overall_confidence >= 0.90:
        explanations.append("Extensive evidence across all pillars")
    elif overall_confidence >= 0.75:
        explanations.append("Solid evidence with minor gaps")
    elif overall_confidence >= 0.55:
        explanations.append("Moderate evidence; some information gaps exist")
    elif overall_confidence >= 0.35:
        explanations.append("Sparse evidence; significant data gaps")
    else:
        explanations.append("Very sparse evidence; low certainty")

    # Identify weakest pillar
    weakest = min(pillars, key=lambda p: pillar_confs[p]["overall"])
    weakest_overall = pillar_confs[weakest]["overall"]
    if weakest_overall < 0.5:
        explanations.append(f"Weakest pillar: {weakest} ({weakest_overall:.0%} completeness)")

    if missing_critical:
        explanations.append(
            f"Missing critical fields: {', '.join(missing_critical)} "
            f"(confidence ×{critical_mult:.2f})"
        )

    # Confidence level label
    conf_pct = overall_confidence * 100
    if conf_pct >= 90:
        level = "Very High"
    elif conf_pct >= 75:
        level = "High"
    elif conf_pct >= 55:
        level = "Moderate"
    elif conf_pct >= 35:
        level = "Low"
    else:
        level = "Very Low"

    return {
        "confidence_score": round(conf_pct, 1),
        "confidence_level": level,
        "pillar_confidence": {
            p: {
                "overall": round(pillar_confs[p]["overall"] * 100, 1),
                "completeness": round(pillar_confs[p]["completeness"] * 100, 1),
                "historical_depth": round(pillar_confs[p]["historical_depth"] * 100, 1),
                "freshness": round(pillar_confs[p]["freshness"] * 100, 1),
                "quality": round(pillar_confs[p]["quality"] * 100, 1),
                "source_reliability": round(pillar_confs[p]["source_reliability"] * 100, 1),
            }
            for p in pillars
        },
        "data_confidence": {
            "completeness": round(
                sum(pillar_confs[p]["completeness"] for p in pillars) / len(pillars) * 100, 1
            ),
            "historical_depth": round(
                sum(pillar_confs[p]["historical_depth"] for p in pillars) / len(pillars) * 100, 1
            ),
            "freshness": round(
                sum(pillar_confs[p]["freshness"] for p in pillars) / len(pillars) * 100, 1
            ),
            "quality": round(
                sum(pillar_confs[p]["quality"] for p in pillars) / len(pillars) * 100, 1
            ),
            "source_reliability": round(
                sum(pillar_confs[p]["source_reliability"] for p in pillars) / len(pillars) * 100, 1
            ),
            "critical_data_completeness": round(
                (len(critical_fields) - len(missing_critical)) / max(len(critical_fields), 1) * 100, 1
            ),
        },
        "critical_penalty_applied": len(missing_critical) > 0,
        "missing_critical": missing_critical,
        "missing_data": all_missing,
        "confidence_explanations": explanations,
    }


def confidence_adjust(raw_score: float | None, confidence_score: float, config: dict | None = None) -> float | None:
    """Apply confidence adjustment to a raw score.

    Uses a configurable blend: adjusted = raw * (cw * conf + (1-cw) * 1.0)
    where cw = confidence_weight.

    This ensures:
    - At conf=0, score is reduced by (1-cw) proportion
    - At conf=1, score is unchanged
    - The adjustment is linear between those extremes
    """
    if raw_score is None:
        return None
    cfg = {**CONFIDENCE_CONFIG, **(config or {})}
    cw = cfg.get("confidence_weight", 0.55)
    conf_frac = confidence_score / 100.0
    multiplier = cw * conf_frac + (1.0 - cw) * 1.0
    return round(raw_score * multiplier, 1)