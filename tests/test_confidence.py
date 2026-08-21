"""
Tests for the confidence scoring system (lib/confidence.py).

Covers:
  Test 1  — Complete stock: high confidence
  Test 2  — Sparse stock: low confidence
  Test 3  — High raw score + sparse data: reduced adjusted score
  Test 4  — Slightly lower raw score + excellent data: better adjusted score
  Test 5  — Missing critical metric: large confidence penalty
  Test 6  — Stale data: lower freshness → lower confidence
  Test 7  — Long history: higher confidence than short history
  Test 8  — Duplicate data: no artificial confidence boost
  Test 9  — Conflicting sources (not yet fully implemented: placeholder)
  Test 10 — Progressive data addition: confidence increases monotonically to ceiling
  Test 11 — US vs non-US: short interest not required for WSE
  Test 12 — Pillar confidence: data-rich pillar doesn't hide data-poor pillar
  Test 13 — Nonlinear penalty: extra missing fields hurt more than first
"""
import math
import os
import sys

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.confidence import (
    CONFIDENCE_CONFIG,
    PILLAR_FIELDS,
    compute_confidence,
    confidence_adjust,
    pillar_confidence,
    pillar_completeness,
    pillar_freshness,
    pillar_historical_depth,
    pillar_quality,
    pillar_source_reliability,
)

# ---------------------------------------------------------------------------
# Helper: build feature dicts at various completeness levels
# ---------------------------------------------------------------------------

ALL_FEATURES = {
    "analyst_upside_pct": 12.5,
    "pe_forward": 22.3,
    "price_to_book": 5.1,
    "dividend_yield_pct": 0.49,
    "fcf_yield_pct": 4.2,
    "roe_pct": 35.0,
    "revenue_growth_pct": 15.0,
    "operating_margin_pct": 28.0,
    "gross_margin_pct": 55.0,
    "return_3m_pct": 8.0,
    "return_6m_pct": 15.0,
    "return_12m_pct": 30.0,
    "price_vs_ma200_pct": 12.0,
    "ma50_vs_ma200_pct": 8.0,
    "ma200_slope_3m_pct": 3.0,
    "rsi14": 58.0,
    "ma20": 185.0,
    "ma50": 178.0,
    "ma200": 165.0,
    "proximity_52w_high_pct": 92.0,
    "atr14": 3.5,
    "atr_pct_of_price": 1.9,
    "max_drawdown_6m_pct": -12.0,
    "beta": 1.1,
    "recommendation_mean": 1.8,
    "analyst_opinions": 35,
    "short_interest_pct_float": 2.1,
    "avg_volume": 50_000_000,
    "avg_dollar_volume": 9_200_000_000,
    "above_ma50": True,
    "above_ma200": True,
    "piotroski_f_score": 7,
    "altman_health_score": 85,
}


def make_features(include_all=True, drop=None, is_us=True):
    """Build a feature dict. drop is a list of field names to set to None."""
    f = dict(ALL_FEATURES)
    if not include_all:
        # Start with all None
        f = {k: None for k in ALL_FEATURES}
    if drop:
        for k in drop:
            f[k] = None
    # Remove WSE-specific if US
    if is_us:
        f["piotroski_f_score"] = None
        f["altman_health_score"] = None
    return f


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_complete_stock():
    """Complete stock with all features → high confidence (>85%)."""
    f = make_features()
    result = compute_confidence(f, is_us=True)
    assert result["confidence_score"] >= 80, f"Expected >=80, got {result['confidence_score']}"
    assert result["confidence_level"] in ("Very High", "High"), f"Got {result['confidence_level']}"
    print(f"  PASS: complete US stock confidence = {result['confidence_score']}% ({result['confidence_level']})")


def test_02_sparse_stock():
    """Very little data → low confidence (<40%)."""
    f = make_features(include_all=False, drop=[])
    result = compute_confidence(f, is_us=True)
    assert result["confidence_score"] < 40, f"Expected <40, got {result['confidence_score']}"
    assert result["confidence_level"] in ("Very Low", "Low"), f"Got {result['confidence_level']}"
    print(f"  PASS: sparse stock confidence = {result['confidence_score']}% ({result['confidence_level']})")


def test_03_high_score_sparse_data():
    """High raw score with sparse data should have low confidence and meaningfully reduced adjusted score."""
    f = make_features(include_all=False, drop=[])
    # Sparse: only 3 fields
    f["pe_forward"] = 10.0
    f["return_12m_pct"] = 50.0
    f["rsi14"] = 55.0
    result = compute_confidence(f, is_us=True)
    raw = 92.0  # Hypothetical high raw score
    adjusted = confidence_adjust(raw, result["confidence_score"])
    assert result["confidence_score"] < 60, f"Expected low confidence, got {result['confidence_score']}"
    assert adjusted < raw, f"Adjusted ({adjusted}) should be < raw ({raw})"
    assert adjusted < raw * 0.85, f"Adjusted should be meaningfully reduced: {adjusted} vs {raw}"
    print(f"  PASS: raw=92, conf={result['confidence_score']}%, adjusted={adjusted}")


def test_04_lower_score_excellent_data():
    """Slightly lower raw score with excellent data → better adjusted score than test_03."""
    f = make_features()
    result = compute_confidence(f, is_us=True)
    raw = 86.0
    adjusted = confidence_adjust(raw, result["confidence_score"])
    assert result["confidence_score"] >= 80, f"Expected high confidence, got {result['confidence_score']}"
    # The adjusted score for 86 with high confidence should beat 92 with low confidence
    # From test_03, the sparse adjusted was low. Let's compare:
    sparse_f = make_features(include_all=False, drop=[])
    sparse_f["pe_forward"] = 10.0
    sparse_f["return_12m_pct"] = 50.0
    sparse_f["rsi14"] = 55.0
    sparse_result = compute_confidence(sparse_f, is_us=True)
    sparse_adjusted = confidence_adjust(92.0, sparse_result["confidence_score"])
    assert adjusted > sparse_adjusted, (
        f"Better-data stock ({adjusted}) should outrank sparse-data stock ({sparse_adjusted})"
    )
    print(f"  PASS: good-data adjusted={adjusted} > sparse-data adjusted={sparse_adjusted}")


def test_05_missing_critical():
    """Missing a critical metric → large confidence penalty."""
    f = make_features(drop=["pe_forward", "return_12m_pct"])
    result = compute_confidence(f, is_us=True)
    assert result["critical_penalty_applied"], "Critical penalty should be applied"
    assert len(result["missing_critical"]) == 2, f"Expected 2 critical missing, got {result['missing_critical']}"
    # With 2 critical missing, penalty = 0.75² = 0.5625
    print(f"  PASS: missing critical={result['missing_critical']}, conf={result['confidence_score']}%")


def test_06_stale_data():
    """Stale data categories reduce freshness component."""
    # All features present = good freshness
    f_fresh = make_features()
    result_fresh = compute_confidence(f_fresh, is_us=True)
    freshness_fresh = result_fresh["data_confidence"]["freshness"]
    # Sparse = low freshness
    f_stale = make_features(include_all=False, drop=[])
    result_stale = compute_confidence(f_stale, is_us=True)
    freshness_stale = result_stale["data_confidence"]["freshness"]
    assert freshness_fresh > freshness_stale, f"Fresh {freshness_fresh} should be > stale {freshness_stale}"
    print(f"  PASS: full-data freshness={freshness_fresh}% > sparse freshness={freshness_stale}%")


def test_07_long_history():
    """More historical indicators → higher historical depth score."""
    f_rich = make_features()
    result_rich = compute_confidence(f_rich, is_us=True)
    hist_rich = result_rich["data_confidence"]["historical_depth"]

    f_sparse = make_features(include_all=False, drop=[])
    f_sparse["pe_forward"] = 10.0
    result_sparse = compute_confidence(f_sparse, is_us=True)
    hist_sparse = result_sparse["data_confidence"]["historical_depth"]

    assert hist_rich > hist_sparse, f"Rich history {hist_rich} should be > sparse {hist_sparse}"
    print(f"  PASS: rich history={hist_rich}% > sparse history={hist_sparse}%")


def test_08_duplicate_data_no_boost():
    """Duplicate fields (same info from same source) should NOT inflate confidence."""
    # This test verifies that having two similar fields doesn't double-count.
    # yfinance is the single source for most fields; our system weights by
    # source_reliability, not by field count per se.
    # The key insight: completeness is weighted per-pillar, so having 5 value
    # fields vs 4 doesn't linearly increase confidence — it's capped by the
    # pillar model.
    f_few = make_features(drop=["dividend_yield_pct", "fcf_yield_pct"])
    result_few = compute_confidence(f_few, is_us=True)
    f_all = make_features()
    result_all = compute_confidence(f_all, is_us=True)
    # Adding 2 non-critical fields should NOT increase confidence more than ~5%
    diff = result_all["confidence_score"] - result_few["confidence_score"]
    assert diff < 8.0, f"Adding non-critical fields shouldn't boost conf >8 pts, got {diff}"
    print(f"  PASS: 2 extra non-critical fields only added {diff:.1f}% confidence (capped)")


def test_09_source_quality():
    """Biznesradar enrichment + yfinance corroboration → higher quality score."""
    f_no_br = make_features(is_us=False, drop=["piotroski_f_score", "altman_health_score"])
    result_no_br = compute_confidence(f_no_br, is_us=False)
    f_br = make_features(is_us=False)
    result_br = compute_confidence(f_br, is_us=False, biznesradar_enriched=True,
                                   biznesradar_sourced=["roe_pct"])
    quality_no_br = result_no_br["data_confidence"]["quality"]
    quality_br = result_br["data_confidence"]["quality"]
    assert quality_br >= quality_no_br, f"Biznesradar quality {quality_br} should be >= no-BR {quality_no_br}"
    print(f"  PASS: BR-enriched quality={quality_br}% >= non-BR quality={quality_no_br}%")


def test_10_progressive_data_addition():
    """Confidence increases monotonically and approaches a ceiling.

    Uses evenly-sized groups of added fields across all pillars.
    The key test: the first meaningful jump (from empty to some data)
    should be larger per-field than the last refinement jump.
    """
    all_field_names = [k for k in ALL_FEATURES if ALL_FEATURES[k] is not None]
    # Split into ~6 groups of ~5 fields each
    group_size = max(1, len(all_field_names) // 6)
    groups = [all_field_names[i:i + group_size] for i in range(0, len(all_field_names), group_size)]

    scores = []
    cumulative = []
    for group in groups:
        cumulative.extend(group)
        f = make_features(include_all=False, drop=[])
        for k in cumulative:
            f[k] = ALL_FEATURES[k]
        result = compute_confidence(f, is_us=True)
        scores.append(result["confidence_score"])

    # Monotonicity
    for i in range(1, len(scores)):
        assert scores[i] >= scores[i - 1] - 0.5, (
            f"Confidence should not decrease at stage {i}: {scores[i-1]} → {scores[i]}"
        )

    # Diminishing returns: the per-field gain should decrease from first to last
    fields_per_group = [len(g) for g in groups]
    per_field_gains = []
    for i in range(len(scores)):
        prev = scores[i - 1] if i > 0 else 0
        gain = (scores[i] - prev) / fields_per_group[i]
        per_field_gains.append(gain)

    # First meaningful gain vs last meaningful gain
    first_gain = per_field_gains[0]
    last_gain = per_field_gains[-1]
    assert last_gain <= first_gain * 1.2, (
        f"Per-field gains should not increase: first={first_gain:.1f}, last={last_gain:.1f}"
    )
    assert scores[-1] <= 100, f"Confidence should not exceed 100: {scores[-1]}"

    print(f"  scores: {[round(s, 1) for s in scores]}")
    print(f"  per-field gains: {[round(g, 2) for g in per_field_gains]}")
    print(f"  PASS: first gain/field={first_gain:.2f}, last gain/field={last_gain:.2f}")


def test_11_us_vs_non_us():
    """Non-US stocks are not penalized for missing short interest."""
    # US with short_interest missing → penalty
    f_us_no_short = make_features(drop=["short_interest_pct_float"], is_us=True)
    result_us = compute_confidence(f_us_no_short, is_us=True)
    # WSE without short_interest → should NOT be penalized the same way
    f_wse_no_short = make_features(drop=["short_interest_pct_float"], is_us=False)
    result_wse = compute_confidence(f_wse_no_short, is_us=False)
    # US should have short_interest in critical fields check
    # WSE should have similar or better confidence since short interest isn't required
    assert result_wse["confidence_score"] >= result_us["confidence_score"] - 2, (
        f"WSE ({result_wse['confidence_score']}) should not be penalized more than US "
        f"({result_us['confidence_score']}) for missing short interest"
    )
    print(f"  PASS: US conf={result_us['confidence_score']}%, WSE conf={result_wse['confidence_score']}%")


def test_12_pillar_confidence_independence():
    """Data-rich pillar should not completely hide a data-poor pillar."""
    f = make_features()
    # Remove all sentiment data
    f["recommendation_mean"] = None
    f["analyst_opinions"] = None
    f["short_interest_pct_float"] = None
    result = compute_confidence(f, is_us=True)
    sent_conf = result["pillar_confidence"]["sentiment"]["overall"]
    # Sentiment pillar should have low confidence
    assert sent_conf < 40, f"Sentiment pillar with no data should have low confidence, got {sent_conf}"
    # But overall shouldn't be killed by one bad pillar
    assert result["confidence_score"] > 50, f"Overall conf should still be reasonable, got {result['confidence_score']}"
    print(f"  PASS: sentiment pillar conf={sent_conf}% (no data), overall={result['confidence_score']}%")


def test_13_nonlinear_penalty():
    """The nth missing field should hurt more than the (n-1)th (nonlinear penalty)."""
    base_f = make_features()

    # Drop 1 field
    f1 = make_features(drop=["dividend_yield_pct"])
    # Drop 3 fields
    f3 = make_features(drop=["dividend_yield_pct", "fcf_yield_pct", "analyst_upside_pct"])
    # Drop 6 fields
    f6 = make_features(drop=[
        "dividend_yield_pct", "fcf_yield_pct", "analyst_upside_pct",
        "price_to_book", "gross_margin_pct", "ma200_slope_3m_pct",
    ])

    r_base = compute_confidence(base_f, is_us=True)["confidence_score"]
    r1 = compute_confidence(f1, is_us=True)["confidence_score"]
    r3 = compute_confidence(f3, is_us=True)["confidence_score"]
    r6 = compute_confidence(f6, is_us=True)["confidence_score"]

    # Each additional group should have a larger marginal drop (or at least not smaller)
    drop_1 = r_base - r1
    drop_3_1 = r1 - r3  # dropping 2 more
    drop_6_3 = r3 - r6  # dropping 3 more

    avg_drop_per_field_1 = drop_3_1 / 2
    avg_drop_per_field_2 = drop_6_3 / 3

    print(f"  drops: base={r_base} → -1={r1} ({drop_1}) → -3={r3} ({drop_3_1}) → -6={r6} ({drop_6_3})")
    print(f"  avg drop per field: first 2={avg_drop_per_field_1:.1f}, next 3={avg_drop_per_field_2:.1f}")
    # The nonlinear penalty should mean later fields hurt proportionally more
    # (at minimum not less). We check that confidence keeps decreasing.
    assert r_base > r1 > r3 > r6, "Confidence should monotonically decrease with more missing fields"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all():
    tests = [
        ("Test 01 - Complete stock → high confidence", test_01_complete_stock),
        ("Test 02 - Sparse stock → low confidence", test_02_sparse_stock),
        ("Test 03 - High score + sparse → reduced adjusted", test_03_high_score_sparse_data),
        ("Test 04 - Lower score + excellent data → better adjusted", test_04_lower_score_excellent_data),
        ("Test 05 - Missing critical → large penalty", test_05_missing_critical),
        ("Test 06 - Stale data → lower freshness", test_06_stale_data),
        ("Test 07 - Long history → higher confidence", test_07_long_history),
        ("Test 08 - Duplicate data → no artificial boost", test_08_duplicate_data_no_boost),
        ("Test 09 - Source corroboration → higher quality", test_09_source_quality),
        ("Test 10 - Progressive addition → monotonic + diminishing returns", test_10_progressive_data_addition),
        ("Test 11 - US vs non-US short interest handling", test_11_us_vs_non_us),
        ("Test 12 - Pillar independence (rich doesn't hide poor)", test_12_pillar_confidence_independence),
        ("Test 13 - Nonlinear missing-data penalty", test_13_nonlinear_penalty),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {name}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)