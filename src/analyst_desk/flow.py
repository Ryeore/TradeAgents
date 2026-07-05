"""AnalystDeskFlow -- the deployable CrewAI Flow.

Wraps every desk mode behind a single Flow so it can run as one CrewAI AMP
automation. The mode is chosen from the input state and routed to the matching
pipeline, reusing the existing ``crew.desk`` / ``crew.portfolio`` logic:

    mode = "full" | "analysis" | "quick"  -> single-ticker desk
    mode = "screen"                        -> Opportunity Scout screen
    mode = "portfolio" (deep=False)        -> screen + budget allocation
    mode = "portfolio" (deep=True)         -> full desk per name + conviction alloc

AMP exposes the ``DeskState`` fields as the automation's ``/inputs``.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional

# Make the repo packages (crew, scripts, skills) importable regardless of how the
# flow is launched (local, `crewai run`, or AMP where the checkout is the CWD).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from crewai.flow.flow import Flow, listen, router, start  # noqa: E402
from pydantic import BaseModel  # noqa: E402


class DeskState(BaseModel):
    """Inputs for the analyst desk (surfaced as the AMP automation inputs)."""

    mode: str = "full"          # full | analysis | quick | screen | portfolio
    ticker: str = ""            # single ticker, or space/comma list for portfolio
    account: Optional[float] = None
    risk_pct: float = 1.0
    budget: Optional[float] = None
    preset: Optional[str] = None   # wse_blue | us_mega (screen/portfolio)
    top: int = 0
    deep: bool = False             # portfolio: weight by full-desk CIO conviction
    universe: Optional[str] = None
    model: Optional[str] = None
    result: str = ""               # populated with the final output


def _universe_hint(state: DeskState) -> str:
    if state.universe:
        return state.universe
    parts = []
    if state.preset:
        parts.append(f"preset {state.preset}")
    elif state.ticker:
        parts.append(f"tickers {state.ticker}")
    else:
        parts.append("preset us_mega")
    if state.top:
        parts.append(f"top {state.top}")
    return ", ".join(parts)


class AnalystDeskFlow(Flow[DeskState]):
    """Routes an input mode to the matching desk pipeline."""

    @start()
    def dispatch(self) -> str:
        return (self.state.mode or "full").lower()

    @router(dispatch)
    def route(self) -> str:
        mode = (self.state.mode or "full").lower()
        if mode == "portfolio":
            return "deep" if self.state.deep else "portfolio"
        if mode == "screen":
            return "screen"
        return "single"  # full | analysis | quick

    @listen("single")
    def run_single(self) -> str:
        from crew.desk import build_desk

        flow = self.state.mode if self.state.mode in {"full", "analysis", "quick"} else "full"
        if flow == "full" and self.state.account is None:
            flow = "analysis"  # cannot size a position without an account
        desk = build_desk(
            self.state.ticker, account=self.state.account, risk_pct=self.state.risk_pct,
            model=self.state.model, flow=flow, verbose=True,
        )
        self.state.result = str(desk.crew.kickoff(inputs=desk.inputs))
        return self.state.result

    @listen("screen")
    def run_screen(self) -> str:
        from crew.desk import build_desk

        desk = build_desk(
            self.state.ticker or "SCREEN", model=self.state.model, flow="screen",
            universe=_universe_hint(self.state), verbose=True,
        )
        self.state.result = str(desk.crew.kickoff(inputs=desk.inputs))
        return self.state.result

    @listen("portfolio")
    def run_portfolio(self) -> str:
        from crew.desk import build_desk

        desk = build_desk(
            self.state.ticker or "PORTFOLIO", model=self.state.model, flow="portfolio",
            budget=self.state.budget, universe=_universe_hint(self.state), verbose=True,
        )
        self.state.result = str(desk.crew.kickoff(inputs=desk.inputs))
        return self.state.result

    @listen("deep")
    def run_deep(self) -> str:
        from crew.portfolio import run_portfolio_deep

        tickers = None
        if not self.state.preset and self.state.ticker:
            tickers = [t for t in re.split(r"[,\s]+", self.state.ticker) if t]
        alloc = run_portfolio_deep(
            budget=self.state.budget or 0, tickers=tickers, preset=self.state.preset,
            top=self.state.top or 6, account=self.state.account, risk_pct=self.state.risk_pct,
            model=self.state.model, verbose=True,
        )
        self.state.result = json.dumps(alloc, indent=2, default=str)
        return self.state.result
