"""Browser-automation node package.

This package decomposes the original ``build_browser_automation_node``
factory (formerly ~5,000 lines in ``agent/ec_skills/build_node.py``)
into single-responsibility modules:

* ``config``  — ``NodeConfig`` dataclass + ``parse_node_config``.
  Parses ``config_metadata["inputsValues"]`` once at build time.

* ``events`` — DOM-event payload extraction, compaction, and the
  "Triggering Event" snapshot block injected into the LLM task.

* ``session`` — ``BrowserSessionManager``: cache, acquire, dispose,
  lifecycle/aliveness checks, scope-key resolution.

* ``hooks``   — ``BrowserUseHookContext`` factory and the three
  lifecycle-hook invokers (early / prompt-build / late).

* ``agent``   — Build + reuse the ``browser_use.Agent``, reset its
  state across pend_event-loop rounds, install step monkey-patches
  (cancellation, tab refocus, abort guard, DOM-focus hide/restore).

* ``runner``  — ``BrowserUseRunner``: the linear async flow that
  replaces ``_run_browser_use``.

* ``auto``    — ``AutoNode``: the synchronous LangGraph node body.
  Exposes ``build_browser_automation_node`` (the public factory).

Backward-compatibility: ``agent.ec_skills.build_node`` keeps a thin
shim that re-exports ``build_browser_automation_node`` from this
package, so existing callers remain unchanged.
"""

# Public entry-point will be re-exported once auto.py is in place.
# Until then, callers should keep importing from agent.ec_skills.build_node.
__all__ = []
