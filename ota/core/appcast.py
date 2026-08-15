"""
Appcast XML parsing utilities.

Self-contained implementation that parses Sparkle-compatible appcast XML format.
No external Sparkle/WinSparkle framework dependencies required.

Features:
- Parse appcast XML (Sparkle 1.x/2.x compatible format)
- Select best item for current platform/arch
- Compare versions with simple, dependency-free semver-ish comparison
- Support Ed25519 signature verification
"""
from __future__ import annotations

import re
from functools import cmp_to_key
import platform as _platform
from dataclasses import dataclass
from typing import List, Optional, Tuple
import xml.etree.ElementTree as ET

from utils.logger_helper import logger_helper as logger


# User-prefix parsing ---------------------------------------------------
#
# See ota/docs/multi_version_picker.md for the full rationale. Short version:
# a Sparkle version string may carry an optional ``<user>_`` prefix, e.g.
# ``songc_v26.05.03.22.22``. Items without such a prefix are treated as
# *universal* (visible to every user). Items with a prefix are only shown
# to the user whose email local-part matches that prefix (case-insensitive).
#
# We deliberately restrict what can be considered a user prefix so we don't
# accidentally strip a legitimate build-suffix from versions that happen to
# contain an underscore, and so prerelease words like ``rc_v1.0`` don't get
# misread as a user identity.

# Words that must NEVER be interpreted as a user prefix. These are common
# prerelease / channel tags that some build pipelines put before the version
# core. Prerelease information belongs *after* a ``-`` in the version core
# (``v1.0-rc.1``), which ``compare_versions`` already handles correctly.
_FORBIDDEN_USER_PREFIXES = frozenset({
    "rc", "beta", "alpha", "preview", "dev", "snapshot", "nightly",
    "canary", "insider", "edge",
})


def _split_user_prefix(raw_version: str) -> Tuple[Optional[str], str]:
    """Peel an optional ``<user>_`` prefix off a raw version string.

    Examples::

        _split_user_prefix("songc_v26.05.03.22.22") == ("songc", "v26.05.03.22.22")
        _split_user_prefix("v0.9.11")                == (None, "v0.9.11")
        _split_user_prefix("26.05.03.22.22")         == (None, "26.05.03.22.22")
        _split_user_prefix("rc_v1.0")                == (None, "rc_v1.0")
        _split_user_prefix("songc2_v1.0")            == ("songc2", "v1.0")

    The prefix is returned lower-cased so caller matching is
    case-insensitive.
    """
    if not raw_version or "_" not in raw_version:
        return None, raw_version
    head, rest = raw_version.split("_", 1)
    head = head.strip()
    if not head or not rest:
        return None, raw_version
    # Prefix must contain at least one non-digit, non-dot character,
    # otherwise the ``_`` is part of the version itself (e.g. ``26_05_03``
    # style) and we leave it alone.
    head_stripped = head.replace(".", "")
    if head_stripped.isdigit():
        return None, raw_version
    # Reject reserved prerelease / channel words.
    if head.lower() in _FORBIDDEN_USER_PREFIXES:
        return None, raw_version
    # Loose sanity check: a user prefix should look like an identifier,
    # not contain whitespace or weird punctuation. We allow letters,
    # digits, dot, dash. Anything else -> treat the ``_`` as version data.
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", head):
        return None, raw_version
    return head.lower(), rest


@dataclass
class AppcastItem:
    version: str
    url: str
    os: Optional[str] = None  # macos | windows | linux (custom)
    arch: Optional[str] = None  # x86_64 | arm64 | None (universal)
    length: Optional[int] = None
    content_type: Optional[str] = None
    ed_signature: Optional[str] = None  # Sparkle 2: edSignature (Ed25519, base64)
    alternate_url: Optional[str] = None  # Accelerated/alternate download URL
    description_html: Optional[str] = None
    pub_date: Optional[str] = None
    # Optional per-user tag parsed from the leading ``<user>_`` segment of
    # the raw version string. ``None`` means the item is universal (visible
    # to every user). Populated by :func:`parse_appcast`; never parsed from
    # the XML directly (today). See ota/docs/multi_version_picker.md.
    user_prefix: Optional[str] = None
    # The version string with any ``<user>_`` prefix peeled off. This is
    # what should be used for version comparison / display. ``version`` is
    # preserved verbatim so we can still show ``songc_v26.05.03.22.22`` to
    # the user if desired.
    version_core: Optional[str] = None


def parse_appcast(xml_text: str) -> List[AppcastItem]:
    """Parse Sparkle appcast XML and return a list of AppcastItem.

    We extract attributes we need:
      - enclosure/@url (download)
      - enclosure/@sparkle:version (version)
      - enclosure/@sparkle:os (os)
      - enclosure/@sparkle:arch (arch)
      - enclosure/@length (size)
      - enclosure/@type (content-type)
      - enclosure/@sparkle:edSignature (Ed25519 signature)
      - enclosure/@sparkle:alternateUrl (accelerated/alternate download URL)
      - item/description (release notes HTML)
      - item/pubDate
    """
    ns = {
        'sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle'
    }

    root = ET.fromstring(xml_text)
    items: List[AppcastItem] = []

    for item in root.findall('./channel/item'):
        enclosure = item.find('enclosure')
        if enclosure is None:
            continue
        url = enclosure.get('url') or ''
        version = enclosure.get(f"{{{ns['sparkle']}}}version") or ''
        os_name = enclosure.get(f"{{{ns['sparkle']}}}os") or None
        arch = enclosure.get(f"{{{ns['sparkle']}}}arch") or None
        length_val = enclosure.get('length')
        content_type = enclosure.get('type')
        ed_sig = enclosure.get(f"{{{ns['sparkle']}}}edSignature") or None
        alternate_url = enclosure.get(f"{{{ns['sparkle']}}}alternateUrl") or None
        
        # Debug: Log all enclosure attributes
        logger.debug(f"[APPCAST] Enclosure attributes for version {version}:")
        for key, value in enclosure.attrib.items():
            logger.debug(f"[APPCAST]   {key} = {value}")

        # Description may be CDATA/HTML
        desc_el = item.find('description')
        if desc_el is not None:
            # Get text content (CDATA is automatically unwrapped by ET)
            desc_html = ''.join(desc_el.itertext()).strip()
            # Remove any trailing ]]> that might be included
            if desc_html.endswith(']]>'):
                desc_html = desc_html[:-3].strip()
        else:
            desc_html = None
        pub_date_el = item.find('pubDate')
        pub_date = pub_date_el.text if pub_date_el is not None else None

        try:
            length = int(length_val) if length_val else None
        except ValueError:
            length = None

        if not url or not version:
            continue

        user_prefix, version_core = _split_user_prefix(version)

        items.append(AppcastItem(
            version=version,
            url=url,
            os=os_name,
            arch=arch,
            length=length,
            content_type=content_type,
            ed_signature=ed_sig,
            alternate_url=alternate_url,
            description_html=desc_html,
            pub_date=pub_date,
            user_prefix=user_prefix,
            version_core=version_core,
        ))

    return items


def current_os_tag() -> str:
    sysname = _platform.system().lower()
    if sysname == 'darwin':
        return 'macos'
    if sysname == 'windows':
        return 'windows'
    return 'linux'


def normalize_arch_tag(arch: Optional[str]) -> str:
    a = (arch or '').lower()
    if a in ('amd64', 'x64', 'x86_64'):  # normalize to amd64
        return 'amd64'
    if a in ('aarch64', 'arm64', 'arm64e'):  # normalize to aarch64
        return 'aarch64'
    # Unknown -> return original or empty
    return a or ''


def _normalize_version_text(v: str) -> str:
    """Normalize version text for comparison.

    - strip spaces
    - remove optional leading 'v' prefix (v1.2.3 -> 1.2.3)
    - drop build metadata (+...)
    """
    s = (v or '').strip()
    if s.lower().startswith('v'):
        s = s[1:].strip()
    if '+' in s:
        s = s.split('+', 1)[0]
    return s


def _parse_main_version_parts(v: str) -> List[int]:
    """Parse main numeric version parts, supporting multi-segment versions."""
    main = _normalize_version_text(v).split('-', 1)[0]
    parts = main.split('.') if main else []
    nums: List[int] = []
    for p in parts:
        token = p.strip()
        if not token:
            continue
        if token.isdigit():
            nums.append(int(token))
            continue
        # Fallback: keep leading numeric prefix (e.g. "1rc1" -> 1)
        m = re.match(r'^(\d+)', token)
        if m:
            nums.append(int(m.group(1)))
            continue
        break
    return nums or [0]


def _parse_prerelease_parts(v: str) -> List[str]:
    """Parse prerelease identifiers after '-' (e.g. beta.1 -> ['beta', '1'])."""
    s = _normalize_version_text(v)
    if '-' not in s:
        return []
    suffix = s.split('-', 1)[1].strip()
    if not suffix:
        return []
    return [p.strip() for p in suffix.split('.') if p.strip()]


def compare_versions(v1: str, v2: str) -> int:
    """Compare two semver-like version strings.

    Supports:
    - leading 'v' prefix
    - multi-segment numeric versions (e.g. 0.7.0.1)
    - prerelease tags (e.g. -beta, -rc.1)

    Returns:
      >0 if v1 > v2
       0 if equal
      <0 if v1 < v2
    """
    n1 = _parse_main_version_parts(v1)
    n2 = _parse_main_version_parts(v2)
    max_len = max(len(n1), len(n2))
    for i in range(max_len):
        a = n1[i] if i < len(n1) else 0
        b = n2[i] if i < len(n2) else 0
        if a != b:
            return 1 if a > b else -1

    p1 = _parse_prerelease_parts(v1)
    p2 = _parse_prerelease_parts(v2)

    # Release > prerelease when main parts are equal
    if not p1 and not p2:
        return 0
    if not p1:
        return 1
    if not p2:
        return -1

    # Compare prerelease identifiers using semver-like precedence
    min_len = min(len(p1), len(p2))
    for i in range(min_len):
        a = p1[i]
        b = p2[i]
        a_num = a.isdigit()
        b_num = b.isdigit()
        if a_num and b_num:
            ai = int(a)
            bi = int(b)
            if ai != bi:
                return 1 if ai > bi else -1
        elif a_num and not b_num:
            return -1
        elif not a_num and b_num:
            return 1
        else:
            if a != b:
                return 1 if a > b else -1

    if len(p1) == len(p2):
        return 0
    return 1 if len(p1) > len(p2) else -1


def version_tuple(v: str) -> Tuple[int, int, int]:
    # Backward-compatible helper kept for callers that only need X.Y.Z display/sorting.
    nums = _parse_main_version_parts(v)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])  # type: ignore[return-value]


def select_eligible_versions(
    items: List[AppcastItem],
    platform_tag: Optional[str],
    current_version: str,
    arch_tag: Optional[str] = None,
    user_prefix: Optional[str] = None,
) -> List[AppcastItem]:
    """Return every item the current user is eligible to install, newest-first.

    Filters:
      * ``item.os`` must match ``platform_tag`` (or be ``None``).
      * ``item.arch`` must match ``arch_tag`` (or be ``None``) when arch is
        given.
      * ``item.version_core`` must compare strictly greater than
        ``current_version``.
      * ``item.user_prefix`` must be either ``None`` (universal) or exactly
        equal to the provided ``user_prefix`` (case-insensitive; the
        caller should already have normalized it).

    An empty / ``None`` ``user_prefix`` means "logged-out or unknown
    user" and will only see universal items.

    Results are sorted newest-first using :func:`compare_versions` on the
    version core (without the ``<user>_`` prefix), so a user who cares
    about multiple parallel builds can pick from the full list.
    """
    if not items:
        return []
    tag = platform_tag or current_os_tag()
    arch = normalize_arch_tag(arch_tag)
    normalized_user = (user_prefix or "").strip().lower() or None

    candidates = [it for it in items if (it.os is None or it.os.lower() == tag)]
    if arch:
        candidates = [
            it for it in candidates
            if (it.arch is None or normalize_arch_tag(it.arch) == arch)
        ]
    # User-prefix filter: universal items always pass; tagged items only
    # pass when the tag matches the current user.
    def _user_ok(it: AppcastItem) -> bool:
        if it.user_prefix is None:
            return True
        return normalized_user is not None and it.user_prefix == normalized_user
    candidates = [it for it in candidates if _user_ok(it)]

    # Version filter: strictly newer than current (use version_core so the
    # ``<user>_`` prefix does not break comparison).
    def _version_core(it: AppcastItem) -> str:
        return it.version_core or it.version
    candidates = [
        it for it in candidates
        if compare_versions(_version_core(it), current_version) > 0
    ]

    candidates.sort(
        key=cmp_to_key(lambda a, b: compare_versions(_version_core(a), _version_core(b))),
        reverse=True,
    )
    return candidates


def item_to_update_dict(item: AppcastItem) -> dict:
    """Shape an :class:`AppcastItem` into the dict the OTA GUI expects.

    Used by the three platform updaters to build both the legacy
    single-item ``update_info`` fields and the new
    ``update_info['available_versions']`` list (see
    ``ota/docs/multi_version_picker.md``). Keeping this in one place
    guarantees every downstream consumer — the single-version
    confirmation dialog, the new multi-version picker, and the OTA
    download manager — sees identical field names for identical data.

    The alternate-URL auto-derivation rule (S3 bucket → S3 accelerate)
    was previously duplicated across all three platform updaters; it
    now lives here so new items picked up by the multi-version picker
    benefit from it automatically. COS appcasts rely on the AWS-style
    fallback remaining correct for S3 only; COS uses Tencent's CDN
    directly so no client-side rewrite is needed.
    """
    alt = item.alternate_url
    if (
        not alt
        and item.url
        and ".s3." in item.url
        and "amazonaws.com" in item.url
    ):
        alt = item.url.replace(".s3.", ".s3-accelerate.")
    return {
        "version": item.version,
        "version_core": item.version_core or item.version,
        "user_prefix": item.user_prefix,
        "download_url": item.url,
        "alternate_url": alt,
        "file_size": item.length or 0,
        "signature": item.ed_signature or "",
        "description": item.description_html or "",
        "pub_date": item.pub_date,
        "os": item.os,
        "arch": item.arch,
    }


def select_latest_for_platform(
    items: List[AppcastItem],
    platform_tag: Optional[str],
    current_version: str,
    arch_tag: Optional[str] = None,
    user_prefix: Optional[str] = None,
) -> Optional[AppcastItem]:
    """Pick the single newest eligible item, or ``None`` if none qualify.

    Thin back-compat wrapper over :func:`select_eligible_versions`. All
    existing callers continue to work unchanged; callers that want the
    full list should use :func:`select_eligible_versions` directly.
    """
    eligible = select_eligible_versions(
        items, platform_tag, current_version, arch_tag, user_prefix
    )
    return eligible[0] if eligible else None

