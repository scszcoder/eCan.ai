"""L3: remember what the resolver worked out, so the next run does not pay for it.

Platform-side and business-free. Sites say "this descriptor resolved this
element here"; this module scores it, serves the best one back, and retires the
ones that stop working.

What gets learned, and what deliberately does not
-------------------------------------------------
**Learned: a semantic descriptor.** "The customer name is the short titled
string that is not a number and not a duration." That survives a redesign,
because it describes what a human sees.

**Not learned: a selector.** It would be easy to have L2 hand back
``div.x > span:nth-child(2)`` and cache it — and we would be rebuilding exactly
the thing that has broken four times this year, only now generated
automatically and at scale. A learned selector is a *faster* way to acquire
technical debt. See ``docs/SELF_HEALING_ROADMAP.md`` §1.

Why scores rather than a cache
------------------------------
A descriptor that worked once may have worked by luck, and a page that changes
again should not be stuck with yesterday's answer. Following ``workflow-use``'s
``healing/`` module: score on use, promote what keeps working, retire what
stops. Confidence has to be *earned repeatedly*, not granted once.

Storage
-------
One JSON file under appdata, written atomically. Local-only and never synced —
it describes one machine's experience of a site, and (like browser profiles)
there is no reason for it to travel. See
``tests/unit/test_browser_profile_stays_local.py`` for the same rule applied to
profiles.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from utils.logger_helper import logger_helper as logger

from .element_targeting import TargetDescriptor

# A descriptor has to earn this before it is served ahead of a site's own
# built-in strategies. One lucky hit is not evidence.
PROMOTE_AFTER_HITS = 3

# ...and is dropped once it has failed this many times in a row. Kept low: a
# stale descriptor costs a wasted attempt on every single resolution.
RETIRE_AFTER_MISSES = 3

# Never keep more than this per (site, element). Pages change; the tail is junk.
MAX_PER_ELEMENT = 8

# How many retirements to remember. A retired descriptor is dropped from the
# serving bucket immediately -- keeping it would cost a wasted attempt on every
# resolution -- but its LIFETIME is the only evidence we get about which kinds
# of descriptor actually last, so that outlives the descriptor itself.
MAX_LIFETIMES = 200


@dataclass
class LearnedTarget:
    """One descriptor and how well it has held up."""

    target_text: str = ""
    container_hint: str = ""
    position_hint: str = ""
    role: str = ""
    source: str = ""            # how it was learned: "resolver", "manual"
    hits: int = 0
    misses: int = 0
    consecutive_misses: int = 0
    first_learned: float = field(default_factory=time.time)
    last_used: float = 0.0
    promoted_at: float = 0.0    # when it first earned trust; 0 = never did

    def kind(self) -> str:
        """Which semantic fields carry this descriptor: 'text+container'...

        The unit that lifetimes are aggregated over. Individual descriptors are
        specific to one page and die with it; the KIND is what transfers -- if
        text-anchored descriptors outlive container-anchored ones on this site,
        that is worth knowing the next time there is a choice.
        """
        parts = []
        if self.target_text:
            parts.append("text")
        if self.container_hint:
            parts.append("container")
        if self.position_hint:
            parts.append("position")
        return "+".join(parts) or "none"

    def descriptor(self) -> TargetDescriptor:
        return TargetDescriptor(
            target_text=self.target_text,
            container_hint=self.container_hint,
            position_hint=self.position_hint,
            role=self.role,
        )

    def key(self) -> tuple:
        return (self.target_text, self.container_hint, self.position_hint, self.role)

    @property
    def trusted(self) -> bool:
        return self.hits >= PROMOTE_AFTER_HITS and self.consecutive_misses == 0

    @property
    def retired(self) -> bool:
        return self.consecutive_misses >= RETIRE_AFTER_MISSES

    def score(self) -> float:
        """Hit rate, mildly damped so a 1/1 does not outrank a 40/42."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / (total + 2.0)


class _Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, List[LearnedTarget]]] = {}
        self._lifetimes: List[dict] = []
        self._loaded = False
        self._dirty = False

    # ── persistence ────────────────────────────────────────────────────────

    def _path(self) -> Path:
        try:
            from config.app_info import app_info
            base = Path(app_info.appdata_path)
        except Exception:
            base = Path.home() / ".ecan"
        base.mkdir(parents=True, exist_ok=True)
        return base / "learned_targets.json"

    def load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = self._path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Kept beside the descriptors but not one of them; a file written
            # before this existed simply has none.
            self._lifetimes = list((raw or {}).pop("_lifetimes", None) or [])
            for site, elements in (raw or {}).items():
                for element, entries in (elements or {}).items():
                    bucket = self._data.setdefault(site, {}).setdefault(element, [])
                    for entry in entries or []:
                        try:
                            bucket.append(LearnedTarget(**entry))
                        except TypeError:
                            continue      # shape drifted; drop that row only
            logger.info(
                f"[learned-targets] loaded {sum(len(e) for s in self._data.values() for e in s.values())} "
                f"descriptor(s) from {path.name}"
            )
        except Exception as exc:
            # A corrupt store must never stop a run. Start empty and move on.
            logger.warning(f"[learned-targets] could not read {path}: {exc}")

    def save(self) -> None:
        if not self._dirty:
            return
        path = self._path()
        try:
            payload = {
                site: {
                    element: [asdict(t) for t in targets]
                    for element, targets in elements.items()
                }
                for site, elements in self._data.items()
            }
            if self._lifetimes:
                payload["_lifetimes"] = self._lifetimes[-MAX_LIFETIMES:]
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(path)             # atomic on the same volume
            self._dirty = False
        except Exception as exc:
            logger.warning(f"[learned-targets] could not write {path}: {exc}")


_STORE = _Store()


# ── the API sites use ──────────────────────────────────────────────────────

def best_for(site: str, element: str) -> Optional[TargetDescriptor]:
    """The descriptor most likely to work, or None if nothing has earned it.

    Only returns something that has been promoted. An unproven descriptor is
    worse than nothing: it costs an attempt on every resolution and teaches us
    little, because a miss could just mean it was never right.
    """
    with _STORE._lock:
        _STORE.load()
        candidates = [
            t for t in _STORE._data.get(site, {}).get(element, [])
            if t.trusted and not t.retired
        ]
        if not candidates:
            return None
        # Score dominates; kind survival only separates descriptors that have
        # earned the same record. Letting it outrank the score would mean
        # preferring a kind that once lasted a long time over one that is
        # working right now.
        lifetimes = {}
        try:
            from statistics import median
            for row in _STORE._lifetimes:
                lifetimes.setdefault(str(row.get("kind") or "?"), []).append(
                    row.get("survived_s", 0))
            lifetimes = {k: {"median_survived_s": float(median(v))}
                         for k, v in lifetimes.items()}
        except Exception:
            lifetimes = {}
        best = max(candidates,
                   key=lambda t: (t.score(), _kind_rank(t.kind(), lifetimes),
                                  t.hits))
        best.last_used = time.time()
        _STORE._dirty = True
        return best.descriptor()


def record_success(site: str, element: str, descriptor: TargetDescriptor,
                   *, source: str = "resolver") -> None:
    """This descriptor just resolved the element. Credit it."""
    if not descriptor or not descriptor.is_semantic():
        # Refuse to learn something that is not semantic — that is how a
        # selector would sneak into the store.
        return
    fragile, why = descriptor.is_fragile()
    if fragile:
        # Fragile by construction, however well it has worked so far. Learning
        # it would produce the quiet heal/break/heal cycle: every round looks
        # like a success locally, so nothing ever flags it, and the descriptor
        # is wrong again the moment the page grows.
        logger.info(
            f"[learned-targets] {site}/{element}: refusing to learn "
            f"{descriptor.describe()!r} — {why}"
        )
        return
    _update(site, element, descriptor, hit=True, source=source)
    _tell_guard(site, element, resolved=True, source=source)


def record_failure(site: str, element: str, descriptor: TargetDescriptor) -> None:
    """This descriptor was tried and did not resolve. Count it against."""
    if not descriptor:
        return
    _update(site, element, descriptor, hit=False)
    _tell_guard(site, element, resolved=False, source="")


def _tell_guard(site: str, element: str, *, resolved: bool, source: str) -> None:
    """Report to the spend guard whether a resolution actually stuck.

    This is the only place that knows the answer, and the guard's breaker is
    useless without it: without an outcome it would keep paying for the same
    failed resolution every poll. Only outcomes that came from the resolver are
    charged — a descriptor that was already learned costs nothing, so its
    success or failure says nothing about L2's spend.
    """
    if resolved and source and source != "resolver":
        return
    try:
        from . import resolver_guard
        resolver_guard.record_outcome(site, element, resolved)
    except Exception:
        pass


def _update(site: str, element: str, descriptor: TargetDescriptor,
            *, hit: bool, source: str = "") -> None:
    try:
        key = (descriptor.target_text, descriptor.container_hint,
               descriptor.position_hint, descriptor.role)
        with _STORE._lock:
            _STORE.load()
            site_s, element_s = str(site), str(element)
            # Look WITHOUT creating: a failure for something never learned must
            # leave no trace, or a site that keeps failing slowly fills the
            # store with empty buckets.
            existing = _STORE._data.get(site_s, {}).get(element_s, [])
            found = next((t for t in existing if t.key() == key), None)
            if found is None and not hit:
                return
            bucket = _STORE._data.setdefault(site_s, {}).setdefault(element_s, [])
            if found is None:
                found = LearnedTarget(
                    target_text=descriptor.target_text,
                    container_hint=descriptor.container_hint,
                    position_hint=descriptor.position_hint,
                    role=descriptor.role,
                    source=source,
                )
                bucket.append(found)
                logger.info(
                    f"[learned-targets] {site}/{element}: learned "
                    f"{descriptor.describe()!r} (from {source})"
                )

            if hit:
                found.hits += 1
                found.consecutive_misses = 0
                if found.hits == PROMOTE_AFTER_HITS:
                    found.promoted_at = time.time()
                    logger.info(
                        f"[learned-targets] {site}/{element}: promoted "
                        f"{descriptor.describe()!r} after {found.hits} hits"
                    )
            else:
                found.misses += 1
                found.consecutive_misses += 1
                if found.retired:
                    logger.info(
                        f"[learned-targets] {site}/{element}: retiring "
                        f"{descriptor.describe()!r} after "
                        f"{found.consecutive_misses} consecutive misses"
                    )

            # A retired descriptor leaves the serving bucket at once -- keeping
            # it would cost a wasted attempt on every resolution -- but how long
            # it lasted is the only evidence we ever get about which KINDS hold
            # up, so that is banked before it goes.
            for dead in [t for t in bucket if t.retired]:
                _bank_lifetime(site, element, dead)
            bucket[:] = [t for t in bucket if not t.retired]
            if len(bucket) > MAX_PER_ELEMENT:
                bucket.sort(key=lambda t: (t.score(), t.hits), reverse=True)
                del bucket[MAX_PER_ELEMENT:]

            _STORE._dirty = True
    except Exception as exc:
        logger.debug(f"[learned-targets] update failed: {exc}")


def _bank_lifetime(site: str, element: str, dead: "LearnedTarget") -> None:
    """Record how long a descriptor lasted, keyed by its kind.

    A descriptor that never earned promotion is recorded too: a kind that keeps
    failing to earn trust is as informative as one that earns it and then dies.
    """
    try:
        now = time.time()
        _STORE._lifetimes.append({
            "kind": dead.kind(),
            "site": str(site),
            "element": str(element),
            "promoted": bool(dead.promoted_at),
            "survived_s": int(now - dead.promoted_at) if dead.promoted_at else 0,
            "hits": dead.hits,
            "misses": dead.misses,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        })
        del _STORE._lifetimes[:-MAX_LIFETIMES]
        logger.info(
            f"[learned-targets] {site}/{element}: {dead.kind()} descriptor "
            f"lasted {int(now - dead.promoted_at) if dead.promoted_at else 0}s "
            f"after promotion ({dead.hits} hits, {dead.misses} misses)"
        )
    except Exception as exc:
        logger.debug(f"[learned-targets] could not bank lifetime: {exc}")


def kind_lifetimes() -> Dict[str, Dict[str, float]]:
    """How long each KIND of descriptor has survived on this machine.

    ``{kind: {"retired": n, "never_promoted": n, "median_survived_s": x}}``.

    The unit is the kind, not the descriptor: individual descriptors are
    specific to one page and die with it, while the kind is what transfers to
    the next choice. One machine's sample is small -- this is the local half of
    what the fleet layer would answer properly (§14).
    """
    from statistics import median
    buckets: Dict[str, List[dict]] = {}
    with _STORE._lock:
        _STORE.load()
        for row in _STORE._lifetimes:
            buckets.setdefault(str(row.get("kind") or "?"), []).append(row)

    out: Dict[str, Dict[str, float]] = {}
    for kind, rows in buckets.items():
        promoted = [r for r in rows if r.get("promoted")]
        out[kind] = {
            "retired": len(rows),
            "never_promoted": len(rows) - len(promoted),
            "median_survived_s": float(
                median([r.get("survived_s", 0) for r in promoted])
            ) if promoted else 0.0,
        }
    return out


def _kind_rank(kind: str, lifetimes: Dict[str, Dict[str, float]]) -> float:
    """How well this kind has held up here. Unknown kinds rank neutral.

    Neutral rather than worst: a kind with no history has not failed, it has
    simply not been tried, and burying it would stop us ever learning about it.
    """
    row = lifetimes.get(kind)
    if not row:
        return 0.0
    return float(row.get("median_survived_s", 0.0))


def flush() -> None:
    """Persist. Call at run end — writing per hit would be pointless churn."""
    with _STORE._lock:
        _STORE.save()


def report() -> Dict[str, Dict[str, List[dict]]]:
    """Everything known, as plain dicts, for logs and inspection."""
    with _STORE._lock:
        _STORE.load()
        return {
            site: {
                element: [
                    {
                        "descriptor": t.descriptor().describe(),
                        "hits": t.hits,
                        "misses": t.misses,
                        "trusted": t.trusted,
                        "score": round(t.score(), 3),
                        "kind": t.kind(),
                        "promoted_at": t.promoted_at,
                    }
                    for t in targets
                ]
                for element, targets in elements.items()
            }
            for site, elements in _STORE._data.items()
        }


def log_kind_report(reason: str = "") -> None:
    """Which kinds of descriptor last, on this machine. Quiet when nothing has
    retired yet, which is the normal state early on."""
    data = kind_lifetimes()
    if not data:
        return
    logger.info(f"[learned-targets] kind lifetimes"
                f"{f' ({reason})' if reason else ''}:")
    for kind, row in sorted(data.items(),
                            key=lambda kv: -kv[1]["median_survived_s"]):
        logger.info(
            f"[learned-targets]   {kind}: {int(row['median_survived_s'])}s "
            f"median after promotion, {row['retired']} retired "
            f"({row['never_promoted']} never earned trust)")


def log_report(reason: str = "") -> None:
    data = report()
    if not data:
        return
    logger.info(f"[learned-targets] report{f' ({reason})' if reason else ''}:")
    for site, elements in sorted(data.items()):
        for element, targets in sorted(elements.items()):
            for t in targets:
                logger.info(
                    f"[learned-targets]   {site}/{element}: {t['descriptor']!r} "
                    f"hits={t['hits']} misses={t['misses']} "
                    f"trusted={t['trusted']} score={t['score']}"
                )


def reset(*, delete_file: bool = False) -> None:
    """Drop everything in memory. Tests, and a clean slate after a redesign."""
    with _STORE._lock:
        _STORE._data.clear()
        _STORE._lifetimes.clear()
        _STORE._loaded = True     # do not re-read the file behind the caller
        _STORE._dirty = False
        if delete_file:
            try:
                _STORE._path().unlink()
            except Exception:
                pass
