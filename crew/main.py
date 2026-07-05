"""Command-line entry point for the CrewAI analyst desk.

Examples:
    python -m crew.main AAPL --account 50000 --risk 1
    python -m crew.main CDR.WA --analysis
    python -m crew.main NVDA --quick
    python -m crew.main --screen --preset wse_blue --top 8
    python -m crew.main AAPL --plan            # dry run, no LLM/API key needed
"""
from __future__ import annotations

import argparse
import sys

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crew.main",
        description="Run the 9-analyst investment committee as a CrewAI crew.",
    )
    p.add_argument("ticker", nargs="?", help="Ticker symbol, e.g. AAPL or CDR.WA")
    p.add_argument("--account", type=float, default=None,
                   help="Account value; enables the Portfolio Manager sizing stage")
    p.add_argument("--risk", type=float, default=1.0,
                   help="Risk per trade as %% of account (default 1.0)")
    p.add_argument("--model", default=None,
                   help="LLM model id (default env ANALYST_DESK_MODEL or gpt-4o-mini)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--analysis", action="store_true",
                      help="Run analysts 1-8 + final report (no position sizing)")
    mode.add_argument("--quick", action="store_true",
                      help="Run the Data Scout snapshot only")
    mode.add_argument("--screen", action="store_true",
                      help="Run the Opportunity Scout screener only")

    p.add_argument("--preset", help="Screener preset: wse_blue or us_mega (with --screen)")
    p.add_argument("--top", type=int, default=0, help="Screener: keep top N (with --screen)")
    p.add_argument("--quiet", action="store_true", help="Reduce agent step logging")
    p.add_argument("--plan", action="store_true",
                   help="Print the pipeline plan and exit (no LLM/API key required)")
    return p


def resolve_flow(args) -> str:
    if args.screen:
        return "screen"
    if args.quick:
        return "quick"
    if args.analysis:
        return "analysis"
    return "full"


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    flow = resolve_flow(args)

    if flow != "screen" and not args.ticker:
        print("error: a ticker is required (or use --screen).", file=sys.stderr)
        return 2
    if flow == "full" and args.account is None:
        # No account -> fall back to analysis-only (can't size a position).
        flow = "analysis"

    if args.plan:
        from .desk import describe_pipeline

        print(describe_pipeline(
            ticker=(args.ticker or "TICKER").upper(), flow=flow,
            account=args.account, risk_pct=args.risk,
        ))
        return 0

    from .desk import build_desk

    if flow == "screen":
        # Screener flow: pass universe selection through the task description.
        desk = build_desk(ticker=args.ticker or "SCREEN", model=args.model,
                          flow="screen", verbose=not args.quiet)
        hint = []
        if args.preset:
            hint.append(f"preset={args.preset}")
        if args.top:
            hint.append(f"top={args.top}")
        if args.ticker:
            hint.append(f"tickers={args.ticker}")
        desk.inputs["screen_hint"] = ", ".join(hint) or "preset=us_mega"
        result = desk.crew.kickoff(inputs=desk.inputs)
    else:
        desk = build_desk(
            ticker=args.ticker, account=args.account, risk_pct=args.risk,
            model=args.model, flow=flow, verbose=not args.quiet,
        )
        result = desk.crew.kickoff(inputs=desk.inputs)

    print("\n" + "=" * 70)
    print(f"Desk complete. Reports written to: {desk.reports_dir}")
    print("=" * 70)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
