#!/usr/bin/env python
"""view_results.py -- readable dashboard for screener/allocation JSON outputs.

Builds a compact terminal view and optional markdown report from:
1) screen_candidates.py output (ranked list)
2) portfolio_allocator.py output (allocations + summary)

Usage:
    python scripts/view_results.py --screen-file screen.json
    python scripts/view_results.py --allocation-file alloc.json
    python scripts/view_results.py --screen-file screen.json --allocation-file alloc.json --out-md output/dashboard.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_json_file(path: str) -> Any:
    """Read JSON from UTF-8/UTF-16 files with or without BOM."""
    data = Path(path).read_bytes()

    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return json.loads(data.decode("utf-16"))
    if data.startswith(b"\xef\xbb\xbf"):
        return json.loads(data.decode("utf-8-sig"))

    for enc in ("utf-8", "utf-16"):
        try:
            return json.loads(data.decode(enc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
    raise ValueError(f"Unsupported JSON encoding or invalid JSON: {path}")


def fmt_num(val: Any, ndigits: int = 1, suffix: str = "") -> str:
    if val is None:
        return "-"
    try:
        return f"{float(val):.{ndigits}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def trend_emoji(score: Any) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "-"
    if s >= 70:
        return "UP"
    if s >= 50:
        return "FLAT"
    return "DOWN"


def confidence_flag(score: Any) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "NA"
    if s >= 90:
        return "HIGH"
    if s >= 75:
        return "MED"
    return "LOW"


def to_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(parts: list[str]) -> str:
        return " | ".join(parts[i].ljust(widths[i]) for i in range(len(parts)))

    sep = "-+-".join("-" * w for w in widths)
    out = [line(headers), sep]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def render_screen(screen: dict, top: int) -> tuple[str, str]:
    ranked = screen.get("ranked") or []
    ranked = ranked[:top] if top > 0 else ranked

    headers = [
        "Rank", "Symbol", "Score", "Trend", "Sent", "Risk", "Conf", "Flag"
    ]
    rows: list[list[str]] = []
    for i, r in enumerate(ranked, start=1):
        rows.append([
            str(i),
            str(r.get("symbol") or "-"),
            fmt_num(r.get("screen_score")),
            fmt_num(r.get("trend_score", r.get("momentum_score"))),
            fmt_num(r.get("sentiment_score")),
            fmt_num(r.get("risk_score")),
            fmt_num(r.get("confidence_score"), suffix="%"),
            trend_emoji(r.get("trend_score", r.get("momentum_score"))),
        ])

    terminal = []
    terminal.append("SCREEN DASHBOARD")
    terminal.append(f"Universe: {screen.get('universe_size', '-')}  |  Showing: {len(rows)}")
    terminal.append(to_table(headers, rows) if rows else "No ranked rows found.")

    md = []
    md.append("## Screen Dashboard")
    md.append("")
    md.append(f"- Universe size: {screen.get('universe_size', '-')}")
    md.append(f"- Rows shown: {len(rows)}")
    md.append("")
    md.append("| Rank | Symbol | Score | Trend | Sent | Risk | Conf | Flag |")
    md.append("|---:|:---|---:|---:|---:|---:|---:|:---:|")
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} | {r[7]} |")
    md.append("")
    return "\n".join(terminal), "\n".join(md)


def render_alloc(alloc: dict, top: int) -> tuple[str, str]:
    rows_src = alloc.get("allocations") or []
    rows_src = rows_src[:top] if top > 0 else rows_src

    headers = [
        "Symbol", "A.Score", "Weight%", "Shares", "Cost PLN", "Conf", "Source"
    ]
    rows: list[list[str]] = []
    for r in rows_src:
        rows.append([
            str(r.get("symbol") or "-"),
            fmt_num(r.get("allocation_score")),
            fmt_num(r.get("actual_weight_pct"), suffix="%"),
            str(r.get("shares") if r.get("shares") is not None else "-"),
            fmt_num(r.get("cost_pln"), 2),
            confidence_flag(r.get("confidence_score")),
            str(r.get("allocation_score_source") or "-"),
        ])

    summary = alloc.get("summary") or {}
    terminal = []
    terminal.append("ALLOCATION DASHBOARD")
    terminal.append(
        "Deployed: "
        + fmt_num(summary.get("deployed"), 2)
        + " PLN"
        + "  |  Leftover: "
        + fmt_num(summary.get("leftover_cash"), 2)
        + " PLN"
        + "  |  Cash: "
        + fmt_num(summary.get("cash_pct"), suffix="%")
    )
    terminal.append(to_table(headers, rows) if rows else "No allocation rows found.")

    md = []
    md.append("## Allocation Dashboard")
    md.append("")
    md.append(f"- Deployed: {fmt_num(summary.get('deployed'), 2)} PLN")
    md.append(f"- Leftover cash: {fmt_num(summary.get('leftover_cash'), 2)} PLN")
    md.append(f"- Cash pct: {fmt_num(summary.get('cash_pct'), suffix='%')}")
    md.append("")
    md.append("| Symbol | A.Score | Weight% | Shares | Cost PLN | Conf | Source |")
    md.append("|:---|---:|---:|---:|---:|:---:|:---|")
    for r in rows:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {r[6]} |")
    md.append("")
    return "\n".join(terminal), "\n".join(md)


def main() -> None:
    p = argparse.ArgumentParser(description="Show readable dashboards for screen/allocator JSON files.")
    p.add_argument("--screen-file", help="Path to screen_candidates.py JSON output")
    p.add_argument("--allocation-file", help="Path to portfolio_allocator.py JSON output")
    p.add_argument("--top", type=int, default=10, help="Rows to show from each section (0 = all)")
    p.add_argument("--out-md", help="Optional path to write a markdown report")
    args = p.parse_args()

    if not args.screen_file and not args.allocation_file:
        raise SystemExit("Pass at least one of --screen-file or --allocation-file")

    terminal_blocks: list[str] = []
    md_blocks: list[str] = ["# Results Dashboard", ""]

    if args.screen_file:
        screen = read_json_file(args.screen_file)
        if not isinstance(screen, dict):
            raise SystemExit("Screen file must contain a JSON object.")
        t, m = render_screen(screen, args.top)
        terminal_blocks.append(t)
        md_blocks.append(m)

    if args.allocation_file:
        alloc = read_json_file(args.allocation_file)
        if not isinstance(alloc, dict):
            raise SystemExit("Allocation file must contain a JSON object.")
        t, m = render_alloc(alloc, args.top)
        terminal_blocks.append(t)
        md_blocks.append(m)

    print("\n\n".join(terminal_blocks))

    if args.out_md:
        out_path = Path(args.out_md)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(md_blocks) + "\n", encoding="utf-8")
        print(f"\nSaved markdown dashboard to: {out_path}")


if __name__ == "__main__":
    main()
