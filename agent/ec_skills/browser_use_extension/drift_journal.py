"""A permanent record of how a site CHANGED, kept for years, never overwritten.

This is not logging, and it is not a page dump. A log answers "what is
happening now" and is rotated away when it grows. A page dump answers "what did
this page contain" -- which nobody wants two years later, and which would
quietly become a multi-year archive of customer messages.

What this stores is the **delta**: the site used to build conversation rows
carrying ``data-qa-id``; it now builds them carrying neither that nor the class
we keyed on, and a ``title`` instead. That is the artifact worth keeping. It is
small, it is free of customer content by construction, and it is the exact
thing someone needs when the next redesign lands and the question is "has this
happened before, and what did we change last time".

How a change is detected
------------------------
:func:`note_shape` is handed the current *structural* shape of something -- the
attribute names a row is built from, the field names a websocket frame carries.
It compares against the last shape seen on this machine and, when they differ,
writes the diff to the journal and adopts the new one.

The comparison has to survive a restart: both site changes we have been bitten
by happened between runs, not during one. So last-known-good shapes live in a
small mutable sidecar (``known_shapes.json``), kept separate from the journal,
which is immutable history and is never rewritten.

The rules that make the journal different from a log
----------------------------------------------------
* **Append-only. A newer occurrence never overwrites an older one.** Files are
  partitioned by year for readability, not for deletion. No size cap, no backup
  count, no rollover that discards.
* **Retention is a floor, not a cap.** ``RETENTION_FLOOR_YEARS`` is three, and
  :func:`prune` refuses anything younger. Nothing prunes automatically.
* **Structured.** One JSON object per line, so years of it can be read by a
  script rather than by eye.
* **Shape, not content.** Structural names travel; free text is replaced by a
  description of its shape. An archive meant to outlive three years of
  customers must not accumulate their data.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from utils.logger_helper import logger_helper as logger

# The promise. prune() will not delete anything younger than this, whatever it
# is asked to do.
RETENTION_FLOOR_YEARS = 3

# One full record per change per day. A site that has genuinely moved will
# re-trigger on every scan; without coalescing, one afternoon writes tens of
# thousands of identical rows and buries the one worth reading.
_COALESCE_WINDOW_S = 24 * 3600

# A single record must not be able to write a hundred megabytes.
_MAX_EVIDENCE_CHARS = 64_000
_MAX_NAMES = 60


@dataclass
class _Incident:
    first_seen: float
    last_written: float
    count: int = 0


_LOCK = threading.Lock()
_INCIDENTS: Dict[tuple, _Incident] = {}
_SEQUENCE = 0

# Last shape this process reported per key. A caller on a hot path (a frame
# decoder, a per-poll scan) reports the same shape over and over; comparing in
# memory first means the disk is touched only when something actually moved.
_LAST_SEEN: Dict[str, Any] = {}
_SEQUENCE_SEEDED = False

# What the BUILD expected each watched thing to look like, registered by the
# bundles. See :func:`register_shipped_baseline`.
_SHIPPED: Dict[str, Dict[str, Any]] = {}


# ── where it lives ─────────────────────────────────────────────────────────

def journal_dir() -> Path:
    """Where the journal lives. Override with ``ECAN_DRIFT_JOURNAL_DIR``."""
    override = (os.getenv("ECAN_DRIFT_JOURNAL_DIR") or "").strip()
    if override:
        base = Path(override)
    else:
        try:
            from config.app_info import app_info
            base = Path(app_info.appdata_path) / "drift_journal"
        except Exception:
            base = Path.home() / ".ecan" / "drift_journal"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _journal_path(when: Optional[datetime] = None) -> Path:
    """One file per year. Partitioning is for readability; nothing is deleted."""
    stamp = when or datetime.now(timezone.utc)
    return journal_dir() / f"drift-{stamp.year}.jsonl"


def _shapes_path() -> Path:
    """Last-known-good shapes. Mutable, unlike the journal beside it."""
    return journal_dir() / "known_shapes.json"


# ── describing a shape ─────────────────────────────────────────────────────

def canonical_shape(shape: Any) -> Any:
    """Reduce an observation to the part that is structure, and sort it.

    Collections of names are sorted so that ordering noise does not read as a
    change. Free text is replaced by a description of its shape, so that a
    caller passing something careless cannot put customer content into a file
    that is kept for years.
    """
    from .element_resolver import describe_shape

    if isinstance(shape, dict):
        return {
            str(k)[:60]: canonical_shape(v)
            for k, v in sorted(shape.items(), key=lambda kv: str(kv[0]))[:_MAX_NAMES]
        }
    if isinstance(shape, (set, frozenset)):
        return sorted(str(v)[:60] for v in shape)[:_MAX_NAMES]
    if isinstance(shape, (list, tuple)):
        return [canonical_shape(v) for v in list(shape)[:_MAX_NAMES]]
    if isinstance(shape, str):
        # Structural tokens -- attribute names, tags, roles -- are short and
        # have no spaces. Anything longer is content, and only its shape goes in.
        if len(shape) <= 48 and not any(ch.isspace() for ch in shape):
            return shape
        return f"<{describe_shape(shape)}>"
    if isinstance(shape, (int, float, bool)) or shape is None:
        return shape
    return f"<{type(shape).__name__}>"


def dom_fingerprint(nodes: Iterable[Any]) -> Dict[str, List[str]]:
    """The structural signature of some DOM nodes -- names only, never values.

    Give it dicts describing nodes (``{"tag", "attributes", "classes",
    "role"}``) and it returns the union of what those nodes are BUILT from.
    Two fingerprints differing means the site changed how it builds that thing,
    which is exactly the event worth recording -- and it contains nothing any
    customer wrote.
    """
    tags, attrs, classes, roles = set(), set(), set(), set()
    for node in list(nodes or [])[:200]:
        if not isinstance(node, dict):
            continue
        if node.get("tag"):
            tags.add(str(node["tag"])[:40].lower())
        if node.get("role"):
            roles.add(str(node["role"])[:40])

        raw_attrs = node.get("attributes")
        if isinstance(raw_attrs, dict):
            attrs.update(str(k)[:60] for k in list(raw_attrs)[:40])
        elif isinstance(raw_attrs, (list, tuple, set)):
            attrs.update(str(k)[:60] for k in list(raw_attrs)[:40])

        raw_classes = node.get("classes")
        if isinstance(raw_classes, str):
            raw_classes = raw_classes.split()
        if isinstance(raw_classes, (list, tuple, set)):
            classes.update(str(c)[:60] for c in list(raw_classes)[:40])

    return {
        "tags": sorted(tags),
        "attributes": sorted(attrs),
        "classes": sorted(classes),
        "roles": sorted(roles),
    }


def diff_shapes(before: Any, after: Any) -> Dict[str, Any]:
    """What changed between two shapes. An empty dict means nothing did.

    Collections of names diff as sets (gained / lost), dicts diff key by key,
    and scalars report the old and the new value.
    """
    before = canonical_shape(before)
    after = canonical_shape(after)
    if before == after:
        return {}

    if isinstance(before, dict) and isinstance(after, dict):
        out: Dict[str, Any] = {}
        for key in sorted(set(before) | set(after)):
            if key not in before:
                out[key] = {"added": after[key]}
            elif key not in after:
                out[key] = {"removed": before[key]}
            else:
                sub = diff_shapes(before[key], after[key])
                if sub:
                    out[key] = sub
        return out

    if isinstance(before, list) and isinstance(after, list):
        gained = [v for v in after if v not in before]
        lost = [v for v in before if v not in after]
        out = {}
        if gained:
            out["gained"] = gained[:_MAX_NAMES]
        if lost:
            out["lost"] = lost[:_MAX_NAMES]
        return out

    return {"was": before, "now": after}


# ── the known-shape store (mutable, and survives restarts) ─────────────────

def _load_known() -> Dict[str, Any]:
    try:
        path = _shapes_path()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.debug(f"[drift-journal] could not read known shapes: {exc}")
    return {}


def _save_known(data: Dict[str, Any]) -> None:
    path = _shapes_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                   encoding="utf-8")
    os.replace(tmp, path)


def note_shape(
    site: str,
    key: str,
    shape: Any,
    *,
    kind: str = "shape_change",
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Report what something is built from now; record it if it moved.

    This is the main entry point. Call it with the structure the site is
    presenting right now -- the attribute names on a row, the field names in a
    websocket payload, the output of :func:`dom_fingerprint`. Returns the diff
    when the shape changed (having journalled it), or ``None`` when it did not.

    The first sighting is not a change. It is adopted silently as the baseline,
    because a machine seeing a site for the first time has learned nothing about
    whether that site changed.

    Args:
        site: which bundle observed it. Free-form; never interpreted here.
        key: what was observed ("sidebar_row", "chat_ws_payload").
        shape: the structural observation -- names and counts, not content.
        kind: the ``kind`` recorded in the journal.
        context: anything else worth keeping about the moment. Summarised.
    """
    try:
        store_key = f"{site}::{key}"
        current = canonical_shape(shape)
        now_iso = datetime.now(timezone.utc).isoformat()

        # Fast path: the overwhelming majority of calls report a shape this
        # process has already reported. Callers sit on hot paths, so those must
        # not cost a file read and write.
        with _LOCK:
            if _LAST_SEEN.get(store_key) == current:
                return None
            _LAST_SEEN[store_key] = current

        with _LOCK:
            known = _load_known()
            entry = known.get(store_key)
            previous = entry.get("shape") if isinstance(entry, dict) else None
            held_since = (entry.get("first_seen") if isinstance(entry, dict)
                          else None) or now_iso

            compared_against = "local"
            if previous is None:
                # No local history. Fall back to what the build shipped, so a
                # fresh install detects a change instead of adopting it.
                shipped = canonical_shape(shipped_baseline(site, key)) \
                    if shipped_baseline(site, key) is not None else None
                if shipped is None:
                    known[store_key] = {"shape": current, "first_seen": now_iso,
                                        "last_seen": now_iso}
                    _save_known(known)
                    return None                 # nothing to compare against
                previous = shipped
                compared_against = "shipped"
                held_since = "(shipped with this build)"

            delta = diff_shapes(previous, current)
            if not delta:
                entry["last_seen"] = now_iso
                known[store_key] = entry
                _save_known(known)
                return None

            known[store_key] = {
                "shape": current,
                "first_seen": now_iso,
                "last_seen": now_iso,
                "previous_shape": previous,
                "previous_held_since": held_since,
            }
            _save_known(known)

        evidence = {
            "changed": delta,
            "was": previous,
            "now": current,
            "previous_shape_held_since": held_since,
            # Which baseline this was measured against. "shipped" means this
            # machine had no history and the build's expectation was used, so
            # the difference may be an old build or a rollout bucket rather
            # than a change -- see register_shipped_baseline.
            "compared_against": compared_against,
        }
        if context:
            evidence["context"] = canonical_shape(context)

        record_event(
            site, kind, element=key,
            summary=_summarize_delta(key, delta),
            evidence=evidence,
            raw_ok=True,          # already canonical: names and counts only
        )
        return delta

    except Exception as exc:
        logger.debug(f"[drift-journal] note_shape failed for {site}/{key}: {exc}")
        return None


def _summarize_delta(key: str, delta: Dict[str, Any]) -> str:
    """The one line a human reads first.

    'sidebar_row lost attributes: data-qa-id; gained attributes: title'
    """
    bits: List[str] = []

    def walk(node: Any, prefix: str = "") -> None:
        if not isinstance(node, dict):
            return
        for name, value in list(node.items())[:8]:
            if name == "lost" and value:
                bits.append(f"lost {prefix}{', '.join(map(str, value[:4]))}")
            elif name == "gained" and value:
                bits.append(f"gained {prefix}{', '.join(map(str, value[:4]))}")
            elif name in ("was", "now", "added", "removed"):
                continue
            elif isinstance(value, dict):
                walk(value, f"{name}: ")

    walk(delta)
    return f"{key} " + ("; ".join(bits[:6]) if bits else "changed shape")


def register_shipped_baseline(site: str, shapes: Dict[str, Any]) -> None:
    """Declare what this BUILD expected the site to look like.

    Without this, the first sighting on a machine is adopted silently as the
    baseline -- so the first machine to meet a redesign records it as normal and
    never flags it. Only the *second* change would ever be caught, which is the
    wrong one.

    With a shipped baseline, a fresh install compares what it sees against what
    the build expected and reports a difference on day 1.

    A difference is not automatically a site change: the build may simply be old,
    or this machine may be in a gradual-rollout bucket. The record says which
    baseline it was compared against and which build observed it, so the two can
    be told apart later -- and corroboration across machines is what settles it.
    """
    try:
        _SHIPPED[str(site)] = dict(shapes or {})
    except Exception as exc:
        logger.debug(f"[drift-journal] could not register baseline: {exc}")


def shipped_baseline(site: str, key: str = "") -> Optional[Any]:
    """What the build expected, for one key or the whole site."""
    site_shapes = _SHIPPED.get(str(site))
    if site_shapes is None:
        return None
    return site_shapes.get(str(key)) if key else dict(site_shapes)


def last_shape(site: str, key: str) -> Optional[Any]:
    """The shape currently held as the baseline, or None if there is none.

    For callers that accumulate across runs: something only observable
    occasionally (a field that appears on one frame type in a thousand) would
    look like a loss on every restart if the caller started from empty. Seeding
    from the stored baseline is how it avoids reporting that.
    """
    try:
        with _LOCK:
            entry = _load_known().get(f"{site}::{key}")
        return entry.get("shape") if isinstance(entry, dict) else None
    except Exception:
        return None


def forget_shape(site: str = "", key: str = "") -> int:
    """Drop remembered shapes so the next sighting re-baselines.

    Only touches the mutable store; the journal's history is untouched. Use it
    after a deliberate parser rewrite, when the old shape is no longer the
    thing new observations should be compared against.
    """
    removed = 0
    try:
        with _LOCK:
            known = _load_known()
            if not site and not key:
                removed = len(known)
                known = {}
            else:
                prefix = f"{site}::{key}" if key else f"{site}::"
                for store_key in [k for k in known if k.startswith(prefix)]:
                    del known[store_key]
                    removed += 1
            _save_known(known)
            for store_key in [k for k in _LAST_SEEN
                              if not site or k.startswith(f"{site}::{key}"
                                                          if key else f"{site}::")]:
                _LAST_SEEN.pop(store_key, None)
    except Exception as exc:
        logger.warning(f"[drift-journal] forget_shape failed: {exc}")
    return removed


# ── writing ────────────────────────────────────────────────────────────────

def _seed_sequence() -> None:
    """Continue numbering from what is already on disk.

    Record numbers are how a person refers to an entry ("look at #104"), so
    they have to mean one thing on a machine, not one thing per process. This
    runs once per process and costs one read of the current year's file.
    """
    global _SEQUENCE, _SEQUENCE_SEEDED
    if _SEQUENCE_SEEDED:
        return
    _SEQUENCE_SEEDED = True
    try:
        highest = 0
        for path in journal_dir().glob("drift-*.jsonl"):
            for line in path.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    seq = int(json.loads(line).get("seq") or 0)
                except (ValueError, TypeError, AttributeError):
                    continue
                highest = max(highest, seq)
        _SEQUENCE = max(_SEQUENCE, highest)
    except Exception as exc:
        logger.debug(f"[drift-journal] could not seed sequence: {exc}")


def _build_info() -> Dict[str, str]:
    """Which build observed this. Essential eighteen months later."""
    info: Dict[str, str] = {}
    try:
        from config.app_info import app_info
        info["version"] = str(getattr(app_info, "app_version", "") or "")
    except Exception:
        pass
    try:
        import platform
        info["platform"] = platform.system()
        info["machine"] = platform.node()[:64]
    except Exception:
        pass
    return info


def record_event(
    site: str,
    kind: str,
    *,
    element: str = "",
    summary: str = "",
    evidence: Optional[Dict[str, Any]] = None,
    raw_ok: bool = False,
) -> bool:
    """Append one observation. Returns True if it was written.

    Most callers want :func:`note_shape` instead -- it works out what changed.
    Use this directly for a change that is already known to be one, such as a
    parser that was resolving everything and has stopped.

    Args:
        site: which bundle observed it. Free-form; never interpreted here.
        kind: what kind of change -- ``shape_change``, ``strategy_collapse``,
            ``ws_schema_change``... Sites name their own.
        element: the thing that moved.
        summary: one line a human will read first.
        evidence: the delta, and whatever supports it.
        raw_ok: store ``evidence`` as given instead of summarising it. Only for
            data already known to be structural: names and counts.

    Coalesced: the first occurrence of a change is written in full, and repeats
    within the day update a count rather than appending again.
    """
    global _SEQUENCE
    try:
        key = (str(site), str(kind), str(element))
        now = time.time()

        _seed_sequence()
        with _LOCK:
            incident = _INCIDENTS.get(key)
            if incident and (now - incident.last_written) < _COALESCE_WINDOW_S:
                incident.count += 1
                return False                    # already on the record today
            first = incident.first_seen if incident else now
            _INCIDENTS[key] = _Incident(
                first_seen=first, last_written=now,
                count=(incident.count + 1) if incident else 1)
            _SEQUENCE += 1
            sequence = _SEQUENCE
            repeats = _INCIDENTS[key].count

        payload = (evidence or {}) if raw_ok else canonical_shape(evidence or {})
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        if len(blob) > _MAX_EVIDENCE_CHARS:
            payload = {"truncated": True,
                       "evidence_prefix": blob[:_MAX_EVIDENCE_CHARS]}

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": sequence,
            "site": str(site),
            "kind": str(kind),
            "element": str(element),
            "summary": str(summary)[:500],
            "repeats_in_window": repeats,
            "build": _build_info(),
            "evidence": payload,
        }

        path = _journal_path()
        with _LOCK:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                fh.flush()
                # These get written when something is going wrong, which is
                # exactly when the process may not exit cleanly.
                try:
                    os.fsync(fh.fileno())
                except OSError:
                    pass

        logger.warning(
            f"[drift-journal] SITE CHANGE RECORDED {site}"
            f"{'/' + element if element else ''} ({kind}): {summary} -> {path.name}"
        )
        return True

    except Exception as exc:
        # Recording evidence must never be the thing that breaks a run.
        logger.debug(f"[drift-journal] could not record: {exc}")
        return False


# ── reading ────────────────────────────────────────────────────────────────

def read_events(
    *,
    site: str = "",
    kind: str = "",
    since_year: Optional[int] = None,
    limit: int = 500,
) -> List[dict]:
    """Read back the journal, newest year first. For analysis, not the hot path."""
    out: List[dict] = []
    try:
        for path in sorted(journal_dir().glob("drift-*.jsonl"), reverse=True):
            if since_year is not None:
                try:
                    if int(path.stem.split("-")[1]) < since_year:
                        continue
                except (IndexError, ValueError):
                    pass
            for line in path.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue          # one bad line must not lose the file
                if site and event.get("site") != site:
                    continue
                if kind and event.get("kind") != kind:
                    continue
                out.append(event)
                if len(out) >= limit:
                    return out
    except Exception as exc:
        logger.warning(f"[drift-journal] could not read: {exc}")
    return out


def journal_stats() -> Dict[str, Any]:
    """How much history exists, and from when. Cheap enough for a status page."""
    stats: Dict[str, Any] = {"files": [], "events": 0, "bytes": 0}
    try:
        for path in sorted(journal_dir().glob("drift-*.jsonl")):
            lines = sum(1 for line in path.open(encoding="utf-8",
                                                errors="replace") if line.strip())
            size = path.stat().st_size
            stats["files"].append({"name": path.name, "events": lines,
                                   "bytes": size})
            stats["events"] += lines
            stats["bytes"] += size
    except Exception:
        pass
    return stats


def prune(older_than_years: int = RETENTION_FLOOR_YEARS) -> List[str]:
    """Delete whole year-files older than *older_than_years*. Never automatic.

    Nothing calls this. It exists so that deleting history is a deliberate act
    with a floor under it: anything younger than :data:`RETENTION_FLOOR_YEARS`
    is refused, whatever is asked for. The point of the journal is that the
    record of the PREVIOUS site change is still there when the next one
    arrives, and they are years apart.
    """
    years = max(int(older_than_years), RETENTION_FLOOR_YEARS)
    cutoff = datetime.now(timezone.utc).year - years
    removed: List[str] = []
    try:
        for path in sorted(journal_dir().glob("drift-*.jsonl")):
            try:
                year = int(path.stem.split("-")[1])
            except (IndexError, ValueError):
                continue
            if year <= cutoff:
                path.unlink()
                removed.append(path.name)
                logger.warning(f"[drift-journal] pruned {path.name} (year {year})")
    except Exception as exc:
        logger.warning(f"[drift-journal] prune failed: {exc}")
    return removed


def reset_incident_window() -> None:
    """Drop this process's in-memory state: the day-coalescing window and the
    cache of shapes already reported. The on-disk baseline and the journal are
    untouched. Tests, and after a deliberate re-baseline."""
    global _SEQUENCE_SEEDED
    with _LOCK:
        _INCIDENTS.clear()
        _LAST_SEEN.clear()
        _SEQUENCE_SEEDED = False
