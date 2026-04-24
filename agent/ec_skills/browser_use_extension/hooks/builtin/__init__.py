"""
Built-in hooks — Tier-0.  These ship with the app and enforce mission-
critical behavior (privacy filtering, crosstalk guards, typing locks, etc.).

Third-party code MAY NOT register Tier-0 hooks or unregister built-ins.
The HookDispatcher enforces this structurally (package-prefix check).

Each built-in lives in its own module so hooks can evolve independently.
This package is empty in PR 2; subsequent PRs (3, 4) populate it with:

    * ``bypass_actions.py``          — HOT-PATH-A generic bypass hook
    * ``verify_active_session.py``   — crosstalk guard (pre-action)
    * ``typing_lock.py``             — Feige active-chat exclusive lock
    * ``send_message.py``            — deterministic reply sender
    * ``ensure_tab_focused.py``      — tab focus enforcer (pre-step)
    * ``privacy_filter.py``          — (future) rehome of PrivacyAgent's
                                       existing redaction path as a hook
"""
from __future__ import annotations

# Intentionally empty — populated by later PRs.
__all__: list[str] = []
