"""What this build expects the site to look like.

The platform journal compares an observation against the last shape seen *on
this machine*. That has a hole: on a fresh install there is no last shape, so
whatever the machine sees first is adopted silently as normal. The first machine
to meet a redesign therefore records it as correct and never flags it — only the
*second* change would ever be caught, which is the wrong one.

Shipping an expected shape closes that. A new install compares what it sees
against what the build was written for and reports a difference on day one.

A difference is not proof of a site change
------------------------------------------
Three things produce one, and the record says which baseline was used so they
can be told apart later:

* the site really did change (what we are looking for);
* the build is old, and the site moved before this install existed;
* this machine is in a gradual-rollout bucket the baseline was not taken from.

Only corroboration across machines settles it, which is why the fleet layer's
first job is counting how many installs saw the same delta
(``docs/SELF_HEALING_ROADMAP.md`` §14).

Regenerating
------------
``ecan drift export-baseline`` writes the current shapes from a machine known to
be healthy, which is how build N+1's baseline gets made.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

from utils.logger_helper import logger_helper as logger

SITE = "feige_chat"
_BASELINE_FILE = Path(__file__).with_name("baseline.json")

_LOCK = threading.Lock()
_REGISTERED = False


def load() -> Dict[str, Any]:
    """The shipped shapes, without the provenance notes."""
    try:
        data = json.loads(_BASELINE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning(f"[baseline] could not read {_BASELINE_FILE.name}: {exc}")
        return {}


def register() -> None:
    """Hand the shipped shapes to the journal. Idempotent and cheap to call."""
    global _REGISTERED
    if _REGISTERED:
        return
    with _LOCK:
        if _REGISTERED:
            return
        _REGISTERED = True
    try:
        shapes = load()
        if not shapes:
            logger.debug("[baseline] nothing shipped; machine-local only")
            return
        from agent.ec_skills.browser_use_extension import drift_journal
        drift_journal.register_shipped_baseline(SITE, shapes)
        logger.debug(f"[baseline] registered {sorted(shapes)} for {SITE}")
    except Exception as exc:
        logger.debug(f"[baseline] could not register: {exc}")
