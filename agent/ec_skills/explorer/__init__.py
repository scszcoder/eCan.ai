"""A page explorer that works like an engineer at DevTools (2026-10-31).

browser-use hands its model the whole page as an element dump every step, takes
one JSON action list per step and summarises history away; a model there acts
like a form-filler. This explorer gives a strong model what a developer has:
on-demand views (``snapshot``, ``screenshot``), code (``run_js``), the page's own
traffic (``network``), the page's form data (probe/read/write/revert/try_recipe),
precise input (click by visible text, type a whole string), full history and
free reasoning between actions -- with publish/submit/save/sign-up blocked in code.

``explore_sync(task, store_id=..., start_url=..., domains=[...])`` from a code node.
"""
from .loop import explore, explore_sync

__all__ = ["explore", "explore_sync"]
