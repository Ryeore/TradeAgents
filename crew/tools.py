"""CrewAI tools + skill loaders for the analyst desk.

Every tool is a thin wrapper that shells out to the matching ``scripts/*.py``
and returns its JSON payload verbatim. The scripts stay the single source of
truth for all deterministic math (indicators, fundamentals, scorecard, sizing);
the agents only *reason* over the JSON.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Optional, Type

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - allows --plan without deps installed
    class BaseModel:  # type: ignore
        pass

    def Field(default=None, **kwargs):  # type: ignore
        return default

try:
    from crewai.tools import BaseTool
except ImportError:  # pragma: no cover - allows importing without crewai installed
    class BaseTool:  # type: ignore
        name: str = ""
        description: str = ""
        args_schema = None

        def _run(self, *args, **kwargs):
            raise NotImplementedError


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
SKILLS_DIR = os.path.join(REPO_ROOT, "skills")
REPORTS_DIR = os.path.join(REPO_ROOT, "agentReports")


# --------------------------------------------------------------------------- #
# Script runner
# --------------------------------------------------------------------------- #
def run_script(script: str, args: list[str], timeout: int = 240) -> str:
    """Run ``scripts/<script>`` with the current interpreter and return stdout.

    Errors are returned as a JSON string so the agent always gets valid JSON.
    """
    path = os.path.join(SCRIPTS_DIR, script)
    if not os.path.isfile(path):
        return json.dumps({"error": f"script not found: {script}"})
    cmd = [sys.executable, path, *[str(a) for a in args]]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=REPO_ROOT
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"{script} timed out after {timeout}s"})
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if out:
        return out
    return json.dumps({"error": err or f"{script} exited {proc.returncode}", "script": script})


# --------------------------------------------------------------------------- #
# Skill loader (agent personas live in skills/*.md -> single source of truth)
# --------------------------------------------------------------------------- #
_FRONTMATTER = re.compile(r"^\s*---\s*\n.*?\n---\s*\n", re.DOTALL)


def load_skill(rel_path: str) -> str:
    """Return a skill markdown body with its YAML frontmatter stripped."""
    path = os.path.join(SKILLS_DIR, rel_path)
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    return _FRONTMATTER.sub("", text, count=1).strip()


# --------------------------------------------------------------------------- #
# Input schemas
# --------------------------------------------------------------------------- #
class TickerInput(BaseModel):
    ticker: str = Field(..., description="Ticker symbol, e.g. AAPL or CDR.WA (WSE needs .WA)")


class TechnicalsInput(BaseModel):
    ticker: str = Field(..., description="Ticker symbol, e.g. NVDA or KRU.WA")
    period: str = Field("1y", description="Lookback period, e.g. 1y or 2y")


class ScreenInput(BaseModel):
    tickers: Optional[list[str]] = Field(None, description="Explicit tickers to rank")
    preset: Optional[str] = Field(None, description="Built-in watchlist: wse_blue or us_mega")
    universe: Optional[str] = Field(None, description="Path to a file with one ticker per line")
    top: int = Field(0, description="Keep only the top N (0 = all)")
    min_score: float = Field(0.0, description="Drop candidates below this screen score")


class ScorecardInput(BaseModel):
    valuation: float = Field(..., description="Valuation sub-score 1-10")
    quality: float = Field(..., description="Quality / fundamentals sub-score 1-10")
    technical: float = Field(..., description="Technical / timing sub-score 1-10")
    sentiment: float = Field(..., description="Sentiment / positioning sub-score 1-10")
    macro: float = Field(..., description="Macro / risk sub-score 1-10")


class PositionSizerInput(BaseModel):
    price: float = Field(..., description="Current price from the Data Scout")
    atr: float = Field(..., description="ATR(14) from the Chartist")
    conviction: float = Field(..., description="CIO composite conviction score 1-10")
    account: float = Field(..., description="Total account value")
    risk_pct: float = Field(1.0, description="Risk per trade as % of account")
    max_pos_pct: float = Field(12.0, description="Hard cap on position size as % of account")
    atr_stop_mult: float = Field(2.0, description="Stop distance = mult * ATR")
    tranches: int = Field(3, description="Number of DCA buys")


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
class FetchQuoteTool(BaseTool):
    name: str = "fetch_quote"
    description: str = (
        "Live quote snapshot for a ticker: price, day/52wk range, market cap, "
        "trailing/forward EPS, analyst target prices, recommendation and analyst "
        "count, plus web_search_terms. Returns JSON. Input: ticker."
    )
    args_schema: Type[BaseModel] = TickerInput

    def _run(self, ticker: str) -> str:
        return run_script("fetch_quote.py", [ticker])


class FetchFundamentalsTool(BaseTool):
    name: str = "fetch_fundamentals"
    description: str = (
        "Valuation & quality fundamentals: P/E, PEG, EV/EBITDA, EV/Sales, P/B, "
        "FCF yield, ROIC(est), ROE/ROA, margins, growth, balance sheet, ownership, "
        "dividend, and a forward_estimates block (+1y direct, +2y extrapolated). "
        "Returns JSON. Input: ticker."
    )
    args_schema: Type[BaseModel] = TickerInput

    def _run(self, ticker: str) -> str:
        return run_script("fetch_fundamentals.py", [ticker])


class FetchTechnicalsTool(BaseTool):
    name: str = "fetch_technicals"
    description: str = (
        "Technical read: MA20/50/200, RSI(14), MFI(14), ATR(14) and ATR%, 52-week "
        "Fibonacci retracements, swing high/low and a trend label. The ATR here "
        "drives position sizing. Returns JSON. Inputs: ticker, optional period (1y/2y)."
    )
    args_schema: Type[BaseModel] = TechnicalsInput

    def _run(self, ticker: str, period: str = "1y") -> str:
        return run_script("fetch_technicals.py", [ticker, period])


class FetchSentimentTool(BaseTool):
    name: str = "fetch_sentiment"
    description: str = (
        "Positioning read: short interest and days-to-cover, insider transaction "
        "summary, top institutional holders, and the analyst recommendation trend. "
        "Returns JSON. Input: ticker."
    )
    args_schema: Type[BaseModel] = TickerInput

    def _run(self, ticker: str) -> str:
        return run_script("fetch_sentiment.py", [ticker])


class FetchMacroTool(BaseTool):
    name: str = "fetch_macro"
    description: str = (
        "Top-down dashboard: stock vs sector ETF vs S&P 500 6-month relative "
        "performance, plus VIX, 10y/2y yield proxies, USD, oil and gold levels. "
        "Returns JSON. Input: ticker."
    )
    args_schema: Type[BaseModel] = TickerInput

    def _run(self, ticker: str) -> str:
        return run_script("fetch_macro.py", [ticker])


class ScreenCandidatesTool(BaseTool):
    name: str = "screen_candidates"
    description: str = (
        "Rank a universe of tickers by a blended value/quality/momentum screen "
        "score (0-100). Provide any of: tickers list, preset (wse_blue|us_mega), "
        "universe file path; plus optional top and min_score. Returns ranked JSON."
    )
    args_schema: Type[BaseModel] = ScreenInput

    def _run(self, tickers=None, preset=None, universe=None, top=0, min_score=0.0) -> str:
        args: list[str] = []
        if preset:
            args += ["--preset", preset]
        if universe:
            args += ["--universe", universe]
        if top:
            args += ["--top", top]
        if min_score:
            args += ["--min-score", min_score]
        if tickers:
            args += list(tickers)
        if not (preset or universe or tickers):
            return json.dumps({"error": "provide tickers, preset, or universe"})
        return run_script("screen_candidates.py", args)


class ScorecardTool(BaseTool):
    name: str = "scorecard"
    description: str = (
        "CIO 5-dimension scorecard. Pass the five 1-10 sub-scores (valuation, "
        "quality, technical, sentiment, macro). Returns the weighted composite "
        "score, verdict band, and conviction_1_10 as JSON."
    )
    args_schema: Type[BaseModel] = ScorecardInput

    def _run(self, valuation, quality, technical, sentiment, macro) -> str:
        return run_script(
            "scorecard.py",
            ["--valuation", valuation, "--quality", quality, "--technical", technical,
             "--sentiment", sentiment, "--macro", macro],
        )


class PositionSizerTool(BaseTool):
    name: str = "position_sizer"
    description: str = (
        "Portfolio Manager sizing engine. Given price, atr, conviction and account "
        "(plus optional risk_pct, max_pos_pct, atr_stop_mult, tranches), returns the "
        "share count, DCA tranche limit prices, ATR stop, and two R-multiple targets "
        "as JSON. Size is the MIN of risk-based and conviction-capped shares."
    )
    args_schema: Type[BaseModel] = PositionSizerInput

    def _run(self, price, atr, conviction, account, risk_pct=1.0, max_pos_pct=12.0,
             atr_stop_mult=2.0, tranches=3) -> str:
        return run_script(
            "position_sizer.py",
            ["--price", price, "--atr", atr, "--conviction", conviction,
             "--account", account, "--risk-pct", risk_pct, "--max-pos-pct", max_pos_pct,
             "--atr-stop-mult", atr_stop_mult, "--tranches", tranches],
        )


# Registry so the desk can pick tools by name.
def build_tools() -> dict[str, BaseTool]:
    """Instantiate one of each tool, keyed by tool name."""
    instances = [
        FetchQuoteTool(), FetchFundamentalsTool(), FetchTechnicalsTool(),
        FetchSentimentTool(), FetchMacroTool(), ScreenCandidatesTool(),
        ScorecardTool(), PositionSizerTool(),
    ]
    return {t.name: t for t in instances}
