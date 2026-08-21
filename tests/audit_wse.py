"""
WSE Screening Verification Audit

Performs a comprehensive audit of the Warsaw Stock Exchange (WSE) screening
results from screen_candidates.py --preset wse --biznesradar.

Checks: universe, ticker mapping, data quality, confidence, scoring,
ranking, outliers, currency, sector, market cap, liquidity, freshness.
"""
import json
import math
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── helpers ────────────────────────────────────────────────────────────

def load_screen(path="screen_wse_full.json"):
    """Load the WSE screen JSON with encoding detection."""
    data = open(path, "rb").read()
    if data.startswith(b"\xff\xfe"):
        text = data.decode("utf-16")
    elif data.startswith(b"\xef\xbb\xbf"):
        text = data.decode("utf-8-sig")
    else:
        text = data.decode("utf-8")
    return json.loads(text)


def fmt(v, ndigits=1):
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.{ndigits}f}"
    except (TypeError, ValueError):
        return str(v)


# ── main audit ────────────────────────────────────────────────────────

def run_audit():
    print("=" * 70)
    print("WSE SCREENING VERIFICATION AUDIT")
    print("=" * 70)

    screen = load_screen()
    ranked = screen.get("ranked", [])
    n = len(ranked)

    # ── SECTION 1: Universe ──────────────────────────────────────────
    print(f"\n{'─'*50}")
    print("1. UNIVERSE")
    print(f"{'─'*50}")
    print(f"  Total stocks in universe: {screen.get('universe_size', '?')}")
    print(f"  Total ranked:              {n}")
    errors = [r for r in ranked if r.get("error")]
    success = [r for r in ranked if not r.get("error") and r.get("screen_score") is not None]
    partial = [r for r in ranked if not r.get("error") and r.get("screen_score") is None]
    print(f"  Successful:                {len(success)}")
    print(f"  Partial (null score):      {len(partial)}")
    print(f"  Failed (errors):           {len(errors)}")
    if partial:
        print("  Partial stocks:")
        for r in partial:
            print(f"    {r.get('symbol')}: {r.get('name', '?')}")
    if errors:
        print("  Failed stocks:")
        for r in errors:
            print(f"    {r.get('symbol')}: {r.get('error', '?')[:80]}")
    print(f"  Horizon: {screen.get('horizon', '?')}")
    print(f"  Biznesradar enrichment: {screen.get('biznesradar_enrichment', False)}")

    # Count .WA suffixes
    wa_count = sum(1 for r in ranked if r.get("symbol", "").endswith(".WA"))
    non_wa = sum(1 for r in ranked if not r.get("symbol", "").endswith(".WA"))
    print(f"  .WA suffix present: {wa_count}")
    print(f"  .WA suffix absent:  {non_wa}")

    # ── SECTION 2: Scoring overview ──────────────────────────────────
    print(f"\n{'─'*50}")
    print("2. SCORING OVERVIEW")
    print(f"{'─'*50}")

    raw_scores = [r["raw_screen_score"] for r in success if r.get("raw_screen_score") is not None]
    adj_scores = [r["screen_score"] for r in success if r.get("screen_score") is not None]
    conf_scores = [r["confidence_score"] for r in success if r.get("confidence_score") is not None]

    if raw_scores:
        print(f"  Raw scores:     min={min(raw_scores):.1f}  max={max(raw_scores):.1f}  mean={sum(raw_scores)/len(raw_scores):.1f}")
    if adj_scores:
        print(f"  Adjusted:       min={min(adj_scores):.1f}  max={max(adj_scores):.1f}  mean={sum(adj_scores)/len(adj_scores):.1f}")
    if conf_scores:
        print(f"  Confidence:     min={min(conf_scores):.1f}  max={max(conf_scores):.1f}  mean={sum(conf_scores)/len(conf_scores):.1f}")

    # Confidence distribution
    levels = Counter(r.get("confidence_level", "?") for r in success)
    print(f"  Confidence levels:")
    for level in ["Very High", "High", "Moderate", "Low", "Very Low"]:
        if level in levels:
            print(f"    {level}: {levels[level]}")

    # ── SECTION 3: Data quality ─────────────────────────────────────
    print(f"\n{'─'*50}")
    print("3. DATA QUALITY")
    print(f"{'─'*50}")

    completeness_vals = [r.get("data_confidence", {}).get("completeness", 0) for r in success]
    hist_vals = [r.get("data_confidence", {}).get("historical_depth", 0) for r in success]
    fresh_vals = [r.get("data_confidence", {}).get("freshness", 0) for r in success]
    qual_vals = [r.get("data_confidence", {}).get("quality", 0) for r in success]
    src_vals = [r.get("data_confidence", {}).get("source_reliability", 0) for r in success]
    crit_vals = [r.get("data_confidence", {}).get("critical_data_completeness", 0) for r in success]

    for name, vals in [("Completeness", completeness_vals), ("Historical", hist_vals),
                        ("Freshness", fresh_vals), ("Quality", qual_vals),
                        ("Source", src_vals), ("Critical", crit_vals)]:
        if vals:
            print(f"  {name:15s}  min={min(vals):.1f}  max={max(vals):.1f}  mean={sum(vals)/len(vals):.1f}")

    # Data sources
    br_enriched = sum(1 for r in success if r.get("biznesradar_enriched"))
    print(f"  Biznesradar enriched: {br_enriched}/{len(success)}")

    # Missing critical data
    with_critical_missing = sum(1 for r in success if r.get("missing_critical"))
    print(f"  Stocks with missing critical data: {with_critical_missing}/{len(success)}")
    if with_critical_missing > 0:
        # Show most common missing critical fields
        crit_counter = Counter()
        for r in success:
            for f in r.get("missing_critical", []):
                crit_counter[f] += 1
        print(f"  Most common missing critical fields:")
        for field, count in crit_counter.most_common(8):
            print(f"    {field}: {count}")

    # ── SECTION 4: Top/Bottom rankings ──────────────────────────────
    print(f"\n{'─'*50}")
    print("4. TOP & BOTTOM RANKINGS")
    print(f"{'─'*50}")

    print("\n  Top 15 by adjusted score:")
    for i, r in enumerate(success[:15], 1):
        print(f"  {i:2d}. {r['symbol']:10s} {r.get('name','?'):30s}  raw={fmt(r.get('raw_screen_score')):>6s}  adj={fmt(r.get('screen_score')):>6s}  conf={fmt(r.get('confidence_score')):>5s}%  {r.get('confidence_level','')}")

    print("\n  Bottom 15 by adjusted score:")
    for i, r in enumerate(success[-15:], len(success)-14):
        print(f"  {i:2d}. {r['symbol']:10s} {r.get('name','?'):30s}  raw={fmt(r.get('raw_screen_score')):>6s}  adj={fmt(r.get('screen_score')):>6s}  conf={fmt(r.get('confidence_score')):>5s}%  {r.get('confidence_level','')}")

    # ── SECTION 5: Confidence extremes ──────────────────────────────
    print(f"\n{'─'*50}")
    print("5. CONFIDENCE EXTREMES")
    print(f"{'─'*50}")

    by_conf = sorted(success, key=lambda r: r.get("confidence_score", 0))
    print("\n  Bottom 15 by confidence:")
    for i, r in enumerate(by_conf[:15], 1):
        missing_str = ",".join(r.get("missing_critical", [])[:2]) or "none"
        print(f"  {i:2d}. {r['symbol']:10s}  conf={fmt(r.get('confidence_score')):>5s}%  level={r.get('confidence_level',''):12s}  missing_critical: {missing_str}")

    print("\n  Top 15 by confidence:")
    for i, r in enumerate(by_conf[-15:][::-1], 1):
        missing_str = ",".join(r.get("missing_critical", [])[:2]) or "none"
        print(f"  {i:2d}. {r['symbol']:10s}  conf={fmt(r.get('confidence_score')):>5s}%  level={r.get('confidence_level',''):12s}  missing_critical: {missing_str}")

    # ── SECTION 6: Rank changes raw→adjusted ────────────────────────
    print(f"\n{'─'*50}")
    print("6. RANK CHANGES (RAW → ADJUSTED)")
    print(f"{'─'*50}")

    by_raw = sorted(success, key=lambda r: (r.get("raw_screen_score") or 0), reverse=True)
    raw_rank = {r["symbol"]: i+1 for i, r in enumerate(by_raw)}
    adj_rank = {r["symbol"]: i+1 for i, r in enumerate(success)}

    rank_changes = []
    for r in success:
        sym = r["symbol"]
        rr = raw_rank.get(sym, 0)
        ar = adj_rank.get(sym, 0)
        change = rr - ar  # positive = moved up when adjusted
        rank_changes.append((abs(change), change, sym, rr, ar,
                            r.get("raw_screen_score"), r.get("screen_score"),
                            r.get("confidence_score")))

    rank_changes.sort(reverse=True)
    print("\n  Biggest rank movers (raw→adjusted):")
    print(f"  {'Sym':10s} {'RawRk':>5s} {'AdjRk':>5s} {'Δ':>5s} {'Raw':>6s} {'Adj':>6s} {'Conf':>5s}")
    for _, ch, sym, rr, ar, raw, adj, conf in rank_changes[:20]:
        arrow = "↑" if ch > 0 else "↓" if ch < 0 else "─"
        print(f"  {sym:10s} {rr:5d} {ar:5d} {ch:+4d}{arrow} {fmt(raw):>6s} {fmt(adj):>6s} {fmt(conf):>5s}%")

    # ── SECTION 7: Outlier detection ────────────────────────────────
    print(f"\n{'─'*50}")
    print("7. OUTLIER DETECTION")
    print(f"{'─'*50}")

    outliers = []
    for r in success:
        sig = r.get("signals", {})
        issues = []

        # Check price
        price = sig.get("atr_pct_of_price")  # we use atr_pct as a proxy
        price_val = r.get("price")
        if price_val is not None:
            if price_val <= 0:
                issues.append(f"price={price_val}")
            elif price_val > 5000:
                issues.append(f"high_price={price_val}")

        # Check P/E
        pe = sig.get("pe_forward")
        if pe is not None:
            if pe < 0.1 and pe > 0:
                issues.append(f"tiny_pe={pe}")
            elif pe > 500:
                issues.append(f"huge_pe={pe}")
            elif pe < -500:
                issues.append(f"neg_pe={pe}")

        # Check ROE
        roe = sig.get("roe_pct")
        if roe is not None:
            if abs(roe) > 500:
                issues.append(f"extreme_roe={roe}")

        # Check revenue growth
        rg = sig.get("revenue_growth_pct")
        if rg is not None and abs(rg) > 1000:
            issues.append(f"extreme_rev_growth={rg}")

        # Check beta
        beta = sig.get("beta")
        if beta is not None and (beta < 0 or beta > 5):
            issues.append(f"extreme_beta={beta}")

        # Check ATR
        atr = sig.get("atr_pct_of_price")
        if atr is not None and atr > 50:
            issues.append(f"extreme_atr={atr}")

        # High raw score with low confidence
        raw_s = r.get("raw_screen_score", 0) or 0
        conf = r.get("confidence_score", 100) or 100
        if raw_s > 75 and conf < 50:
            issues.append(f"HIGH_RAW({raw_s:.0f})_LOW_CONF({conf:.0f}%)")

        # Low raw score with high confidence
        if raw_s < 30 and conf > 85:
            issues.append(f"LOW_RAW({raw_s:.0f})_HIGH_CONF({conf:.0f}%)")

        if issues:
            outliers.append((r["symbol"], r.get("name", "?"), r.get("screen_score"),
                           r.get("confidence_score"), issues))

    print(f"  Stocks with warnings: {len(outliers)}")
    for sym, name, score, conf, issues in outliers[:25]:
        print(f"  {sym:10s}  score={fmt(score):>6s}  conf={fmt(conf):>5s}%  {', '.join(issues)}")

    if len(outliers) > 25:
        print(f"  ... and {len(outliers)-25} more")

    # ── SECTION 8: Sector analysis ──────────────────────────────────
    print(f"\n{'─'*50}")
    print("8. SECTOR ANALYSIS")
    print(f"{'─'*50}")

    sectors = Counter(r.get("sector", "Unknown") for r in success)
    print(f"  Sectors ({len(sectors)}):")
    for sector, count in sectors.most_common():
        sector_stocks = [r for r in success if r.get("sector") == sector]
        avg_conf = sum(r.get("confidence_score", 0) for r in sector_stocks) / max(len(sector_stocks), 1)
        avg_score = sum(r.get("screen_score", 0) or 0 for r in sector_stocks) / max(len(sector_stocks), 1)
        missing_crit = sum(1 for r in sector_stocks if r.get("missing_critical"))
        print(f"    {sector:35s}  n={count:3d}  avg_adj={avg_score:.1f}  avg_conf={avg_conf:.1f}%  missing_crit={missing_crit}")

    # ── SECTION 9: Currency & exchange check ────────────────────────
    print(f"\n{'─'*50}")
    print("9. CURRENCY & EXCHANGE")
    print(f"{'─'*50}")

    currencies = Counter(r.get("currency", "Unknown") for r in success)
    print(f"  Currencies: {dict(currencies)}")
    non_pln = [(r["symbol"], r.get("currency")) for r in success if r.get("currency") != "PLN"]
    if non_pln:
        print(f"  Non-PLN stocks: {non_pln}")
    else:
        print("  All stocks in PLN ✓")

    # ── SECTION 10: Liquidity ───────────────────────────────────────
    print(f"\n{'─'*50}")
    print("10. LIQUIDITY")
    print(f"{'─'*50}")

    low_liq = [r for r in success if r.get("low_liquidity")]
    print(f"  Low liquidity: {len(low_liq)}/{len(success)}")
    if low_liq:
        for r in low_liq[:10]:
            adv = r.get("signals", {}).get("avg_dollar_volume", 0) or 0
            print(f"    {r['symbol']:10s}  ADV={adv:,.0f} PLN  score={fmt(r.get('screen_score'))}  conf={fmt(r.get('confidence_score'))}%")
        if len(low_liq) > 10:
            print(f"    ... and {len(low_liq)-10} more")

    # ── SECTION 11: Manual score recalculation ──────────────────────
    print(f"\n{'─'*50}")
    print("11. SCORE RECALCULATION (sampled)")
    print(f"{'─'*50}")

    # Recalculate for a sample
    import random
    random.seed(42)
    sample = random.sample(success, min(12, len(success)))

    from lib.confidence import compute_confidence, confidence_adjust
    from lib.common import is_us_listing

    recalc_ok = 0
    recalc_fail = 0
    for r in sample:
        sym = r["symbol"]
        is_us = is_us_listing(sym)

        # Reconstruct features dict from signals
        sig = r.get("signals", {})
        f = dict(sig)

        conf_result = compute_confidence(
            f, is_us=is_us,
            biznesradar_enriched=r.get("biznesradar_enriched", False),
            biznesradar_sourced=r.get("biznesradar_sourced"),
        )
        expected_conf = conf_result["confidence_score"]
        actual_conf = r.get("confidence_score", 0)
        conf_diff = abs(expected_conf - actual_conf)

        raw = r.get("raw_screen_score")
        expected_adj = confidence_adjust(raw, expected_conf) if raw is not None else None
        actual_adj = r.get("screen_score")
        adj_diff = abs(expected_adj - actual_adj) if expected_adj is not None and actual_adj is not None else 0

        status = "✓" if conf_diff < 0.5 and adj_diff < 0.5 else "✗"
        if conf_diff < 0.5 and adj_diff < 0.5:
            recalc_ok += 1
        else:
            recalc_fail += 1
            print(f"  {status} {sym}: conf expected={expected_conf} actual={actual_conf} diff={conf_diff:.2f}  adj expected={expected_adj} actual={actual_adj} diff={adj_diff:.2f}")
        if status == "✓":
            print(f"  {status} {sym}: conf={actual_conf}% adj={actual_adj} — OK")

    print(f"\n  Recalculated: {recalc_ok} OK, {recalc_fail} FAIL (of {len(sample)})")

    # ── SECTION 12: Ranking consistency ─────────────────────────────
    print(f"\n{'─'*50}")
    print("12. RANKING CONSISTENCY")
    print(f"{'─'*50}")

    adj_list = [(r.get("screen_score") or 0, r["symbol"]) for r in success]
    is_sorted = all(adj_list[i][0] >= adj_list[i+1][0] for i in range(len(adj_list)-1))
    print(f"  Adjusted scores monotonically decreasing: {is_sorted}")

    # Check for duplicate scores
    score_counts = Counter(r.get("screen_score") for r in success)
    dup_scores = {s: c for s, c in score_counts.items() if c > 1}
    if dup_scores:
        print(f"  Duplicate adjusted scores: {len(dup_scores)}")
        for s, c in sorted(dup_scores.items(), reverse=True)[:5]:
            print(f"    score={s}: {c} stocks share this score")

    # ── SECTION 13: Market cap analysis ─────────────────────────────
    print(f"\n{'─'*50}")
    print("13. MARKET CAP ANALYSIS")
    print(f"{'─'*50}")

    caps = []
    for r in success:
        mc = r.get("signals", {}).get("avg_dollar_volume")
        caps.append((r["symbol"], mc))
    # Actually use real market cap isn't in signals directly... use price*volume as proxy
    # Let's just report the range of avg_dollar_volume
    adv_vals = [r.get("signals", {}).get("avg_dollar_volume", 0) or 0 for r in success]
    adv_vals = [v for v in adv_vals if v > 0]
    if adv_vals:
        print(f"  ADV (PLN): min={min(adv_vals):,.0f}  max={max(adv_vals):,.0f}  median={sorted(adv_vals)[len(adv_vals)//2]:,.0f}")

    # ── SECTION 14: Final summary ───────────────────────────────────
    print(f"\n{'='*70}")
    print("FINAL VERDICT")
    print(f"{'='*70}")

    critical_issues = 0
    high_issues = 0
    medium_issues = 0
    low_issues = 0

    # Critical checks
    if len(success) < 130:
        critical_issues += 1
        print("  CRITICAL: Too many screening failures")
    non_pln_currencies = [r for r in success if r.get("currency") != "PLN"]
    if non_pln_currencies:
        critical_issues += 1
        print(f"  CRITICAL: Non-PLN currencies found: {non_pln_currencies}")
    if not is_sorted:
        critical_issues += 1
        print("  CRITICAL: Ranking not sorted correctly")
    if recalc_fail > 2:
        critical_issues += 1
        print(f"  CRITICAL: {recalc_fail} score recalculations failed")

    # High checks
    if with_critical_missing > len(success) * 0.3:
        high_issues += 1
        print(f"  HIGH: {with_critical_missing}/{len(success)} stocks missing critical data")
    if len(outliers) > 20:
        high_issues += 1
        print(f"  HIGH: {len(outliers)} outlier warnings")

    # Medium checks
    if min(conf_scores) < 20:
        medium_issues += 1
        print(f"  MEDIUM: Some stocks have very low confidence ({min(conf_scores):.1f}%)")
    if len(low_liq) > 0:
        medium_issues += 1
        print(f"  MEDIUM: {len(low_liq)} stocks flagged as low liquidity")

    # Low
    if dup_scores:
        low_issues += 1
        print(f"  LOW: {len(dup_scores)} duplicate score values exist")

    print(f"\n  Critical: {critical_issues}  High: {high_issues}  Medium: {medium_issues}  Low: {low_issues}")

    if critical_issues > 0:
        verdict = "NOT RELIABLE — FIX REQUIRED"
    elif high_issues > 2:
        verdict = "READY WITH WARNINGS"
    else:
        verdict = "READY FOR USE"

    print(f"\n  VERDICT: {verdict}")
    print(f"{'='*70}")

    return locals()


if __name__ == "__main__":
    run_audit()