"""Node-runtime helpers for ``build_node`` deterministic fast-paths.

This package holds generic, site-agnostic execution helpers that used
to live inline inside ``agent.ec_skills.build_node``'s node builders
but are large enough to deserve their own module (> ~250 LOC).  Each
helper is designed so that it can be reused across multiple sites via
an explicit plugin-point when the work includes any site-specific
DOM reasoning.

Current contents:

* :mod:`.frontdesk_dispatch` — the PreDispatch fan-out fast-path that
  reads an ``EventMonitor`` snapshot, enriches each candidate with
  optional site-specific ground-truth data, and fans out assignment
  ``send_chat`` calls to worker agents in round-robin order.
"""
