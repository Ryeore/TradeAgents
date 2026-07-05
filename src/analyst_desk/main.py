"""Entry points for the AnalystDeskFlow (CrewAI AMP + `crewai run`).

`kickoff()` is the project script the platform runs. Inputs can be supplied
locally via the DESK_INPUTS env var (a JSON object matching DeskState); on
CrewAI AMP they arrive through the automation's /kickoff endpoint.
"""
from __future__ import annotations

import json
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass

from analyst_desk.flow import AnalystDeskFlow


def _inputs() -> dict:
    raw = os.environ.get("DESK_INPUTS")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def kickoff():
    """Run the flow. Locally reads DESK_INPUTS; AMP passes inputs itself."""
    flow = AnalystDeskFlow()
    result = flow.kickoff(inputs=_inputs())
    print(result)
    return result


def plot():
    """Render the flow graph to analyst_desk_flow.html."""
    AnalystDeskFlow().plot()


if __name__ == "__main__":
    kickoff()
