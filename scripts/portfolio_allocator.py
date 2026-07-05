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
from lib.common import emit, round_or_none  # noqa: E402


def load_candidates(obj) -> list[dict]:
    """Accept either a bare candidate list or a screen_candidates.py payload."""
    rows = obj.get("ranked", obj) if isinstance(obj, dict) else obj
    out: list[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        score = r.get("score", r.get("screen_score", r.get("conviction")))
        out.append({
            "symbol": r.get("symbol"),
            "price": r.get("price"),
            "score": score,
            "atr": r.get("atr"),
        })
    return out


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
             holdings: list[dict] | None = None) -> dict:
    """Distribute `budget` across candidates weighted by score**score_power."""
    usable = [c for c in candidates
              if c.get("price") and c.get("score") is not None and c["price"] > 0
              and c["score"] >= min_score]
    usable.sort(key=lambda c: c["score"], reverse=True)
    if top:
        usable = usable[:top]

    result = {
        "budget": round_or_none(budget),
        "params": {
            "max_weight_pct": round(max_weight * 100, 1),
            "min_score": min_score,
            "top": top or None,
            "score_power": score_power,
            "cash_reserve_pct": round(reserve_pct * 100, 1),
            "leftover_sweep": sweep,
        },
        "allocations": [],
        "summary": {},
        "note": "Weights scale with score^score_power, capped per name. Shares are whole "
                "units; leftover cash is swept into the highest-scored affordable names "
                "(still under the per-name cap). Educational, not financial advice.",
    }
    if not usable:
        result["summary"] = {"error": "no usable candidates (need price and score)"}
        return result

    raw = {c["symbol"]: float(c["score"]) ** score_power for c in usable}
    tot = sum(raw.values())
    weights = {k: v / tot for k, v in raw.items()} if tot > 0 else raw
    weights = apply_weight_cap(weights, max_weight)

    investable = budget * (1.0 - reserve_pct)
    by_symbol = {c["symbol"]: c for c in usable}
    cap_amount = max_weight * budget

    # --- initial whole-share allocation by target weight ----------------- #
    shares = {sym: int((investable * w) // float(by_symbol[sym]["price"]))
              for sym, w in weights.items()}
    deployed = sum(shares[s] * float(by_symbol[s]["price"]) for s in shares)

    # --- greedy leftover sweep: fill best names first, respect the cap --- #
    if sweep:
        ranked = sorted(usable, key=lambda c: c["score"], reverse=True)
        while True:
            best = None
            for c in ranked:
                sym, price = c["symbol"], float(c["price"])
                cur = shares[sym] * price
                if price <= investable - deployed + 1e-9 and cur + price <= cap_amount + 1e-9:
                    best = sym
                    break
            if best is None:
                break
            shares[best] += 1
            deployed += float(by_symbol[best]["price"])

    dropped = [s for s in shares if shares[s] <= 0]
    allocs = []
    for sym in shares:
        if shares[sym] <= 0:
            continue
        c = by_symbol[sym]
        price = float(c["price"])
        cost = shares[sym] * price
        allocs.append({
            "symbol": sym,
            "price": round_or_none(price),
            "score": round_or_none(c["score"]),
            "target_weight_pct": round_or_none(weights[sym] * 100),
            "shares": shares[sym],
            "cost": round_or_none(cost),
            "actual_weight_pct": round_or_none(cost / budget * 100),
        })
    allocs.sort(key=lambda a: a["cost"], reverse=True)

    summary = {
        "deployed": round_or_none(deployed),
        "leftover_cash": round_or_none(budget - deployed),
        "cash_pct": round_or_none((budget - deployed) / budget * 100) if budget else None,
        "num_positions": len(allocs),
        "dropped_below_one_share": dropped,
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
    args = p.parse_args()

    if args.candidates_file:
        with open(args.candidates_file, "r", encoding="utf-8-sig") as fh:
            obj = json.load(fh)
    else:
        obj = json.loads(args.candidates_json)
    candidates = load_candidates(obj)

    holdings = None
    if args.holdings_file:
        with open(args.holdings_file, "r", encoding="utf-8-sig") as fh:
            holdings = json.load(fh)

    emit(allocate(
        args.budget, candidates, max_weight=args.max_weight, min_score=args.min_score,
        top=args.top, score_power=args.score_power, reserve_pct=args.reserve_pct,
        sweep=not args.no_sweep, holdings=holdings,
    ))


if __name__ == "__main__":
    main()
