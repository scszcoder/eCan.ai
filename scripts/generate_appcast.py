#!/usr/bin/env python3
"""
Generate Sparkle/winSparkle appcast.xml from the current GitHub Release context.

- Reads release payload via GITHUB_EVENT_PATH
- For each asset, determines platform (macos/windows/linux) from file extension
- Builds a single <item> with multiple <enclosure> (one per platform)
- Optionally computes Sparkle 2 edSignature (Ed25519 base64) for each asset
  using ED25519_PRIVATE_KEY (PEM) provided via GitHub Secrets
- Writes appcast.xml to ./dist/appcast/appcast.xml

Requirements:
  pip install requests cryptography

Secrets/env expected:
  - ED25519_PRIVATE_KEY (optional): PEM private key for signing assets
  - GITHUB_TOKEN (provided by GitHub Actions)

This script is CI-oriented and safe to run only within GitHub Actions on a release event.
"""
from __future__ import annotations

import os
import json
import base64
import pathlib
import datetime as dt
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

import requests

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False


OWNER_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # e.g., scszcoder/ecbot
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")
ED25519_PRIVATE_KEY_PEM = os.environ.get("ED25519_PRIVATE_KEY", "")

OUTPUT_DIR = pathlib.Path("dist/appcast")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_FILE = OUTPUT_DIR / "appcast.xml"

SPARKLE_NS = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', SPARKLE_NS)


def load_release_payload() -> Optional[Dict[str, Any]]:
    if not EVENT_PATH or not os.path.exists(EVENT_PATH):
        return None
    with open(EVENT_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)
    # Prefer 'release' payload if present; otherwise return the whole payload (manual run)
    return payload.get("release") or payload


def detect_platform(asset_name: str) -> Optional[str]:
    n = asset_name.lower()
    if n.endswith((".dmg", ".zip")):
        return "macos"
    if n.endswith((".exe", ".msi")):
        return "windows"
    if n.endswith((".tar.gz", ".tgz", ".appimage")):
        return "linux"
    return None


def detect_arch(asset_name: str) -> Optional[str]:
    n = asset_name.lower()
    # Common patterns (normalize to aarch64 / amd64)
    if any(k in n for k in ["aarch64", "arm64", "apple-silicon", "silicon"]):
        return "aarch64"
    if any(k in n for k in ["amd64", "x86_64", "x64"]):
        return "amd64"
    # If no hint, return None (treated as generic/universal)
    return None


def get_assets(release: Dict[str, Any]) -> List[Dict[str, Any]]:
    assets = release.get("assets", [])
    return assets


def load_private_key() -> Optional[ed25519.Ed25519PrivateKey]:
    if not ED25519_PRIVATE_KEY_PEM or not CRYPTO_AVAILABLE:
        return None
    try:
        # Support base64-encoded PEM in secret to avoid multiline issues
        pem_bytes = ED25519_PRIVATE_KEY_PEM.strip().encode("utf-8")
        # If looks like base64, try to decode
        if b"BEGIN" not in pem_bytes:
            try:
                pem_bytes = base64.b64decode(pem_bytes)
            except Exception:
                pass
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, ed25519.Ed25519PrivateKey):
            raise ValueError("Provided private key is not Ed25519")
        return key
    except Exception as e:
        print(f"[WARN] Failed to load ED25519 private key: {e}")
        return None


def download_asset(url: str) -> bytes:
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/octet-stream",
        "User-Agent": "generate-appcast-script",
    }
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    return r.content


def sign_bytes_ed25519(private_key: ed25519.Ed25519PrivateKey, data: bytes) -> str:
    sig = private_key.sign(data)
    return base64.b64encode(sig).decode("ascii")


def build_appcast(
    release: Dict[str, Any],
    platform_filter: Optional[str] = None,
    arch_filter: Optional[str] = None,
) -> bytes:
    tag = release.get("tag_name", "")
    version = tag[1:] if tag.startswith("v") else tag
    pub_date = release.get("published_at") or release.get("created_at") or dt.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    description = release.get("body", "") or ""

    rss = ET.Element("rss", attrib={"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = f"{OWNER_REPO} Updates"
    ET.SubElement(channel, "description").text = f"Most recent updates to {OWNER_REPO} ({platform_filter or 'all'}/{arch_filter or 'any'})"
    ET.SubElement(channel, "language").text = "en"

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = f"Release {version}"
    desc = ET.SubElement(item, "description")
    desc.text = f"<![CDATA[{description}]]>"
    ET.SubElement(item, "pubDate").text = pub_date

    private_key = load_private_key()

    count = 0
    for asset in get_assets(release):
        name = asset.get("name", "")
        platform = detect_platform(name)
        if not platform:
            continue
        if platform_filter and platform != platform_filter:
            continue
        arch = detect_arch(name)
        if arch_filter and arch and arch != arch_filter:
            continue
        url = asset.get("browser_download_url")
        length = int(asset.get("size", 0))
        content_type = "application/octet-stream"
        ed_sig: Optional[str] = None

        if private_key is not None and url:
            try:
                data = download_asset(url)
                ed_sig = sign_bytes_ed25519(private_key, data)
                if length == 0:
                    length = len(data)
            except Exception as e:
                print(f"[WARN] Failed to compute edSignature for {name}: {e}")

        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", url)
        enclosure.set(f"{{{SPARKLE_NS}}}version", version)
        enclosure.set(f"{{{SPARKLE_NS}}}os", platform)
        if arch:
            enclosure.set(f"{{{SPARKLE_NS}}}arch", arch)
        enclosure.set("length", str(length))
        enclosure.set("type", content_type)
        if ed_sig:
            enclosure.set(f"{{{SPARKLE_NS}}}edSignature", ed_sig)
        count += 1

    if count == 0:
        msg = f"[WARN] No assets found for platform={platform_filter} arch={arch_filter} - skipping appcast generation"
        print(msg)
        return b""  # Signal caller to skip writing

    xml_bytes = ET.tostring(rss, encoding="utf-8")
    return b"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" + xml_bytes


def main(
    release_payload: Optional[Dict[str, Any]] = None,
    platform_filter: Optional[str] = None,
    arch_filter: Optional[str] = None,
    output_path: Optional[str] = None,
):
    release = release_payload or load_release_payload()
    if not release:
        raise RuntimeError("No release payload provided. Pass JSON or run in GitHub Actions on a release event.")
    xml_bytes = build_appcast(release, platform_filter=platform_filter, arch_filter=arch_filter)
    if not xml_bytes:
        # Nothing to write (no assets matched)
        print("[SKIP] No appcast written due to no matching assets")
        return
    out_file = pathlib.Path(output_path) if output_path else OUTPUT_FILE
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "wb") as f:
        f.write(xml_bytes)
    print(f"[OK] appcast.xml written to {out_file}")


if __name__ == "__main__":
    main()

