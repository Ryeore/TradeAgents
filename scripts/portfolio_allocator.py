#!/usr/bin/env python
"""portfolio_allocator.py -- split a cash budget across ranked candidates.

Turns a budget plus a set of scored candidates into a concrete buy plan: a
target weight per name (driven by its score/conviction), the PLN/USD to deploy,
whole-share counts, and the leftover cash. Optionally folds in existing holdings
so the output shows the *combined* portfolio weights after the new money lands.

This is the multi-name counterpart to position_sizer.py (which sizes ONE name).

Candidates may be passed as:
  * a JSON list  [{"symbol","price","score"[,"atr"]}, ...]
  * OR the raw output of screen_candidates.py (has a "ranked" array with
    "screen_score"); this lets you pipe the screener straight in.

Usage:
    python scripts/screen_candidates.py --preset wse_blue --top 8 > screen.json
    python scripts/portfolio_allocator.py --budget 2000 --candidates-file screen.json
    python scripts/portfolio_allocator.py --budget 2000 \
        --candidates-json "[{\"symbol\":\"KRU.WA\",\"price\":400,\"score\":72}]"
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import emit, get_ticker, last_price, round_or_none, safe_info  # noqa: E402


def read_json_file(path: str) -> object:
    """Read JSON from files encoded as UTF-8/UTF-16 with or without BOM."""
    with open(path, "rb") as fh:
        data = fh.read()

    # Prefer explicit BOM detection when present.
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return json.loads(data.decode("utf-16"))
    if data.startswith(b"\xef\xbb\xbf"):
        return json.loads(data.decode("utf-8-sig"))

    # Fallback chain for BOM-less files.
    for enc in ("utf-8", "utf-16"):
        try:
            return json.loads(data.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Unsupported JSON encoding or invalid JSON: {path}")


def load_candidates(obj) -> list[dict]:
    """Accept either a bare candidate list or a screen_candidates.py payload."""
    rows = obj.get("ranked", obj) if isinstance(obj, dict) else obj
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        score = r.get("score", r.get("screen_score", r.get("conviction")))
        data_quality = r.get("data_quality") if isinstance(r.get("data_quality"), dict) else {}
        coverage_pct = data_quality.get("coverage_pct")
        if coverage_pct is None and data_quality.get("coverage_ratio") is not None:
            coverage_pct = float(data_quality.get("coverage_ratio")) * 100.0
        out.append({
            "symbol": r.get("symbol"),
            "price": r.get("price"),
            "currency": r.get("currency"),
            "score": score,
            "atr": r.get("atr"),
            "value_score": r.get("value_score"),
            "quality_score": r.get("quality_score"),
            "trend_score": r.get("trend_score", r.get("momentum_score")),
            "momentum_score": r.get("momentum_score", r.get("trend_score")),
            "sentiment_score": r.get("sentiment_score"),
            "risk_score": r.get("risk_score"),
            "confidence_score": r.get("confidence_score", coverage_pct),
            "raw_screen_score": r.get("raw_screen_score"),
            "screen_score": r.get("screen_score"),
            "conviction": r.get("conviction"),
        })
    return out


def weighted_mean_available(parts: list[tuple[float | None, float]]) -> float | None:
    vals = [(v, w) for v, w in parts if v is not None and w > 0]
    if not vals:
        return None
    wsum = sum(w for _, w in vals)
    if wsum <= 0:
        return None
    return sum(v * w for v, w in vals) / wsum


def confidence_multiplier(confidence_score: float | None, floor: float = 0.7) -> float:
    """Map confidence in [0,100] to a multiplier in [floor,1.0]."""
    if confidence_score is None:
        return 1.0
    c = max(0.0, min(100.0, float(confidence_score)))
    return float(floor + (1.0 - floor) * (c / 100.0))


def derive_allocation_score(
    candidate: dict,
    *,
    use_components: bool,
    apply_confidence: bool,
    confidence_floor: float,
    value_w: float,
    quality_w: float,
    trend_w: float,
    sentiment_w: float,
    risk_w: float,
) -> tuple[float | None, str]:
    """Build an allocation score with graceful fallback to legacy score fields."""
    legacy = candidate.get("score", candidate.get("screen_score", candidate.get("conviction")))

    component_base = None
    if use_components:
        component_base = weighted_mean_available([
            (candidate.get("value_score"), value_w),
            (candidate.get("quality_score"), quality_w),
            (candidate.get("trend_score", candidate.get("momentum_score")), trend_w),
            (candidate.get("sentiment_score"), sentiment_w),
            (candidate.get("risk_score"), risk_w),
        ])

    base = component_base if component_base is not None else legacy
    if base is None:
        return None, "none"

    if apply_confidence:
        mult = confidence_multiplier(candidate.get("confidence_score"), floor=confidence_floor)
        return float(base) * mult, "components+confidence" if component_base is not None else "legacy+confidence"

    return float(base), "components" if component_base is not None else "legacy"


def normalize_currency(symbol: str | None, currency: str | None) -> str:
    """Best-effort currency normalization for candidate rows."""
    cur = (currency or "").strip().upper()
    if cur:
        return cur
    sym = (symbol or "").strip().upper()
    if sym.endswith(".WA"):
        return "PLN"
    return "USD"


def fetch_usdpln_rate() -> float:
    """Fetch USDPLN FX spot from yfinance."""
    ticker = get_ticker("USDPLN=X")
    info = safe_info(ticker)
    rate = last_price(ticker, info)
    if rate is None or rate <= 0:
        raise ValueError("Could not fetch USDPLN rate. Pass --usdpln manually.")
    return float(rate)


def convert_candidates_to_pln(candidates: list[dict], usdpln: float) -> tuple[list[dict], list[dict]]:
    """Return PLN-normalized candidates plus skipped rows with unsupported currency."""
    out: list[dict] = []
    skipped: list[dict] = []
    for c in candidates:
        cur = normalize_currency(c.get("symbol"), c.get("currency"))
        price = c.get("price")
        if price is None:
            out.append({**c, "currency": cur, "price_pln": None})
            continue
        if cur == "PLN":
            price_pln = float(price)
        elif cur == "USD":
            price_pln = float(price) * usdpln
        else:
            skipped.append({
                "symbol": c.get("symbol"),
                "currency": cur,
                "reason": "unsupported currency (only PLN and USD are supported)",
            })
            continue
        out.append({**c, "currency": cur, "price_pln": price_pln})
    return out, skipped


def apply_weight_cap(weights: dict[str, float], cap: float) -> dict[str, float]:
    """Iteratively cap any weight at `cap`, redistributing the excess pro-rata.

    If the caps cannot absorb the full 1.0 (few names, low cap), the shortfall
    is left undeployed (reported as leftover cash) rather than forced in.
    """
    w = dict(weights)
    for _ in range(100):
        excess = 0.0
        for k, v in list(w.items()):
            if v > cap + 1e-12:
                excess += v - cap
                w[k] = cap
        if excess <= 1e-12:
            break
        uncapped = {k: v for k, v in w.items() if v < cap - 1e-12}
        pool = sum(uncapped.values())
        if pool <= 0:
            break  # everyone capped; remainder stays as cash
        for k in uncapped:
            w[k] += excess * (uncapped[k] / pool)
    return w


def allocate(budget: float, candidates: list[dict], *, max_weight: float = 0.35,
             min_score: float = 0.0, top: int = 0, score_power: float = 1.5,
             reserve_pct: float = 0.0, sweep: bool = True,
             holdings: list[dict] | None = None,
             usdpln: float | None = None,
             min_fractional_share: float = 0.5,
             use_component_scores: bool = True,
             apply_confidence: bool = True,
             confidence_floor: float = 0.7,
             value_weight: float = 0.20,
             quality_weight: float = 0.20,
             trend_weight: float = 0.30,
             sentiment_weight: float = 0.20,
             risk_weight: float = 0.10) -> dict:
    """Distribute `budget` across candidates weighted by score**score_power."""
    if usdpln is None:
        usdpln = fetch_usdpln_rate()

    normalized, skipped = convert_candidates_to_pln(candidates, float(usdpln))

    enriched: list[dict] = []
    for c in normalized:
        alloc_score, score_source = derive_allocation_score(
            c,
            use_components=use_component_scores,
            apply_confidence=apply_confidence,
            confidence_floor=confidence_floor,
            value_w=value_weight,
            quality_w=quality_weight,
            trend_w=trend_weight,
            sentiment_w=sentiment_weight,
            risk_w=risk_weight,
        )
        c2 = {**c, "allocation_score": alloc_score, "allocation_score_source": score_source}
        enriched.append(c2)

    usable = [c for c in enriched
              if c.get("price_pln") and c.get("allocation_score") is not None and c["price_pln"] > 0
              and c["allocation_score"] >= min_score]
    usable.sort(key=lambda c: c["allocation_score"], reverse=True)
    if top:
        usable = usable[:top]

    result = {
        "budget": round_or_none(budget),
        "params": {
            "budget_currency": "PLN",
            "fx_usdpln": round_or_none(usdpln, 6),
            "max_weight_pct": round(max_weight * 100, 1),
            "min_score": min_score,
            "top": top or None,
            "score_power": score_power,
            "cash_reserve_pct": round(reserve_pct * 100, 1),
            "leftover_sweep": sweep,
            "min_fractional_share": round_or_none(min_fractional_share),
            "use_component_scores": use_component_scores,
            "apply_confidence": apply_confidence,
            "confidence_floor": round_or_none(confidence_floor),
            "allocation_weights": {
                "value": round_or_none(value_weight),
                "quality": round_or_none(quality_weight),
                "trend": round_or_none(trend_weight),
                "sentiment": round_or_none(sentiment_weight),
                "risk": round_or_none(risk_weight),
            },
        },
        "allocations": [],
        "summary": {},
        "note": "Weights scale with allocation_score^score_power, capped per name. "
                "Allocation score uses component scores (value/quality/trend/sentiment/risk) "
                "when available, otherwise falls back to legacy score/screen_score/conviction. "
                "Shares are whole "
                "units; leftover cash is swept into the highest-scored affordable names "
                "(still under the per-name cap). Budget is PLN; USD prices are converted "
                "using fx_usdpln. Educational, not financial advice.",
    }
    if skipped:
        result["skipped_candidates"] = skipped
    if not usable:
        result["summary"] = {"error": "no usable candidates (need price and allocation score)"}
        return result

    raw = {c["symbol"]: float(c["allocation_score"]) ** score_power for c in usable}
    tot = sum(raw.values())
    weights = {k: v / tot for k, v in raw.items()} if tot > 0 else raw
    weights = apply_weight_cap(weights, max_weight)

    investable = budget * (1.0 - reserve_pct)
    by_symbol = {c["symbol"]: c for c in usable}
    cap_amount = max_weight * budget

    # --- initial allocation by target weight with optional 0.x->1 round-up --- #
    target_shares = {
        sym: (investable * w) / float(by_symbol[sym]["price_pln"]) for sym, w in weights.items()
    }
    rounded_up_symbols: set[str] = set()
    shares: dict[str, int] = {}
    for sym, frac in target_shares.items():
        n = int(frac)
        if n == 0 and min_fractional_share > 0 and frac >= min_fractional_share:
            n = 1
            rounded_up_symbols.add(sym)
        shares[sym] = n

    deployed = sum(shares[s] * float(by_symbol[s]["price_pln"]) for s in shares)

    # If round-up pushes us over budget, trim back the weakest rounded names first.
    if deployed > investable + 1e-9:
        trim_order = sorted(
            [
                s for s in shares if shares[s] > 0
            ],
            key=lambda s: (
                0 if s in rounded_up_symbols else 1,
                by_symbol[s].get("allocation_score") or 0,
                float(by_symbol[s].get("price_pln") or 0),
            ),
        )
        for sym in trim_order:
            while shares[sym] > 0 and deployed > investable + 1e-9:
                shares[sym] -= 1
                deployed -= float(by_symbol[sym]["price_pln"])
            if deployed <= investable + 1e-9:
                break

    rounded_up_buys = [s for s in rounded_up_symbols if shares.get(s, 0) > 0]
    rounded_up_dropped = [s for s in rounded_up_symbols if shares.get(s, 0) <= 0]

    # --- greedy leftover sweep: fill best names first, respect the cap --- #
    if sweep:
        ranked = sorted(usable, key=lambda c: c["allocation_score"], reverse=True)
        while True:
            best = None
            for c in ranked:
                sym, price = c["symbol"], float(c["price_pln"])
                cur = shares[sym] * price
                if price <= investable - deployed + 1e-9 and cur + price <= cap_amount + 1e-9:
                    best = sym
                    break
            if best is None:
                break
            shares[best] += 1
            deployed += float(by_symbol[best]["price_pln"])

    dropped = [s for s in shares if shares[s] <= 0]
    allocs = []
    for sym in shares:
        if shares[sym] <= 0:
            continue
        c = by_symbol[sym]
        price_raw = float(c["price"])
        price_pln = float(c["price_pln"])
        cost = shares[sym] * price_pln
        allocs.append({
            "symbol": sym,
            "currency": c.get("currency"),
            "price": round_or_none(price_raw),
            "price_pln": round_or_none(price_pln),
            "allocation_score": round_or_none(c.get("allocation_score")),
            "allocation_score_source": c.get("allocation_score_source"),
            "score": round_or_none(c.get("score")),
            "screen_score": round_or_none(c.get("screen_score")),
            "conviction": round_or_none(c.get("conviction")),
            "confidence_score": round_or_none(c.get("confidence_score")),
            "value_score": round_or_none(c.get("value_score")),
            "quality_score": round_or_none(c.get("quality_score")),
            "trend_score": round_or_none(c.get("trend_score", c.get("momentum_score"))),
            "sentiment_score": round_or_none(c.get("sentiment_score")),
            "risk_score": round_or_none(c.get("risk_score")),
            "target_weight_pct": round_or_none(weights[sym] * 100),
            "shares": shares[sym],
            "cost": round_or_none(cost),
            "cost_pln": round_or_none(cost),
            "actual_weight_pct": round_or_none(cost / budget * 100),
        })
    allocs.sort(key=lambda a: a["cost"], reverse=True)

    summary = {
        "deployed": round_or_none(deployed),
        "leftover_cash": round_or_none(budget - deployed),
        "cash_pct": round_or_none((budget - deployed) / budget * 100) if budget else None,
        "num_positions": len(allocs),
        "dropped_below_one_share": dropped,
        "rounded_up_to_one_share": sorted(rounded_up_buys),
        "rounded_up_but_trimmed": sorted(rounded_up_dropped),
    }

    if holdings:
        held = {h.get("symbol"): float(h.get("value") or 0) for h in holdings}
        total_after = sum(held.values()) + deployed
        combined = []
        symbols = set(held) | {a["symbol"] for a in allocs}
        buy = {a["symbol"]: a["cost"] for a in allocs}
        for sym in symbols:
            new_val = held.get(sym, 0.0) + buy.get(sym, 0.0)
            combined.append({
                "symbol": sym,
                "held_value": round_or_none(held.get(sym, 0.0)),
                "buy_value": round_or_none(buy.get(sym, 0.0)),
                "post_value": round_or_none(new_val),
                "post_weight_pct": round_or_none(new_val / total_after * 100)
                if total_after else None,
            })
        combined.sort(key=lambda r: r["post_value"] or 0, reverse=True)
        summary["portfolio_after_deploy"] = combined
        summary["portfolio_total_after"] = round_or_none(total_after)

    result["allocations"] = allocs
    result["summary"] = summary
    return result


def main() -> None:
    p = argparse.ArgumentParser(description="Split a budget across ranked candidates.")
    p.add_argument("--budget", type=float, required=True, help="Cash to deploy")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--candidates-file", help="JSON file: candidate list or screener output")
    src.add_argument("--candidates-json", help="JSON string: candidate list or screener output")
    p.add_argument("--holdings-file", help="JSON file: [{symbol, value}] existing holdings")
    p.add_argument("--max-weight", type=float, default=0.35, help="Max weight per name (0-1)")
    p.add_argument("--min-score", type=float, default=0.0, help="Drop candidates below this score")
    p.add_argument("--top", type=int, default=0, help="Keep only the top N candidates")
    p.add_argument("--score-power", type=float, default=1.5,
                   help="Concentration: higher = more into top names (default 1.5)")
    p.add_argument("--reserve-pct", type=float, default=0.0,
                   help="Fraction of budget to keep as cash (0-1)")
    p.add_argument("--no-sweep", action="store_true",
                   help="Disable sweeping leftover cash into affordable top names")
    p.add_argument("--usdpln", type=float,
                   help="Override USDPLN FX rate. If omitted, fetched from yfinance")
    p.add_argument("--min-fractional-share", type=float, default=0.5,
                   help="If target size is >= this fraction of a share, round up to 1 share")
    p.add_argument("--use-legacy-score", action="store_true",
                   help="Disable component-based allocation score and use legacy score fields only")
    p.add_argument("--no-confidence", action="store_true",
                   help="Disable confidence-based score adjustment")
    p.add_argument("--confidence-floor", type=float, default=0.7,
                   help="Minimum multiplier for confidence adjustment (0-1)")
    p.add_argument("--w-value", type=float, default=0.20,
                   help="Allocation component weight: value")
    p.add_argument("--w-quality", type=float, default=0.20,
                   help="Allocation component weight: quality")
    p.add_argument("--w-trend", type=float, default=0.30,
                   help="Allocation component weight: trend")
    p.add_argument("--w-sentiment", type=float, default=0.20,
                   help="Allocation component weight: sentiment")
    p.add_argument("--w-risk", type=float, default=0.10,
                   help="Allocation component weight: risk")
    args = p.parse_args()

    if args.candidates_file:
        obj = read_json_file(args.candidates_file)
    else:
        obj = json.loads(args.candidates_json)
    candidates = load_candidates(obj)

    holdings = None
    if args.holdings_file:
        holdings = read_json_file(args.holdings_file)

    emit(allocate(
        args.budget, candidates, max_weight=args.max_weight, min_score=args.min_score,
        top=args.top, score_power=args.score_power, reserve_pct=args.reserve_pct,
        sweep=not args.no_sweep, holdings=holdings, usdpln=args.usdpln,
        min_fractional_share=args.min_fractional_share,
        use_component_scores=not args.use_legacy_score,
        apply_confidence=not args.no_confidence,
        confidence_floor=args.confidence_floor,
        value_weight=args.w_value,
        quality_weight=args.w_quality,
        trend_weight=args.w_trend,
        sentiment_weight=args.w_sentiment,
        risk_weight=args.w_risk,
    ))


if __name__ == "__main__":
    main()
