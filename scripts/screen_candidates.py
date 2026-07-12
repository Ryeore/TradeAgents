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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import (  # noqa: E402
    atr, emit, get_ticker, history, last_price, round_or_none, rsi, safe_info, sma,
)

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
                          "MBR.WA", "SNT.WA", "ASB.WA", "NVDA", "AVGO", "MU"],
    "current_pl": ["KRU.WA", "XTB.WA", "DIA.WA", "CBF.WA", "ACP.WA", "PKO.WA",
                          "MBR.WA", "SNT.WA", "ASB.WA"]
}


# (Removed TEMP_PRESETS; rely on git history or add a real preset name instead of keeping commented-out lists.)


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


def _latest(series):
    if series is None:
        return None
    valid = series.dropna()
    if valid.empty:
        return None
    return float(valid.iloc[-1])


def collect_features(symbol):
    """Collect raw value, quality, trend, sentiment, and risk features for one symbol."""
    ticker = get_ticker(symbol)
    info = safe_info(ticker)
    price = last_price(ticker, info)
    df = history(ticker, period="2y")

    target = info.get("targetMeanPrice")
    upside = (target / price - 1) * 100 if price and target else None
    pe_fwd = info.get("forwardPE")
    pb = info.get("priceToBook")
    div = info.get("dividendYield")
    div = div * 100 if div and div < 1 else div
    if div is not None and div > 25:
        div = None
    roe = _pct(info.get("returnOnEquity"))
    rev_g = _pct(info.get("revenueGrowth"))
    op_margin = _pct(info.get("operatingMargins"))
    gross_margin = _pct(info.get("grossMargins"))
    rec_mean = info.get("recommendationMean")
    analyst_n = info.get("numberOfAnalystOpinions")
    short_pct = _pct(info.get("shortPercentOfFloat"))

    fcf_yield = None
    market_cap = info.get("marketCap")
    free_cashflow = info.get("freeCashflow")
    if market_cap and free_cashflow:
        fcf_yield = (free_cashflow / market_cap) * 100

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

    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName"),
        "price": round_or_none(price),
        "currency": info.get("currency"),
        "features": {
            "analyst_upside_pct": round_or_none(upside),
            "pe_forward": round_or_none(pe_fwd),
            "price_to_book": round_or_none(pb),
            "dividend_yield_pct": round_or_none(div),
            "fcf_yield_pct": round_or_none(fcf_yield),
            "roe_pct": round_or_none(roe),
            "revenue_growth_pct": round_or_none(rev_g),
            "operating_margin_pct": round_or_none(op_margin),
            "gross_margin_pct": round_or_none(gross_margin),
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
        },
    }


def score_candidates(collected_rows):
    """Score candidates with weighted value/quality/trend/sentiment/risk pillars."""
    universe = [row.get("features", {}) for row in collected_rows]

    def vals(key):
        return [f.get(key) for f in universe if f.get(key) is not None]

    pe_vals = vals("pe_forward")
    pb_vals = vals("price_to_book")
    div_vals = vals("dividend_yield_pct")
    fcf_vals = vals("fcf_yield_pct")
    upside_vals = vals("analyst_upside_pct")

    roe_vals = vals("roe_pct")
    rev_vals = vals("revenue_growth_pct")
    opm_vals = vals("operating_margin_pct")
    gm_vals = vals("gross_margin_pct")

    ret3_vals = vals("return_3m_pct")
    ret6_vals = vals("return_6m_pct")
    p200_vals = vals("price_vs_ma200_pct")
    spread_vals = vals("ma50_vs_ma200_pct")
    slope_vals = vals("ma200_slope_3m_pct")

    rec_vals = vals("recommendation_mean")
    short_vals = vals("short_interest_pct_float")

    max_dd_vals = vals("max_drawdown_6m_pct")

    scored = []
    for row in collected_rows:
        f = row.get("features", {})

        value_parts = [
            percentile_score(f.get("analyst_upside_pct"), upside_vals, higher_better=True),
            percentile_score(f.get("pe_forward"), pe_vals, higher_better=False),
            percentile_score(f.get("price_to_book"), pb_vals, higher_better=False),
            percentile_score(f.get("dividend_yield_pct"), div_vals, higher_better=True),
            percentile_score(f.get("fcf_yield_pct"), fcf_vals, higher_better=True),
        ]
        quality_parts = [
            percentile_score(f.get("roe_pct"), roe_vals, higher_better=True),
            percentile_score(f.get("revenue_growth_pct"), rev_vals, higher_better=True),
            percentile_score(f.get("operating_margin_pct"), opm_vals, higher_better=True),
            percentile_score(f.get("gross_margin_pct"), gm_vals, higher_better=True),
        ]
        trend_parts = [
            percentile_score(f.get("return_3m_pct"), ret3_vals, higher_better=True),
            percentile_score(f.get("return_6m_pct"), ret6_vals, higher_better=True),
            percentile_score(f.get("price_vs_ma200_pct"), p200_vals, higher_better=True),
            percentile_score(f.get("ma50_vs_ma200_pct"), spread_vals, higher_better=True),
            percentile_score(f.get("ma200_slope_3m_pct"), slope_vals, higher_better=True),
            sweet_spot_score(f.get("rsi14"), target=57, slope=3),
            structure_score(row.get("price"), f.get("ma20"), f.get("ma50"), f.get("ma200")),
            sweet_spot_score(f.get("proximity_52w_high_pct"), target=97, slope=4),
        ]
        sentiment_parts = [
            percentile_score(f.get("recommendation_mean"), rec_vals, higher_better=False),
            scale(f.get("analyst_opinions"), 0, 30),
            percentile_score(f.get("short_interest_pct_float"), short_vals, higher_better=False),
        ]
        risk_parts = [
            sweet_spot_score(f.get("atr_pct_of_price"), target=4, slope=15),
            percentile_score(f.get("max_drawdown_6m_pct"), max_dd_vals, higher_better=True),
            scale(f.get("return_12m_pct"), -40, 60),
        ]

        value_s = avg(value_parts)
        quality_s = avg(quality_parts)
        trend_s = avg(trend_parts)
        sentiment_s = avg(sentiment_parts)
        risk_s = avg(risk_parts)

        weighted_parts = [
            (value_s, 0.20),
            (quality_s, 0.20),
            (trend_s, 0.30),
            (sentiment_s, 0.20),
            (risk_s, 0.10),
        ]
        weighted_available = [(s, w) for s, w in weighted_parts if s is not None]
        if weighted_available:
            weight_sum = sum(w for _, w in weighted_available)
            raw_score = sum(s * w for s, w in weighted_available) / weight_sum
        else:
            raw_score = None

        required_features = [
            f.get("analyst_upside_pct"), f.get("pe_forward"), f.get("price_to_book"),
            f.get("roe_pct"), f.get("revenue_growth_pct"), f.get("return_3m_pct"),
            f.get("return_6m_pct"), f.get("rsi14"), f.get("ma50"), f.get("ma200"),
            f.get("recommendation_mean"), f.get("short_interest_pct_float"),
            f.get("atr_pct_of_price"),
        ]
        present = sum(1 for x in required_features if x is not None)
        coverage_ratio = present / len(required_features) if required_features else 0.0
        confidence_multiplier = 0.7 + 0.3 * coverage_ratio
        screen_score = round(raw_score * confidence_multiplier, 1) if raw_score is not None else None

        row.update({
            "screen_score": screen_score,
            "raw_screen_score": round_or_none(raw_score),
            "confidence_score": round_or_none(coverage_ratio * 100),
            "value_score": value_s,
            "quality_score": quality_s,
            "trend_score": trend_s,
            "momentum_score": trend_s,
            "sentiment_score": sentiment_s,
            "risk_score": risk_s,
            "signals": {
                "analyst_upside_pct": f.get("analyst_upside_pct"),
                "pe_forward": f.get("pe_forward"),
                "price_to_book": f.get("price_to_book"),
                "dividend_yield_pct": f.get("dividend_yield_pct"),
                "fcf_yield_pct": f.get("fcf_yield_pct"),
                "roe_pct": f.get("roe_pct"),
                "revenue_growth_pct": f.get("revenue_growth_pct"),
                "operating_margin_pct": f.get("operating_margin_pct"),
                "gross_margin_pct": f.get("gross_margin_pct"),
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
            },
            "data_quality": {
                "coverage_ratio": round_or_none(coverage_ratio),
                "coverage_pct": round_or_none(coverage_ratio * 100),
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
    args = p.parse_args()

    universe = load_universe(args)
    if not universe:
        raise SystemExit("No tickers. Pass symbols, --preset, or --universe.")

    total = len(universe)
    rows = []
    for idx, sym in enumerate(universe, start=1):
        print(f"[{idx}/{total}] reviewing {sym}...", file=sys.stderr, flush=True)
        try:
            rows.append(collect_features(sym))
        except Exception as exc:
            print(f"[{idx}/{total}] {sym} failed: {exc}", file=sys.stderr, flush=True)
            rows.append({"symbol": sym, "error": str(exc), "screen_score": None})

    rows = score_candidates(rows)

    ranked = sorted(rows, key=lambda r: (r.get("screen_score") is not None,
                                         r.get("screen_score") or 0), reverse=True)
    ranked = [r for r in ranked if r.get("screen_score") is None
              or r["screen_score"] >= args.min_score]
    if args.top:
        ranked = ranked[:args.top]

    emit({
        "universe_size": len(universe),
        "ranked": ranked,
        "method": "screen_score = weighted(value 20% + quality 20% + trend 30% + "
                  "sentiment 20% + risk 10%), all 0-100 and percentile-normalized within "
                  "the screened universe, then confidence-adjusted by data coverage. "
                  "Momentum_score is kept as a backward-compatible alias of trend_score.",
        "next_step": "Take the top names into data-scout / the analyst-desk for a full work-up. "
                     "Screen score is a coarse filter, NOT a buy signal.",
        "disclaimer": "Educational screen, not financial advice. yfinance fields can be missing "
                      "for non-US listings; verify before acting.",
    })


if __name__ == "__main__":
    main()
