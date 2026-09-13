"""Placement declarations — one reader, one vocabulary.

``residency`` / ``lifetime`` / ``requires[]`` exist on ``EC_Skill`` and
``ManagedTask`` (Path 1.5 Phase 0.3) and, until now, nothing read them. Under
unified execution the scheduler does: ``requires[]`` is matched against a pod's
``capabilities[]`` as a WHERE clause, and ``lifetime`` decides whether work can
go to a cold pod at all.

Everything that reads or writes a placement goes through here, for one reason:
these values are persisted **inside the skill's ``config`` JSON**, because
GraphQL ``SkillUpdateInput`` has no columns for them (the same reason
``run_in_cloud`` lives there). That means every load path has to look in two
places and agree on the precedence, and the last time a field like this was
added it silently no-op'd in three separate metadata whitelists. One reader is
the fix.

The capability vocabulary lives here too, and its TypeScript twin is
``gui_v2/src/types/domain/placement.ts``. A skill can only usefully require what
some pod can advertise, so the two lists have to say the same words — a
requirement nothing can satisfy is a turn that queues forever.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from utils.logger_helper import logger_helper as logger

RESIDENCY_VALUES = ("local", "cloud", "any")
LIFETIME_VALUES = ("turn", "conversation", "long_running")

DEFAULT_RESIDENCY = "any"
DEFAULT_LIFETIME = "conversation"

# Capabilities a pod can advertise and a skill can require. Keep in step with
# gui_v2/src/types/domain/placement.ts.
CAPABILITIES = (
    "browser_local",     # a real browser on the machine (RPA, browser-use)
    "gpu",               # GPU-backed inference
    "cn_llm",            # CN-region LLM routing
    "intl_llm",          # international LLM routing
    "long_running",      # will host work that never checkpoints
    "file_storage",      # durable local scratch space
)

# Isolation is expressed as a capability, never as a binding: a pod that carries
# dedicated:<agent-id> is the only one that can claim work requiring it, but the
# relationship is still scheduling, so nothing strands when that pod dies —
# the work waits rather than disappearing.
DEDICATED_PREFIX = "dedicated:"

MAX_REQUIRES = 20


def dedicated_capability(agent_id: Any) -> str:
    """The capability that expresses "only this agent's work"."""
    agent = str(agent_id or "").strip()
    if not agent:
        raise ValueError("dedicated capability needs an agent id")
    return f"{DEDICATED_PREFIX}{agent}"


def is_dedicated_capability(value: Any) -> bool:
    return str(value or "").startswith(DEDICATED_PREFIX)


def normalize_residency(value: Any, default: str = DEFAULT_RESIDENCY) -> str:
    text = str(value or "").strip().lower()
    if text in RESIDENCY_VALUES:
        return text
    if text:
        logger.warning(f"[placement] unknown residency {value!r}; using {default!r}")
    return default


def normalize_lifetime(value: Any, default: str = DEFAULT_LIFETIME) -> str:
    text = str(value or "").strip().lower()
    if text in LIFETIME_VALUES:
        return text
    if text:
        logger.warning(f"[placement] unknown lifetime {value!r}; using {default!r}")
    return default


def normalize_requires(value: Any) -> List[str]:
    """A clean capability list: strings, de-duplicated, order kept, bounded.

    Unknown names are NOT dropped — ``dedicated:<agent-id>`` is a legitimate
    requirement that no static list can contain, and a pod may advertise a
    capability this build has never heard of. Dropping them here would silently
    widen placement, which is the dangerous direction.
    """
    if isinstance(value, str):
        items: Iterable[Any] = [v for v in value.replace(";", ",").split(",")]
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        return []

    seen: set = set()
    out: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= MAX_REQUIRES:
            break
    return out


def read_placement(*sources: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Placement from the first source that names each field.

    Sources are consulted in order, which is how the existing cloud flags
    behave: a file's top-level keys win over the ``config`` dict they were also
    written into, so an edit on disk is not shadowed by a stale DB copy.
    """
    residency: Any = None
    lifetime: Any = None
    requires: Any = None

    for source in sources:
        if not isinstance(source, dict):
            continue
        if residency is None and source.get("residency") is not None:
            residency = source.get("residency")
        if lifetime is None and source.get("lifetime") is not None:
            lifetime = source.get("lifetime")
        if requires is None and source.get("requires") is not None:
            requires = source.get("requires")

    return {
        "residency": normalize_residency(residency),
        "lifetime": normalize_lifetime(lifetime),
        "requires": normalize_requires(requires),
    }


def apply_placement(target: Any, *sources: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Read a placement onto ``target`` (an EC_Skill / ManagedTask). Returns it."""
    placement = read_placement(*sources)
    try:
        target.residency = placement["residency"]
        target.lifetime = placement["lifetime"]
        target.requires = list(placement["requires"])
    except Exception as exc:                       # a frozen or odd model
        logger.warning(f"[placement] could not apply placement to {type(target).__name__}: {exc}")
    return placement


def placement_of(obj: Any) -> Dict[str, Any]:
    """The placement an object currently declares, defaults filled in."""
    return {
        "residency": normalize_residency(getattr(obj, "residency", None)),
        "lifetime": normalize_lifetime(getattr(obj, "lifetime", None)),
        "requires": normalize_requires(getattr(obj, "requires", None)),
    }


def is_default_placement(placement: Dict[str, Any]) -> bool:
    """True when a placement says nothing a scheduler could act on."""
    return (
        placement.get("residency") == DEFAULT_RESIDENCY
        and placement.get("lifetime") == DEFAULT_LIFETIME
        and not placement.get("requires")
    )
