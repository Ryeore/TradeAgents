#!/usr/bin/env python
"""position_sizer.py -- Portfolio Manager sizing engine.

Turns the CIO conviction score + price/volatility into a concrete plan:
position size (risk-based AND conviction-capped), DCA tranches with specific
limit prices, an ATR stop loss, and two profit targets at fixed R multiples.

Usage:
    python scripts/position_sizer.py --price 100 --atr 3.2 --conviction 7 \
        --account 50000

Optional knobs:
    --risk-pct 1.0         risk per trade as % of account (default 1.0)
    --max-pos-pct 12       hard cap on position as % of account (default 12)
    --atr-stop-mult 2.0    stop distance = mult * ATR (default 2.0)
    --tranches 3           number of DCA buys (default 3)
    --tranche-step-atr 1.0 spacing between tranches in ATRs (default 1.0)
    --t1-r 2.0 --t2-r 4.0  profit targets in R multiples (default 2R / 4R)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import emit, round_or_none  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--atr", type=float, required=True, help="ATR(14) in price units")
    p.add_argument("--conviction", type=float, required=True, help="CIO score 1-10")
    p.add_argument("--account", type=float, required=True, help="total account value")
    p.add_argument("--risk-pct", type=float, default=1.0)
    p.add_argument("--max-pos-pct", type=float, default=12.0)
    p.add_argument("--atr-stop-mult", type=float, default=2.0)
    p.add_argument("--tranches", type=int, default=3)
    p.add_argument("--tranche-step-atr", type=float, default=1.0)
    p.add_argument("--t1-r", type=float, default=2.0)
    p.add_argument("--t2-r", type=float, default=4.0)
    args = p.parse_args()

    price, atr, conv, acct = args.price, args.atr, args.conviction, args.account
    conv = max(1.0, min(10.0, conv))

    # --- Stop loss & per-share risk (R) ---------------------------------- #
    stop_distance = args.atr_stop_mult * atr
    stop_price = round(price - stop_distance, 2)
    r_per_share = stop_distance  # 1R in price terms

    # --- Risk-based maximum shares --------------------------------------- #
    dollar_risk = acct * (args.risk_pct / 100.0)
    risk_based_shares = int(dollar_risk / r_per_share) if r_per_share > 0 else 0

    # --- Conviction-based position cap ----------------------------------- #
    # Linearly scale allowed weight from ~25% to 100% of max-pos-pct over conv 4->10.
    conv_factor = max(0.0, min(1.0, (conv - 3.0) / 7.0))
    target_pos_pct = args.max_pos_pct * (0.25 + 0.75 * conv_factor)
    conviction_dollars = acct * (target_pos_pct / 100.0)
    conviction_shares = int(conviction_dollars / price) if price > 0 else 0

    # Final size = the more conservative of the two constraints.
    shares = max(0, min(risk_based_shares, conviction_shares))
    position_value = round(shares * price, 2)
    position_pct = round_or_none(position_value / acct * 100) if acct else None
    binding = ("risk-limit" if risk_based_shares <= conviction_shares
               else "conviction-cap")

    # --- DCA tranches (scale-in below current price) --------------------- #
    n = max(1, args.tranches)
    # Weight earlier tranches lighter, later (cheaper) tranches heavier.
    raw_weights = [1 + i for i in range(n)]  # 1,2,3...
    wsum = sum(raw_weights)
    tranches = []
    allocated = 0
    for i in range(n):
        entry = round(price - i * args.tranche_step_atr * atr, 2)
        w = raw_weights[i] / wsum
        t_shares = int(round(shares * w))
        if i == n - 1:  # last tranche absorbs rounding remainder
            t_shares = max(0, shares - allocated)
        allocated += t_shares
        tranches.append({
            "tranche": i + 1,
            "limit_price": entry,
            "shares": t_shares,
            "approx_cost": round(t_shares * entry, 2),
            "weight_pct": round(w * 100, 1),
        })

    # --- Profit targets at fixed R --------------------------------------- #
    target1 = round(price + args.t1_r * r_per_share, 2)
    target2 = round(price + args.t2_r * r_per_share, 2)

    emit({
        "inputs": {
            "price": price, "atr": atr, "conviction": conv, "account": acct,
            "risk_pct": args.risk_pct, "max_pos_pct": args.max_pos_pct,
            "atr_stop_mult": args.atr_stop_mult,
        },
        "position": {
            "shares": shares,
            "position_value": position_value,
            "position_pct_of_account": position_pct,
            "binding_constraint": binding,
            "risk_based_shares": risk_based_shares,
            "conviction_capped_shares": conviction_shares,
            "dollar_risk_at_stop": round(shares * r_per_share, 2),
            "pct_account_at_risk": round_or_none(shares * r_per_share / acct * 100),
        },
        "stop_loss": {
            "price": stop_price,
            "distance_per_share": round(r_per_share, 2),
            "basis": f"{args.atr_stop_mult}x ATR below entry",
        },
        "dca_tranches": tranches,
        "targets": {
            "target1": {"price": target1, "r_multiple": args.t1_r,
                        "action": "trim 1/3 to 1/2, raise stop to breakeven"},
            "target2": {"price": target2, "r_multiple": args.t2_r,
                        "action": "trim remainder or trail stop"},
        },
        "note": "Size is the MIN of risk-based and conviction-capped shares so a stop-out "
                "never exceeds your risk budget. Tranche prices are limit orders; cancel "
                "lower tranches if the thesis breaks.",
    })


if __name__ == "__main__":
    main()
