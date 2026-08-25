"""Save-timestamp skill versioning.

A skill's ``version`` is the UTC timestamp of its last save, formatted as
``yymmddHHMMSSmmm`` — 15 digits, milliseconds last. Fixed-width digit
strings order lexicographically, so version comparison needs no parsing.

Legacy versions (semver placeholders like ``1.0.0``, ``1.0``, or empty)
sort OLDER than any timestamp version: the first save after this ships
upgrades the skill into the scheme, and every subscriber immediately sees
an update.
"""

import re
from datetime import datetime, timezone

_TIMESTAMP_VERSION_RE = re.compile(r"^\d{15}$")

# Comparison outcomes
LOCAL_NEWER = "local_newer"
CLOUD_NEWER = "cloud_newer"
SAME = "same"
UNKNOWN = "unknown"


def is_timestamp_version(value) -> bool:
    """Whether *value* is a 15-digit save-timestamp version."""
    return bool(_TIMESTAMP_VERSION_RE.match(str(value or "").strip()))


def new_skill_version(prev=None) -> str:
    """A fresh UTC save-timestamp version, monotonic w.r.t. *prev*.

    If the clock went backwards relative to a previous timestamp version
    (or two saves land in the same millisecond), returns prev + 1ms so the
    version always advances.
    """
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%y%m%d%H%M%S") + f"{now.microsecond // 1000:03d}"
    prev_str = str(prev or "").strip()
    if is_timestamp_version(prev_str) and stamp <= prev_str:
        stamp = str(int(prev_str) + 1).zfill(15)
    return stamp


def compare_skill_versions(local, cloud) -> str:
    """Compare a local and a cloud skill version.

    Returns LOCAL_NEWER / CLOUD_NEWER / SAME / UNKNOWN. A timestamp
    version always beats a legacy one; two differing legacy values are
    UNKNOWN (no order defined — callers should not prompt an update).
    """
    lv = str(local or "").strip()
    cv = str(cloud or "").strip()
    lts, cts = is_timestamp_version(lv), is_timestamp_version(cv)
    if lts and cts:
        if lv == cv:
            return SAME
        return LOCAL_NEWER if lv > cv else CLOUD_NEWER
    if lts:
        return LOCAL_NEWER
    if cts:
        return CLOUD_NEWER
    return SAME if lv == cv else UNKNOWN
