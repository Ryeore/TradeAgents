"""CrewAI conversion of the 9-analyst investment committee.

This package wires the existing deterministic data/math scripts (``scripts/``)
and the analyst persona playbooks (``skills/``) into a CrewAI multi-agent crew.

- ``tools``  -- CrewAI tools that wrap the ``scripts/*.py`` (single source of math).
- ``desk``   -- builds the agents, tasks, and the sequential crew pipeline.
- ``main``   -- command-line entry point.

Nothing here duplicates the math or the personas: tools shell out to the same
scripts the README documents, and agent backstories are loaded live from the
``skills/*/*.md`` files, so the markdown remains the single source of truth.
"""
from __future__ import annotations

__all__ = ["build_desk", "run_desk"]


def __getattr__(name):  # lazy import so `import crew` works without crewai installed
    if name in ("build_desk", "run_desk"):
        from .desk import build_desk, run_desk

        return {"build_desk": build_desk, "run_desk": run_desk}[name]
    raise AttributeError(name)
