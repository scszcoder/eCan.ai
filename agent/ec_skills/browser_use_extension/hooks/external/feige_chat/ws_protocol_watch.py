"""Watches the WS message protocol for the other kind of site change.

A site does not only move in the DOM. Feige's frames decode to a kv map, and
`ws_reader.extract_messages` reads named keys out of it -- ``nickname``,
``talk_id``, ``sender_role``, ``security_sender_id``. If the backend renames
one or stops populating it, nothing throws: the field comes back empty, a
customer becomes nameless, and the failure surfaces three layers downstream as
a routing bug. ws192 and ws193 both presented that way.

So, the same treatment as the sidebar fingerprint: watch what the frames are
BUILT from, and when that moves, put the diff on the permanent record rather
than in a run log that is gone by the time anyone asks.

Core versus optional, and why the distinction is load-bearing
-------------------------------------------------------------
Not every key appears in every message. ``goods_id`` rides only product cards;
``switch_human_triggered_word`` only a 转人工 handover. If those were judged
per window, a quiet afternoon would look exactly like the backend dropping
them, and the journal would fill with a false alarm a day -- which is worse
than no alarm, because it trains everyone to ignore the file.

So the two are watched differently, and the difference is a real limit rather
than a trick:

* **Core keys** should appear at least once in any window of this size. One of
  them going quiet is evidence, and is reported as a loss.
* **Optional keys** are tracked as an ever-seen union, seeded from the stored
  baseline so a restart does not read as a loss. A NEW one appearing is
  reported -- that is how a rename shows up -- but an optional key falling
  silent is *not* detectable from traffic alone, and this module does not
  pretend otherwise.

Two things make this safe to call from the frame decoder, which is as hot a
path as this codebase has: observation is a set update over a dozen short
strings with no I/O, and the journal's own fast path drops an unchanged report
without touching disk.

Nothing here reads a VALUE. Key names are protocol; values are what customers
wrote, and the journal is kept for years.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional, Set

_SITE_LABEL = "feige_chat"

# Keys that should show up at least once in any window of customer traffic.
# One of these going quiet is the ws193 failure, and is worth an alarm.
CORE_KEYS = frozenset({
    "type",
    "sender_role",
    "nickname",
    "talk_id",
    "pigeon_cid",
    "security_sender_id",
})

# Read by the decoder, but legitimately absent from most windows: fallbacks
# that only fire when the primary is missing, and fields that ride one message
# type. Gains are reported; silence is not evidence. See the module docstring.
OPTIONAL_KEYS = frozenset({
    "uname",
    "security_pigeon_uid",
    "s:client_message_id",
    "client_message_id",
    "generic_search_keywords",
    "goods_id",
    "switch_human_triggered_word",
})

EXPECTED_KEYS = CORE_KEYS | OPTIONAL_KEYS

# Report once the window has seen this many messages. Small enough to catch a
# change within the first minutes of a run; large enough that a single odd
# system frame cannot make a core key look dead.
_WINDOW_FRAMES = 200

# A chatty protocol can carry many unfamiliar keys. Cap what travels.
_MAX_UNEXPECTED = 40

_LOCK = threading.Lock()
_core_seen: Set[str] = set()
_optional_seen: Set[str] = set()
_unexpected: Set[str] = set()
_frames = 0
_seeded = False


def observe(kv: Any) -> None:
    """Note which named fields a decoded message actually carried.

    Called per message from the frame decoder. Cheap by construction: a set
    update and an integer. Never raises -- a frame from a backend we do not
    control must not be able to break decoding.
    """
    global _frames
    try:
        if not isinstance(kv, dict):
            return
        flush_now = None
        with _LOCK:
            for key in kv:
                # Populated, not merely present: a key the backend still emits
                # but has stopped filling is the same failure as a rename.
                if not kv.get(key):
                    continue
                name = str(key)
                if name in CORE_KEYS:
                    _core_seen.add(name)
                elif name in OPTIONAL_KEYS:
                    _optional_seen.add(name)
                elif len(_unexpected) < _MAX_UNEXPECTED:
                    _unexpected.add(name[:60])
            _frames += 1
            if _frames >= _WINDOW_FRAMES:
                flush_now = _snapshot_and_reset()
        if flush_now:
            _report(flush_now)
    except Exception:
        pass


def _seed_from_baseline() -> None:
    """Carry the ever-seen sets across a restart.

    Without this, the first window of every run would report every optional key
    as lost -- an alarm a day, about nothing.
    """
    global _seeded
    if _seeded:
        return
    _seeded = True
    try:
        from agent.ec_skills.browser_use_extension import drift_journal

        previous = drift_journal.last_shape(_SITE_LABEL, "ws_message_fields")
        if isinstance(previous, dict):
            for name in previous.get("optional_ever_seen") or ():
                if str(name) in OPTIONAL_KEYS:
                    _optional_seen.add(str(name))
            for name in list(previous.get("unexpected_ever_seen") or ())[:_MAX_UNEXPECTED]:
                _unexpected.add(str(name)[:60])
    except Exception:
        pass


def _snapshot_and_reset() -> Dict[str, Any]:
    global _frames
    _seed_from_baseline()
    snapshot = {
        "core_populated": sorted(_core_seen),
        "core_silent": sorted(CORE_KEYS - _core_seen),
        # Monotonic: gains are a signal, silence is not evidence.
        "optional_ever_seen": sorted(_optional_seen),
        "unexpected_ever_seen": sorted(_unexpected),
    }
    _core_seen.clear()          # core is judged per window
    _frames = 0
    return snapshot


def _report(shape: Dict[str, Any]) -> None:
    try:
        from agent.ec_skills.browser_use_extension import drift_journal

        drift_journal.note_shape(
            _SITE_LABEL, "ws_message_fields", shape,
            kind="ws_schema_change",
            context={"window_frames": _WINDOW_FRAMES},
        )
    except Exception:
        pass


def flush(force: bool = False) -> Optional[Dict[str, Any]]:
    """Report the current window early. For run end, and for tests.

    Without *force*, a window that has seen nothing is left alone: reporting an
    empty field set from a run that decoded no frames would look exactly like
    the backend having dropped every field at once.
    """
    with _LOCK:
        if not force and _frames == 0:
            return None
        snapshot = _snapshot_and_reset()
    _report(snapshot)
    return snapshot


def reset() -> None:
    """Drop the window and the ever-seen sets. Tests."""
    global _frames, _seeded
    with _LOCK:
        _core_seen.clear()
        _optional_seen.clear()
        _unexpected.clear()
        _frames = 0
        _seeded = False
