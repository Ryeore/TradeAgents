#!/usr/bin/env python
"""screen_candidates.py -- opportunity screener for the Opportunity Scout agent.

Ranks a universe of tickers by a blended value / quality / momentum score so the
desk can surface NEW candidates worth a full work-up. No API keys required.

Usage:
    python scripts/screen_candidates.py AAPL MSFT NVDA
    python scripts/screen_candidates.py --preset wse_blue --top 5
    python scripts/screen_candidates.py --universe watchlist.txt --min-score 55
"""
import argparse
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    DEFAULT_HORIZON, HORIZON_WEIGHTS, atr, emit, get_ticker, history, is_us_listing,
    last_price, round_or_none, rsi, safe_info, sma,
)

# biznesradar enrichment (Warsaw/WSE only) is optional. Import it from this same
# scripts/ dir, but never let a missing module or dependency break the screen.
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
try:
    import fetch_biznesradar  # noqa: E402
except Exception:  # pragma: no cover - enrichment is best-effort
    fetch_biznesradar = None

WATCHLIST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "watchlists"
)


def _read_watchlist(filename: str) -> list[str]:
    """Return upper-cased tickers from watchlists/<filename>, skipping blanks and # comments."""
    path = os.path.join(WATCHLIST_DIR, filename)
    tickers: list[str] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            ticker = line.split("#")[0].strip().upper()
            if ticker:
                tickers.append(ticker)
    return tickers


PRESETS = {
    "wse": _read_watchlist("wse_blue.txt"),
    "us100": _read_watchlist("us100.txt"),
    "all": _read_watchlist("wse_blue.txt") + _read_watchlist("us100.txt"),
    "current_portfolio": ["KRU.WA", "XTB.WA", "DIA.WA", "CBF.WA", "ACP.WA", "PKO.WA",
                          "MBR.WA", "SNT.WA", "ASB.WA", "NVDA", "AVGO", "MU", "DIG.WA"],
    "current_pl": ["KRU.WA", "XTB.WA", "DIA.WA", "CBF.WA", "ACP.WA", "PKO.WA",
                          "MBR.WA", "SNT.WA", "ASB.WA", "DIG.WA"]
}


# (Removed TEMP_PRESETS; rely on git history or add a real preset name instead of keeping commented-out lists.)

# Exponential missing-data penalty: each absent required input multiplies the
# screen score by MISSING_DATA_DECAY, so gaps compound. Tuned so a row missing
# all required inputs keeps ~15% of its raw score (0.86 ** 12 ≈ 0.16).
MISSING_DATA_DECAY = 0.86

# Investing horizon defaults / pillar weightings are shared with the allocator
# (see lib.common.HORIZON_WEIGHTS). Imported above so both stay in lock-step.

# Sector-neutral ranking: value/quality features are ranked WITHIN a company's
# sector when at least this many sector peers have the field, otherwise the
# ranking falls back to the whole screened universe. This stops banks (low P/E,
# low P/B, no gross margin) from mechanically out/under-scoring software names.
MIN_SECTOR_GROUP = 3

# Below this universe size, cross-sectional percentiles are coarse/noisy, so we
# shrink each percentile toward the neutral 50 (regularization) and warn.
SMALL_UNIVERSE_N = 8

# Per-currency soft daily-turnover floors (in the listing currency). Names below
# their floor are flagged `low_liquidity` (informational; not dropped unless the
# caller passes --min-adv). Rough retail-tradeable thresholds, not hard limits.
DEFAULT_ADV_FLOOR = {"USD": 2_000_000.0, "PLN": 2_000_000.0, "EUR": 2_000_000.0}


def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def scale(val, lo, hi):
    """Map val from [lo,hi] onto [0,100], clamped. hi<lo inverts (lower=better)."""
    if val is None:
        return None
    if hi == lo:
        return 50.0
    return clamp((val - lo) / (hi - lo) * 100.0)


def _pct(v):
    """yfinance returns some ratios as fractions; normalise to percent."""
    if v is None:
        return None
    return v * 100 if abs(v) < 5 else v


def _na_if_zero(v):
    """Treat an exact 0.0 as not-applicable.

    yfinance reports grossMargins / operatingMargins / freeCashflow as exactly
    0 for businesses where the field is undefined (notably banks and insurers).
    A literal 0 would otherwise land at the bottom of a percentile ranking, so
    we drop it to None (excluded from scoring) instead of scoring it worst.
    """
    if v is None:
        return None
    return None if abs(v) < 1e-9 else v


def _dividend_yield_pct(info: dict, price: float | None):
    """Robust dividend yield in percent, resilient to yfinance version drift.

    Preference order (most reliable first):
      1. dividendRate / price               (unambiguous, version-independent)
      2. trailingAnnualDividendRate / price
      3. (trailing)dividendYield with best-effort fraction-vs-percent detection
    Anything outside a sane 0-25% band is treated as a data glitch -> None.
    """
    def _sane(y):
        return y if y is not None and 0.0 <= y <= 25.0 else None

    for rate_key in ("dividendRate", "trailingAnnualDividendRate"):
        rate = info.get(rate_key)
        if rate and price:
            got = _sane(rate / price * 100.0)
            if got is not None:
                return round(got, 4)

    for yld_key in ("trailingAnnualDividendYield", "dividendYield"):
        y = info.get(yld_key)
        if y is None:
            continue
        if y > 100:            # e.g. 543 basis-point-ish glitch -> 5.43
            y = y / 100.0
        elif 0 < y <= 1:       # fraction 0.023 -> 2.3 (percent values stay as-is)
            y = y * 100.0
        got = _sane(y)
        if got is not None:
            return round(got, 4)
    return None


def _dividend_growth_pct(ticker) -> float | None:
    """Return trailing-year dividend growth versus the preceding year."""
    try:
        dividends = ticker.dividends
        if dividends is None or dividends.empty:
            return None
        end = dividends.index.max()
        recent_start = end - timedelta(days=365)
        prior_start = end - timedelta(days=730)
        recent = float(dividends[(dividends.index > recent_start) & (dividends.index <= end)].sum())
        prior = float(dividends[(dividends.index > prior_start) & (dividends.index <= recent_start)].sum())
        if prior <= 0:
            return None
        return round((recent / prior - 1.0) * 100.0, 1)
    except Exception:
        return None


def _shrink_toward_50(score, shrink: float):
    """Pull a percentile score toward the neutral 50 by `shrink` in (0,1]."""
    if score is None:
        return None
    return round(50.0 + (score - 50.0) * shrink, 1)


def avg(parts: list[float | None]) -> float | None:
    """Return the mean of non-None values, rounded to 1 decimal."""
    vals = [p for p in parts if p is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def percentile_score(value, universe_values, higher_better=True):
    """Cross-sectional percentile score in [0,100]."""
    if value is None:
        return None
    vals = sorted(v for v in universe_values if v is not None)
    n = len(vals)
    if n == 0:
        return None
    if n == 1:
        return 50.0
    less = sum(1 for v in vals if v < value)
    equal = sum(1 for v in vals if v == value)
    rank = (less + 0.5 * equal) / n
    score = rank * 100.0
    return round(100.0 - score if not higher_better else score, 1)


def sweet_spot_score(value, target, slope, lo=0.0, hi=100.0):
    """Peak score near target; linearly decays with distance by slope points/unit."""
    if value is None:
        return None
    return round(clamp(100.0 - abs(value - target) * slope, lo, hi), 1)


def structure_score(price, ma20, ma50, ma200):
    if None in (price, ma20, ma50, ma200):
        return None
    if price > ma20 > ma50 > ma200:
        return 100.0
    if price > ma50 > ma200:
        return 80.0
    if price > ma200:
        return 60.0
    return 20.0


def piotroski_score(f_score):
    """Map a Piotroski F-Score (0-9) to a direct 0-100 quality sub-score."""
    if f_score is None:
        return None
    return round(max(0, min(9, f_score)) / 9 * 100, 1)


def _latest(series):
    if series is None:
        return None
    valid = series.dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])


def collect_features(symbol, use_biznesradar=False):
    """Collect raw value, quality, trend, sentiment, and risk features for one symbol.

    When ``use_biznesradar`` is set and ``symbol`` is a ``.WA`` (Warsaw/WSE) listing,
    the feature set is enriched from biznesradar.pl: the Piotroski F-Score and Altman
    EM-Score (no Yahoo equivalent) are added, and ROE / P-B are backfilled when
    yfinance leaves them null.
    """
    ticker = get_ticker(symbol)
    info = safe_info(ticker)
    price = last_price(ticker, info)
    df = history(ticker, period="2y")

    target = info.get("targetMeanPrice")
    upside = (target / price - 1) * 100 if price and target else None
    pe_fwd = info.get("forwardPE")
    pb = info.get("priceToBook")
    div = _dividend_yield_pct(info, price)
    div_growth = _dividend_growth_pct(ticker)
    roe = _pct(info.get("returnOnEquity"))
    rev_g = _pct(info.get("revenueGrowth"))
    eps_g = _pct(info.get("earningsGrowth"))
    op_margin = _na_if_zero(_pct(info.get("operatingMargins")))
    gross_margin = _na_if_zero(_pct(info.get("grossMargins")))
    beta = info.get("beta")
    sector = info.get("sector")
    rec_mean = info.get("recommendationMean")
    analyst_n = info.get("numberOfAnalystOpinions")
    short_pct = _pct(info.get("shortPercentOfFloat"))

    fcf_yield = None
    market_cap = info.get("marketCap")
    free_cashflow = _na_if_zero(info.get("freeCashflow"))
    if market_cap and free_cashflow:
        fcf_yield = (free_cashflow / market_cap) * 100

    # Average daily turnover (liquidity), in the listing currency.
    avg_volume = info.get("averageVolume") or info.get("averageDailyVolume10Day")
    avg_dollar_volume = None
    if avg_volume and price:
        avg_dollar_volume = float(avg_volume) * float(price)

    ret3m = ret6m = ret12m = None
    ma20 = ma50 = ma200 = rsi14 = above50 = above200 = None
    price_vs_ma200_pct = ma50_vs_ma200_pct = ma200_slope_3m_pct = None
    atr14 = atr_pct = prox_52w_high_pct = max_dd_6m_pct = None

    if not df.empty and len(df) > 60:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        if len(close) >= 63:
            ret3m = round_or_none((close.iloc[-1] / close.iloc[-63] - 1) * 100)
        if len(close) >= 126:
            ret6m = round_or_none((close.iloc[-1] / close.iloc[-126] - 1) * 100)
        if len(close) >= 252:
            ret12m = round_or_none((close.iloc[-1] / close.iloc[-252] - 1) * 100)

        ma20 = round_or_none(_latest(sma(close, 20)))
        ma50 = round_or_none(_latest(sma(close, 50)))
        ma200_series = sma(close, 200)
        ma200_last = _latest(ma200_series)
        ma200 = round_or_none(ma200_last)
        rsi14 = round_or_none(_latest(rsi(close, 14)))

        if price and ma50:
            above50 = bool(price > ma50)
        if price and ma200:
            above200 = bool(price > ma200)
        if price and ma200:
            price_vs_ma200_pct = round_or_none((price / ma200 - 1) * 100)
        if ma50 and ma200:
            ma50_vs_ma200_pct = round_or_none((ma50 / ma200 - 1) * 100)

        ma200_valid = ma200_series.dropna()
        if len(ma200_valid) >= 63:
            ma200_prev = float(ma200_valid.iloc[-63])
            ma200_now = float(ma200_valid.iloc[-1])
            if ma200_prev:
                ma200_slope_3m_pct = round_or_none((ma200_now / ma200_prev - 1) * 100)

        if len(high) >= 30 and len(low) >= 30:
            atr14_raw = _latest(atr(high, low, close))
            atr14 = round_or_none(atr14_raw)
            if atr14_raw and price:
                atr_pct = round_or_none(atr14_raw / price * 100)

        window_52w = close.tail(252) if len(close) >= 252 else close
        if not window_52w.empty and price:
            high_52w = float(window_52w.max())
            if high_52w:
                prox_52w_high_pct = round_or_none(price / high_52w * 100)

        close_6m = close.tail(126) if len(close) >= 126 else close
        if not close_6m.empty:
            roll_max = close_6m.cummax()
            dd = close_6m / roll_max - 1.0
            max_dd_6m_pct = round_or_none(float(dd.min()) * 100)

        if avg_volume is None and "Volume" in df:
            vol_tail = df["Volume"].tail(30).dropna()
            if not vol_tail.empty:
                avg_volume = float(vol_tail.mean())

    if avg_dollar_volume is None and avg_volume and price:
        avg_dollar_volume = float(avg_volume) * float(price)

    # Optional biznesradar enrichment for Warsaw (WSE) listings.
    piotroski_f = None
    altman_health = None
    br_enriched = False
    br_sources: list[str] = []
    if use_biznesradar and fetch_biznesradar is not None and symbol.upper().endswith(".WA"):
        try:
            br = fetch_biznesradar.collect(symbol)
        except Exception as exc:  # a scrape failure must never break the screen
            print(f"  biznesradar {symbol} skipped: {exc}", file=sys.stderr, flush=True)
            br = None
        if br:
            br_enriched = True
            piotroski_f = br.get("piotroski_f_score")
            altman_health = br.get("altman_health_score")
            # Backfill ROE / P-B when yfinance is null (verified consistent).
            if roe is None and br.get("roe_pct") is not None:
                roe = br["roe_pct"]
                br_sources.append("roe_pct")
            if pb is None and br.get("pb") is not None:
                pb = br["pb"]
                br_sources.append("price_to_book")
            # Backfill P/E when yfinance forwardPE is null. biznesradar's C/Z
            # (trailing) is not a perfect substitute for forward P/E, but is
            # far better than leaving the critical field null, which triggers
            # a confidence penalty. Flagged as biznesradar-sourced so the
            # confidence system can apply appropriate quality/reliability
            # adjustments for a secondary trailing-P/E source.
            if pe_fwd is None and br.get("pe") is not None:
                pe_fwd = br["pe"]
                br_sources.append("pe_trailing_as_forward")
            print(f"  biznesradar {symbol}: F-Score={piotroski_f} altman_health={altman_health}"
                  f"{' backfilled ' + '+'.join(br_sources) if br_sources else ''}",
                  file=sys.stderr, flush=True)

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "price": round_or_none(price),
        "currency": info.get("currency"),
        "sector": sector,
        "biznesradar_enriched": br_enriched,
        "biznesradar_sourced": br_sources,
        "features": {
            "analyst_upside_pct": round_or_none(upside),
            "pe_forward": round_or_none(pe_fwd),
            "price_to_book": round_or_none(pb),
            "dividend_yield_pct": round_or_none(div),
            "dividend_growth_pct": div_growth,
            "fcf_yield_pct": round_or_none(fcf_yield),
            "roe_pct": round_or_none(roe),
            "revenue_growth_pct": round_or_none(rev_g),
            "earnings_growth_pct": round_or_none(eps_g),
            "operating_margin_pct": round_or_none(op_margin),
            "gross_margin_pct": round_or_none(gross_margin),
            "piotroski_f_score": piotroski_f,
            "altman_health_score": altman_health,
            "recommendation_mean": round_or_none(rec_mean),
            "analyst_opinions": analyst_n,
            "short_interest_pct_float": round_or_none(short_pct),
            "return_3m_pct": ret3m,
            "return_6m_pct": ret6m,
            "return_12m_pct": ret12m,
            "rsi14": rsi14,
            "ma20": ma20,
            "ma50": ma50,
            "ma200": ma200,
            "above_ma50": above50,
            "above_ma200": above200,
            "price_vs_ma200_pct": price_vs_ma200_pct,
            "ma50_vs_ma200_pct": ma50_vs_ma200_pct,
            "ma200_slope_3m_pct": ma200_slope_3m_pct,
            "atr14": atr14,
            "atr_pct_of_price": atr_pct,
            "proximity_52w_high_pct": prox_52w_high_pct,
            "max_drawdown_6m_pct": max_dd_6m_pct,
            "beta": round_or_none(beta),
            "avg_volume": round_or_none(avg_volume, 0),
            "avg_dollar_volume": round_or_none(avg_dollar_volume, 0),
        },
    }


def score_candidates(collected_rows, horizon=DEFAULT_HORIZON, min_adv=0.0,
                    cost_basis: dict[str, float] | None = None):
    """Score candidates with horizon-weighted value/quality/trend/sentiment/risk pillars.

    Value/quality features are ranked sector-neutrally (within-sector when enough
    peers exist), percentiles are shrunk toward 50 for tiny universes, the
    missing-data confidence penalty is market-aware (US-only fields don't punish
    non-US listings), and each name gets a liquidity flag.

    When ``cost_basis`` is provided, held names trading below their average cost
    receive a quality-pillar boost proportional to the discount (up to +15 pts)
    and are flagged with ``held`` and ``discount_to_cost_pct``.
    """
    hw = HORIZON_WEIGHTS.get(horizon, HORIZON_WEIGHTS[DEFAULT_HORIZON])
    universe = [row.get("features", {}) for row in collected_rows]
    sectors = [row.get("sector") for row in collected_rows]

    # Regularize percentiles when the universe is too small to rank reliably.
    n_uni = len(universe)
    shrink = min(1.0, (n_uni / SMALL_UNIVERSE_N) ** 0.5) if n_uni > 0 else 1.0

    def vals(key):
        return [f.get(key) for f in universe if f.get(key) is not None]

    def sector_vals(key, sector):
        return [
            f.get(key)
            for f, s in zip(universe, sectors)
            if s == sector and f.get(key) is not None
        ]

    def upctl(value, all_vals, higher_better=True):
        """Universe-wide percentile, shrunk toward 50 for small universes."""
        return _shrink_toward_50(
            percentile_score(value, all_vals, higher_better=higher_better), shrink
        )

    def spctl(value, key, sector, all_vals, higher_better=True):
        """Sector-neutral percentile: rank within sector when >= MIN_SECTOR_GROUP peers."""
        grp = sector_vals(key, sector) if sector else []
        use = grp if len(grp) >= MIN_SECTOR_GROUP else all_vals
        return _shrink_toward_50(
            percentile_score(value, use, higher_better=higher_better), shrink
        )

    pe_vals = vals("pe_forward")
    pb_vals = vals("price_to_book")
    div_vals = vals("dividend_yield_pct")
    div_growth_vals = vals("dividend_growth_pct")
    fcf_vals = vals("fcf_yield_pct")
    upside_vals = vals("analyst_upside_pct")

    roe_vals = vals("roe_pct")
    rev_vals = vals("revenue_growth_pct")
    eps_vals = vals("earnings_growth_pct")
    opm_vals = vals("operating_margin_pct")
    gm_vals = vals("gross_margin_pct")

    ret3_vals = vals("return_3m_pct")
    ret6_vals = vals("return_6m_pct")
    ret12_vals = vals("return_12m_pct")
    p200_vals = vals("price_vs_ma200_pct")
    spread_vals = vals("ma50_vs_ma200_pct")
    slope_vals = vals("ma200_slope_3m_pct")

    rec_vals = vals("recommendation_mean")
    short_vals = vals("short_interest_pct_float")

    max_dd_vals = vals("max_drawdown_6m_pct")
    beta_vals = vals("beta")

    scored = []
    for row, sector in zip(collected_rows, sectors):
        f = row.get("features", {})

        # Value + quality: sector-neutral (bank P/E vs software P/E is apples-to-oranges).
        value_parts = [
            spctl(f.get("analyst_upside_pct"), "analyst_upside_pct", sector, upside_vals, True),
            spctl(f.get("pe_forward"), "pe_forward", sector, pe_vals, False),
            spctl(f.get("price_to_book"), "price_to_book", sector, pb_vals, False),
            spctl(f.get("dividend_yield_pct"), "dividend_yield_pct", sector, div_vals, True),
            spctl(f.get("fcf_yield_pct"), "fcf_yield_pct", sector, fcf_vals, True),
        ]
        quality_parts = [
            spctl(f.get("roe_pct"), "roe_pct", sector, roe_vals, True),
            spctl(f.get("revenue_growth_pct"), "revenue_growth_pct", sector, rev_vals, True),
            spctl(f.get("operating_margin_pct"), "operating_margin_pct", sector, opm_vals, True),
            spctl(f.get("gross_margin_pct"), "gross_margin_pct", sector, gm_vals, True),
            spctl(f.get("earnings_growth_pct"), "earnings_growth_pct", sector, eps_vals, True),
            spctl(f.get("dividend_growth_pct"), "dividend_growth_pct", sector, div_growth_vals, True),
            # Absolute biznesradar quality signal (WSE only; None elsewhere -> skipped).
            piotroski_score(f.get("piotroski_f_score")),
        ]
        # Trend: momentum is comparable across sectors -> universe-wide. 12m return
        # lives here (it is momentum, not risk).
        trend_parts = [
            upctl(f.get("return_3m_pct"), ret3_vals, True),
            upctl(f.get("return_6m_pct"), ret6_vals, True),
            upctl(f.get("return_12m_pct"), ret12_vals, True),
            upctl(f.get("price_vs_ma200_pct"), p200_vals, True),
            upctl(f.get("ma50_vs_ma200_pct"), spread_vals, True),
            upctl(f.get("ma200_slope_3m_pct"), slope_vals, True),
            sweet_spot_score(f.get("rsi14"), target=57, slope=3),
            structure_score(row.get("price"), f.get("ma20"), f.get("ma50"), f.get("ma200")),
            sweet_spot_score(f.get("proximity_52w_high_pct"), target=97, slope=4),
        ]
        sentiment_parts = [
            upctl(f.get("recommendation_mean"), rec_vals, False),
            scale(f.get("analyst_opinions"), 0, 30),
            upctl(f.get("short_interest_pct_float"), short_vals, False),
        ]
        # Risk: genuine risk only -> volatility (ATR%), drawdown, beta, plus (WSE only)
        # the Altman EM-Score as a fundamental-solvency term (higher health = safer).
        risk_parts = [
            sweet_spot_score(f.get("atr_pct_of_price"), target=4, slope=15),
            upctl(f.get("max_drawdown_6m_pct"), max_dd_vals, True),
            upctl(f.get("beta"), beta_vals, False),
            f.get("altman_health_score"),
        ]

        value_s = avg(value_parts)
        quality_s = avg(quality_parts)
        trend_s = avg(trend_parts)
        sentiment_s = avg(sentiment_parts)
        risk_s = avg(risk_parts)

        # --- discount-to-cost-basis boost for held names "on sale" ---
        held = False
        discount_pct = None
        discount_bonus = None
        if cost_basis and row.get("symbol") in cost_basis:
            held = True
            avg_cost = cost_basis[row["symbol"]]
            cur_price = row.get("price")
            if avg_cost and cur_price and avg_cost > 0:
                discount_pct = round((avg_cost - cur_price) / avg_cost * 100, 1)
                # Bonus: 0 at <=0% discount, +15 pts at >=30% discount (linear).
                if discount_pct > 0:
                    discount_bonus = round(min(discount_pct / 30.0 * 15.0, 15.0), 1)
                    quality_parts.append(discount_bonus)

        weighted_parts = [
            (value_s, hw["value"]),
            (quality_s, hw["quality"]),
            (trend_s, hw["trend"]),
            (sentiment_s, hw["sentiment"]),
            (risk_s, hw["risk"]),
        ]
        weighted_available = [(s, w) for s, w in weighted_parts if s is not None]
        if weighted_available:
            weight_sum = sum(w for _, w in weighted_available)
            raw_score = sum(s * w for s, w in weighted_available) / weight_sum
        else:
            raw_score = None

        # --- Multi-dimensional confidence scoring ---
        # Uses lib/confidence.py to compute a rich confidence score that
        # considers: weighted completeness per pillar, historical depth,
        # data freshness, source reliability, data quality, and critical
        # field penalties. Market-aware (short interest not required for
        # non-US listings). Replaces the old flat MISSING_DATA_DECAY model.
        is_us = is_us_listing(row.get("symbol"))
        # Import confidence module dynamically (avoid circular deps)
        from lib.confidence import compute_confidence, confidence_adjust  # noqa: E402
        confidence_result = compute_confidence(
            f,
            is_us=is_us,
            biznesradar_enriched=row.get("biznesradar_enriched", False),
            biznesradar_sourced=row.get("biznesradar_sourced"),
        )
        new_confidence_score = confidence_result["confidence_score"]
        screen_score = confidence_adjust(raw_score, new_confidence_score) if raw_score is not None else None

        # Liquidity flag (informational). Floor is the caller's --min-adv when set,
        # else a per-currency soft default in the listing currency.
        adv = f.get("avg_dollar_volume")
        currency = (row.get("currency") or "").upper()
        adv_floor = min_adv if min_adv and min_adv > 0 else DEFAULT_ADV_FLOOR.get(currency, 0.0)
        low_liquidity = bool(adv is not None and adv_floor > 0 and adv < adv_floor)

        row.update({
            "screen_score": screen_score,
            "raw_screen_score": round_or_none(raw_score),
            "confidence_score": new_confidence_score,
            "confidence_level": confidence_result["confidence_level"],
            "pillar_confidence": confidence_result["pillar_confidence"],
            "data_confidence": confidence_result["data_confidence"],
            "confidence_explanations": confidence_result["confidence_explanations"],
            "missing_critical": confidence_result.get("missing_critical", []),
            "missing_data": confidence_result.get("missing_data", []),
            "value_score": value_s,
            "quality_score": quality_s,
            "trend_score": trend_s,
            "momentum_score": trend_s,
            "sentiment_score": sentiment_s,
            "risk_score": risk_s,
            "low_liquidity": low_liquidity,
            "held": held,
            "discount_to_cost_pct": discount_pct,
            "discount_quality_bonus": discount_bonus,
            "signals": {
                "analyst_upside_pct": f.get("analyst_upside_pct"),
                "pe_forward": f.get("pe_forward"),
                "price_to_book": f.get("price_to_book"),
                "dividend_yield_pct": f.get("dividend_yield_pct"),
                "dividend_growth_pct": f.get("dividend_growth_pct"),
                "fcf_yield_pct": f.get("fcf_yield_pct"),
                "roe_pct": f.get("roe_pct"),
                "revenue_growth_pct": f.get("revenue_growth_pct"),
                "earnings_growth_pct": f.get("earnings_growth_pct"),
                "operating_margin_pct": f.get("operating_margin_pct"),
                "gross_margin_pct": f.get("gross_margin_pct"),
                "piotroski_f_score": f.get("piotroski_f_score"),
                "altman_health_score": f.get("altman_health_score"),
                "recommendation_mean": f.get("recommendation_mean"),
                "analyst_opinions": f.get("analyst_opinions"),
                "short_interest_pct_float": f.get("short_interest_pct_float"),
                "return_3m_pct": f.get("return_3m_pct"),
                "return_6m_pct": f.get("return_6m_pct"),
                "return_12m_pct": f.get("return_12m_pct"),
                "rsi14": f.get("rsi14"),
                "above_ma50": f.get("above_ma50"),
                "above_ma200": f.get("above_ma200"),
                "price_vs_ma200_pct": f.get("price_vs_ma200_pct"),
                "ma50_vs_ma200_pct": f.get("ma50_vs_ma200_pct"),
                "ma200_slope_3m_pct": f.get("ma200_slope_3m_pct"),
                "atr14": f.get("atr14"),
                "atr_pct_of_price": f.get("atr_pct_of_price"),
                "proximity_52w_high_pct": f.get("proximity_52w_high_pct"),
                "max_drawdown_6m_pct": f.get("max_drawdown_6m_pct"),
                "beta": f.get("beta"),
                "avg_dollar_volume": f.get("avg_dollar_volume"),
            },
            "data_quality": {
                "coverage_pct": new_confidence_score,
                "sector": sector,
                "low_liquidity": low_liquidity,
                "confidence_level": confidence_result["confidence_level"],
            },
        })
        row.pop("features", None)
        scored.append(row)

    return scored


def load_universe(args):
    tickers = list(PRESETS.get(args.preset, [])) if args.preset else []
    if args.universe:
        with open(args.universe, "r", encoding="utf-8") as fh:
            for ln in fh:
                ticker = ln.split("#")[0].strip().upper()
                if ticker:
                    tickers.append(ticker)
    tickers += [t.upper() for t in args.tickers]
    seen, out = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main():
    p = argparse.ArgumentParser(description="Rank a universe by value/quality/momentum.")
    p.add_argument("tickers", nargs="*", help="Ticker symbols, e.g. AAPL KRU.WA")
    p.add_argument("--preset", choices=sorted(PRESETS), help="Built-in watchlist")
    p.add_argument("--universe", help="Path to a file with one ticker per line")
    p.add_argument("--top", type=int, default=0, help="Keep only the top N (0 = all)")
    p.add_argument("--min-score", type=float, default=0.0, help="Drop below this score")
    p.add_argument("--horizon", choices=sorted(HORIZON_WEIGHTS), default=DEFAULT_HORIZON,
                   help="Investing horizon: short (weeks-months), medium (~1-5y), or "
                        "long (~10-15y). Re-weights the scoring pillars (long favors "
                        "quality/value, short favors trend/sentiment).")
    p.add_argument("--min-adv", type=float, default=0.0,
                   help="Min average daily turnover in the listing currency. Flags names "
                        "below it as low_liquidity; with --drop-illiquid also removes them.")
    p.add_argument("--drop-illiquid", action="store_true",
                   help="Exclude names flagged low_liquidity from the ranking.")
    p.add_argument("--max-per-sector", type=int, default=0,
                   help="Keep at most N names per sector after ranking (0 = no cap). "
                        "Use 2 to create a diversified actionable shortlist.")
    p.add_argument("--biznesradar", action="store_true",
                   help="Enrich .WA (Warsaw/WSE) names from biznesradar.pl: adds Piotroski "
                        "F-Score (quality) + Altman EM-Score (risk) and backfills ROE / P-B "
                        "when yfinance is null. Adds one cached HTTP scrape per .WA name.")
    p.add_argument("--portfolio-file", help="JSON file with average purchase prices: "
                   "[{Ticker, AveragePurchasePricePLN}] or [{symbol, avg}]. Held names "
                   "trading below cost get a quality-pillar bonus (+15 pts max).")
    args = p.parse_args()

    universe = load_universe(args)
    if not universe:
        raise SystemExit("No tickers. Pass symbols, --preset, or --universe.")

    total = len(universe)
    rows = []
    for idx, sym in enumerate(universe, start=1):
        print(f"[{idx}/{total}] reviewing {sym}...", file=sys.stderr, flush=True)
        try:
            rows.append(collect_features(sym, use_biznesradar=args.biznesradar))
        except Exception as exc:
            print(f"[{idx}/{total}] {sym} failed: {exc}", file=sys.stderr, flush=True)
            rows.append({"symbol": sym, "error": str(exc), "screen_score": None})

    cost_basis = None
    if args.portfolio_file:
        import json as _json
        with open(args.portfolio_file, "r", encoding="utf-8") as _fh:
            pf = _json.load(_fh)
        cost_basis = {}
        for entry in pf:
            sym = entry.get("Ticker") or entry.get("symbol")
            avg = entry.get("AveragePurchasePricePLN") or entry.get("avg")
            if sym and avg:
                cost_basis[sym.upper()] = float(avg)
        if cost_basis:
            print(f"  loaded cost basis for {len(cost_basis)} holdings: "
                  f"{', '.join(sorted(cost_basis))}",
                  file=sys.stderr, flush=True)

    rows = score_candidates(rows, horizon=args.horizon, min_adv=args.min_adv,
                           cost_basis=cost_basis)

    if args.drop_illiquid:
        rows = [r for r in rows if not r.get("low_liquidity")]

    ranked = sorted(rows, key=lambda r: (r.get("screen_score") is not None,
                                         r.get("screen_score") or 0), reverse=True)
    ranked = [r for r in ranked if r.get("screen_score") is None
              or r["screen_score"] >= args.min_score]

    sector_capped: list[dict] = []
    excluded_by_sector: list[dict[str, str]] = []
    if args.max_per_sector:
        sector_counts: dict[str, int] = {}
        for row in ranked:
            sector = row.get("sector")
            if not sector:
                sector_capped.append(row)
                continue
            if sector_counts.get(sector, 0) >= args.max_per_sector:
                excluded_by_sector.append({"symbol": row.get("symbol"), "sector": sector})
                continue
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            sector_capped.append(row)
        ranked = sector_capped
    if args.top:
        ranked = ranked[:args.top]

    warnings = []
    if len(universe) < SMALL_UNIVERSE_N:
        warnings.append(
            f"Small universe ({len(universe)} < {SMALL_UNIVERSE_N}): cross-sectional "
            "percentiles are coarse and shrunk toward 50; treat score gaps as weak signals."
        )
    if args.biznesradar:
        n_enriched = sum(1 for r in ranked if r.get("biznesradar_enriched"))
        warnings.append(
            f"biznesradar enrichment ON: {n_enriched} .WA name(s) carry a Piotroski F-Score "
            "(quality) and Altman EM-Score (risk), with ROE/P-B backfilled when yfinance was "
            "null. These absolute signals apply to WSE names only, so mixed US+WSE runs are "
            "less comparable across markets. biznesradar's P/E (C/Z) is trailing and is NOT "
            "used as a forward-P/E fallback."
        )
    if excluded_by_sector:
        warnings.append(
            f"Sector cap (--max-per-sector {args.max_per_sector}) excluded "
            f"{len(excluded_by_sector)} lower-ranked name(s)."
        )

    hw = HORIZON_WEIGHTS[args.horizon]
    emit({
        "universe_size": len(universe),
        "horizon": args.horizon,
        "biznesradar_enrichment": bool(args.biznesradar),
        "pillar_weights": {k: round(v, 2) for k, v in hw.items()},
        "max_per_sector": args.max_per_sector or None,
        "excluded_by_sector": excluded_by_sector,
        "score_basis": "universe_relative_percentile",
        "comparability": (
            "Value/quality are ranked sector-neutrally (within-sector when >= "
            f"{MIN_SECTOR_GROUP} peers, else universe); trend/sentiment/risk are ranked "
            "across the whole universe. Scores are RELATIVE to THIS run's universe and are "
            "NOT comparable across different universes or dates."
        ),
        "warnings": warnings,
        "ranked": ranked,
        "method": (f"screen_score = weighted(value {hw['value']:.0%} + quality {hw['quality']:.0%} + "
                   f"trend {hw['trend']:.0%} + sentiment {hw['sentiment']:.0%} + risk {hw['risk']:.0%}) "
                   f"for horizon '{args.horizon}'. Value/quality use sector-neutral percentiles; "
                   "trend (incl. 3/6/12m returns) and risk (ATR%, drawdown, beta) use universe-wide "
                   "percentiles. Percentiles are shrunk toward 50 for small universes, then the score "
                   "is confidence-adjusted using multi-dimensional evidence quality (completeness, "
                   "historical depth, freshness, source reliability, data quality, and critical-field "
                   "penalties). Short interest is not required for non-US listings. "
                   "Momentum_score is a backward-compatible alias of trend_score."),
        "next_step": "Take the top names into data-scout / the analyst-desk for a full work-up. "
                     "Screen score is a coarse filter, NOT a buy signal.",
        "disclaimer": "Educational screen, not financial advice. yfinance fields can be missing "
                      "for non-US listings; verify before acting.",
    })


if __name__ == "__main__":
    main()
