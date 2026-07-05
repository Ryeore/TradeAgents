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
    p.add_argument("--budget", type=float, default=None,
                   help="Cash budget to deploy across names (with --portfolio)")
    p.add_argument("--universe", default=None,
                   help="Screen universe hint, e.g. 'preset wse_blue' or 'tickers KRU.WA CDR.WA'")
    p.add_argument("--model", default=None,
                   help="LLM model id (default env ANALYST_DESK_MODEL or gpt-4o-mini)")

    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--analysis", action="store_true",
                      help="Run analysts 1-8 + final report (no position sizing)")
    mode.add_argument("--quick", action="store_true",
                      help="Run the Data Scout snapshot only")
    mode.add_argument("--screen", action="store_true",
                      help="Run the Opportunity Scout screener only")
    mode.add_argument("--portfolio", action="store_true",
                      help="Screen a universe then split --budget across the best names")

    p.add_argument("--preset", help="Screener preset: wse_blue or us_mega (with --screen/--portfolio)")
    p.add_argument("--top", type=int, default=0, help="Screener: keep top N (with --screen/--portfolio)")
    p.add_argument("--quiet", action="store_true", help="Reduce agent step logging")
    p.add_argument("--plan", action="store_true",
                   help="Print the pipeline plan and exit (no LLM/API key required)")
    return p


def resolve_flow(args) -> str:
    if args.portfolio:
        return "portfolio"
    if args.screen:
        return "screen"
    if args.quick:
        return "quick"
    if args.analysis:
        return "analysis"
    return "full"


def universe_hint(args) -> str:
    parts = []
    if args.preset:
        parts.append(f"preset {args.preset}")
    elif args.ticker:
        parts.append(f"tickers {args.ticker}")
    else:
        parts.append("preset us_mega")
    if args.top:
        parts.append(f"top {args.top}")
    return ", ".join(parts)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    flow = resolve_flow(args)

    if flow not in ("screen", "portfolio") and not args.ticker:
        print("error: a ticker is required (or use --screen / --portfolio).", file=sys.stderr)
        return 2
    if flow == "portfolio" and not args.budget:
        print("error: --portfolio requires --budget (e.g. --budget 2000).", file=sys.stderr)
        return 2
    if flow == "full" and args.account is None:
        # No account -> fall back to analysis-only (can't size a position).
        flow = "analysis"

    if args.plan:
        from .desk import describe_pipeline

        print(describe_pipeline(
            ticker=(args.ticker or "TICKER").upper(), flow=flow,
            account=args.account, risk_pct=args.risk,
            budget=args.budget, universe=universe_hint(args),
        ))
        return 0

    from .desk import build_desk

    if flow in ("screen", "portfolio"):
        desk = build_desk(
            ticker=args.ticker or "PORTFOLIO", model=args.model, flow=flow,
            budget=args.budget, universe=universe_hint(args), verbose=not args.quiet,
        )
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
