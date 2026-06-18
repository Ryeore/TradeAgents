#!/usr/bin/env python
"""scorecard.py -- CIO 5-dimension 1-10 scorecard + weighted verdict.

The CIO passes its dimension scores in; this script enforces the rubric,
computes a weighted composite, and maps it to a verdict band.

Usage:
    python scripts/scorecard.py --valuation 7 --quality 8 --technical 6 \
        --sentiment 5 --macro 6
    # optional custom weights (must sum ~1.0):
    python scripts/scorecard.py --valuation 7 --quality 8 --technical 6 \
        --sentiment 5 --macro 6 --w-valuation 0.30 --w-quality 0.30 \
        --w-technical 0.15 --w-sentiment 0.10 --w-macro 0.15
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.common import emit  # noqa: E402

DIMENSIONS = ["valuation", "quality", "technical", "sentiment", "macro"]
DEFAULT_WEIGHTS = {
    "valuation": 0.25,
    "quality": 0.25,
    "technical": 0.20,
    "sentiment": 0.15,
    "macro": 0.15,
}


def verdict_band(score: float) -> str:
    if score >= 8.0:
        return "STRONG BUY"
    if score >= 6.5:
        return "BUY"
    if score >= 5.0:
        return "ACCUMULATE / STARTER"
    if score >= 3.5:
        return "HOLD / WATCH"
    return "AVOID / SELL"


def main() -> None:
    p = argparse.ArgumentParser()
    for d in DIMENSIONS:
        p.add_argument(f"--{d}", type=float, required=True, help=f"{d} score 1-10")
        p.add_argument(f"--w-{d}", type=float, default=DEFAULT_WEIGHTS[d])
    args = vars(p.parse_args())

    scores = {d: max(1.0, min(10.0, args[d])) for d in DIMENSIONS}
    weights = {d: args[f"w_{d}"] for d in DIMENSIONS}
    wsum = sum(weights.values())
    weights = {d: w / wsum for d, w in weights.items()}  # normalize

    composite = round(sum(scores[d] * weights[d] for d in DIMENSIONS), 2)

    emit({
        "scores": {d: round(scores[d], 1) for d in DIMENSIONS},
        "weights": {d: round(weights[d], 3) for d in DIMENSIONS},
        "composite_score": composite,
        "verdict": verdict_band(composite),
        "conviction_1_10": composite,
        "rubric": {
            "9-10": "Exceptional, rare. Asymmetric upside, low risk.",
            "7-8": "Strong. Clear edge on the dimension.",
            "5-6": "Neutral / fair. No strong edge either way.",
            "3-4": "Weak. Headwinds outweigh tailwinds.",
            "1-2": "Severe red flag on this dimension.",
        },
        "note": "Feed composite_score into position_sizer.py as --conviction.",
    })


if __name__ == "__main__":
    main()
