"""Deep portfolio allocation: allocate a budget by full-desk CIO conviction.

Unlike the lightweight ``portfolio`` flow (which weights names by the coarse
value/quality/momentum screen score), this driver runs the full analyst desk on
each shortlisted name, parses the CIO conviction (1-10) from each desk's CIO
report, and splits the budget weighted by that conviction.

It is a multi-desk orchestration (N desks + one deterministic allocation), so it
lives outside the single sequential Crew in ``desk.py``. Requires an LLM key
because each desk kicks off the agents; the screen and allocation steps are
deterministic.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Callable, Optional

from .desk import build_desk
from .tools import REPORTS_DIR, run_script

# Reuse the allocation math directly from the script (single source of truth).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import portfolio_allocator  # type: ignore  # noqa: E402


_CONVICTION_PATTERNS = [
    re.compile(r"conviction\b.{0,15}?[=:]\s*[*_`]*\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(r"conviction\b[^0-9]{0,20}([0-9]+(?:\.[0-9]+)?)\s*/\s*10", re.I),
    re.compile(r"composite[_ ]?score\s*[*_`]*\s*[=:]?\s*[*_`]*\s*([0-9]+(?:\.[0-9]+)?)", re.I),
]


def parse_conviction(text: str) -> Optional[float]:
    """Pull the CIO conviction (1-10) out of a CIO report, best-effort."""
    if not text:
        return None
    for pat in _CONVICTION_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                val = float(m.group(1))
            except ValueError:
                continue
            if 0.0 < val <= 10.0:
                return round(val, 2)
    return None


def screen_shortlist(*, tickers: Optional[list[str]] = None, preset: Optional[str] = None,
                     top: int = 6) -> list[dict]:
    """Run the screener to get [{symbol, price, screen_score}] for the universe."""
    args: list[str] = []
    if preset:
        args += ["--preset", preset]
    if tickers:
        args += list(tickers)
    if top:
        args += ["--top", str(top)]
    if not (preset or tickers):
        return []
    payload = json.loads(run_script("screen_candidates.py", args))
    rows = payload.get("ranked", []) if isinstance(payload, dict) else []
    out = []
    for r in rows:
        if r.get("price") is not None:
            out.append({"symbol": r.get("symbol"), "price": r.get("price"),
                        "screen_score": r.get("screen_score")})
    return out


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8-sig") as fh:
            return fh.read()
    except OSError:
        return ""


def run_portfolio_deep(
    budget: float,
    *,
    tickers: Optional[list[str]] = None,
    preset: Optional[str] = None,
    top: int = 6,
    account: Optional[float] = None,
    risk_pct: float = 1.0,
    model: Optional[str] = None,
    flow: str = "conviction",
    max_weight: float = 0.35,
    score_power: float = 1.5,
    verbose: bool = True,
    progress: Callable[[str], None] = print,
) -> dict:
    """Run a full desk per shortlisted name, then allocate `budget` by conviction."""
    top = top or 6
    shortlist = screen_shortlist(tickers=tickers, preset=preset, top=top)
    if not shortlist:
        return {"error": "empty shortlist; pass tickers or a --preset"}

    progress(f"Deep allocation: running the {flow} desk on {len(shortlist)} names...")
    candidates: list[dict] = []
    skipped: list[dict] = []
    for i, row in enumerate(shortlist, 1):
        sym, price, screen = row["symbol"], row["price"], row.get("screen_score")
        progress(f"  [{i}/{len(shortlist)}] {sym} ...")
        conviction = None
        try:
            desk = build_desk(sym, account=account, risk_pct=risk_pct, model=model,
                              flow=flow, verbose=verbose)
            desk.crew.kickoff(inputs=desk.inputs)
            conviction = parse_conviction(_read(os.path.join(desk.reports_dir, "08-the-cio.md")))
        except Exception as exc:  # keep going; one bad name shouldn't sink the run
            progress(f"      desk failed for {sym}: {exc}")
        if conviction is None:
            skipped.append({"symbol": sym, "reason": "no CIO conviction parsed", "screen_score": screen})
            continue
        candidates.append({"symbol": sym, "price": price, "score": conviction,
                           "conviction": conviction, "screen_score": screen})

    if not candidates:
        return {"error": "no convictions could be parsed from the desks", "skipped": skipped}

    alloc = portfolio_allocator.allocate(
        budget, candidates, max_weight=max_weight, score_power=score_power)
    alloc["basis"] = "full-desk CIO conviction (1-10)"
    alloc["skipped"] = skipped

    _write_report(alloc, candidates, budget, flow)
    return alloc


def _write_report(alloc: dict, candidates: list[dict], budget: float, flow: str) -> str:
    """Write a combined deep-allocation markdown report to agentReports/PORTFOLIO/."""
    out_dir = os.path.join(REPORTS_DIR, "PORTFOLIO")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "deep-allocation.md")
    conv = {c["symbol"]: c for c in candidates}
    lines = [
        "# Portfolio Allocation (deep — by CIO conviction)",
        "",
        f"- Budget: **{budget}**",
        f"- Basis: full-desk conviction via the `{flow}` pipeline per name",
        "",
        "| Symbol | Conviction | Weight % | Shares | Cost |",
        "|--------|-----------:|---------:|-------:|-----:|",
    ]
    for a in alloc.get("allocations", []):
        c = conv.get(a["symbol"], {})
        lines.append(f"| {a['symbol']} | {c.get('conviction', '-')} | "
                     f"{a.get('actual_weight_pct', '-')} | {a['shares']} | {a['cost']} |")
    s = alloc.get("summary", {})
    lines += [
        "",
        f"- Deployed: **{s.get('deployed')}**  |  Leftover cash: **{s.get('leftover_cash')}** "
        f"({s.get('cash_pct')}%)",
    ]
    if alloc.get("skipped"):
        lines.append(f"- Skipped (no conviction): {', '.join(x['symbol'] for x in alloc['skipped'])}")
    lines += ["", "_Educational risk framework, not financial advice._"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return path
