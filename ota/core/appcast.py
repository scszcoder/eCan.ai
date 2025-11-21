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
import platform as _platform
from dataclasses import dataclass
from typing import List, Optional, Tuple
import xml.etree.ElementTree as ET


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


def version_tuple(v: str) -> Tuple[int, int, int]:
    parts = re.split(r'[.+-]', v)
    nums: List[int] = []
    for p in parts:
        if p.isdigit():
            nums.append(int(p))
        else:
            break
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])  # type: ignore[return-value]


def select_latest_for_platform(items: List[AppcastItem], platform_tag: Optional[str], current_version: str, arch_tag: Optional[str] = None) -> Optional[AppcastItem]:
    """Pick the latest item for the given platform/arch whose version > current_version.
    If arch is provided, prefer exact arch match; items without arch are treated as universal.
    """
    if not items:
        return None
    tag = platform_tag or current_os_tag()
    arch = normalize_arch_tag(arch_tag)
    cur = version_tuple(current_version or '0.0.0')
    # First pass: exact arch match or universal
    candidates = [it for it in items if (it.os is None or it.os.lower() == tag)]
    if arch:
        arch_candidates = [it for it in candidates if (it.arch is None or normalize_arch_tag(it.arch) == arch)]
    else:
        arch_candidates = candidates
    if not arch_candidates:
        return None
    arch_candidates.sort(key=lambda it: version_tuple(it.version), reverse=True)
    for it in arch_candidates:
        if version_tuple(it.version) > cur:
            return it
    return None

