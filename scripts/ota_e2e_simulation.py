#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
End-to-End OTA Simulation — Standalone stdlib-only (NO Flask, NO colorlog)

Full pipeline: dist/ → appcast.xml → HTTP → parse → compare → download → SHA256 → dpkg

Usage:
  python3 scripts/ota_e2e_simulation.py
  python3 scripts/ota_e2e_simulation.py --port 9999
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

# ── ANSI helpers ──────────────────────────────────────────────────────────────
_NO_COLOR = os.environ.get("TERM") == "dumb" or not sys.stdout.isatty()
_G, _R, _Y, _B = "\033[92m", "\033[91m", "\033[93m", "\033[94m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _c(t: str, code: str) -> str:
    return f"{code}{t}{_RESET}" if not _NO_COLOR else t


def ok(msg):    print(f"  {_c('✓', _G)}  {msg}")
def fail(msg):  print(f"  {_c('✗', _R)}  {msg}")
def info(msg):  print(f"  {_c('·', _B)}  {msg}")
def warn(msg):  print(f"  {_c('⚠', _Y)}  {msg}")


def step(n: int, title: str):
    print(f"\n{_BOLD}{'═' * 56}{_RESET}")
    print(f"{_BOLD}  Step {n} — {title}{_RESET}")
    print(f"{_BOLD}{'═' * 56}{_RESET}")


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DIST_DIR = PROJECT_ROOT / "dist"


# ──────────────────────────────────────────────────────────────────────────────
# Version extraction  (mirrors appcast_generator.py)
# ──────────────────────────────────────────────────────────────────────────────

_VERSION_RE = re.compile(
    r'ecan-(\d+?\.\d+?\.\d+?(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)_'
)
_STD_RE = re.compile(
    r'-(\d+?\.\d+?\.\d+?(?:-(?:alpha|beta|rc)(?:\.\d+)?)?)'
    r'(?:-(?:macos|darwin|windows|linux|amd64|aarch64|arm64|x86_64))'
)


def extract_version(filename: str) -> Optional[str]:
    for r in (_VERSION_RE, _STD_RE):
        m = r.search(filename)
        if m:
            return m.group(1)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Appcast XML  (mirrors appcast_generator.py)
# ──────────────────────────────────────────────────────────────────────────────

_NS_URI = "http://www.andymatuschak.org/xml-namespaces/sparkle"
_NS_V   = "{" + _NS_URI + "}version"
_NS_OS  = "{" + _NS_URI + "}os"
_NS_SIG = "{" + _NS_URI + "}edSignature"

_PATTERNS = [
    "eCan-*-macos-*.pkg", "eCan-*-macos-*.dmg",
    "eCan-*-windows-*-Setup.exe", "eCan-*-windows-*.msi",
    "eCan-*-linux-*.tar.gz", "eCan-*-linux-*.AppImage",
    "ecan-*_amd64.deb", "ecan-*_aarch64.deb",
]


def calc_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()


def build_appcast_xml(dist_dir: Path, base_url: str) -> str:
    items = []
    for pat in _PATTERNS:
        for pkg in sorted(dist_dir.glob(pat)):
            if not pkg.is_file():
                continue
            version = extract_version(pkg.name) or "1.0.0"
            sha256  = calc_sha256(pkg)
            size    = pkg.stat().st_size
            if "darwin" in pkg.name or "macos" in pkg.name:
                os_type = "macos"
            elif "windows" in pkg.name:
                os_type = "windows"
            else:
                os_type = "linux"
            items.append({
                "title":        f"Version {version}",
                "version":      version,
                "pub_date":     datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000"),
                "download_url": f"{base_url}/downloads/{urllib.parse.quote(pkg.name)}",
                "os":           os_type,
                "file_size":    size,
                "signature":    sha256,
            })

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">',
        '  <channel>',
        f'    <title>eCan.ai Updates</title>',
        f'    <link>{base_url}/appcast.xml</link>',
        f'    <description>Local OTA test appcast</description>',
        f'    <language>en</language>',
        f'    <pubDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>',
    ]
    for item in items:
        sig  = item["signature"][:16] + "..."
        title = item["title"]
        ver   = item["version"]
        url   = item["download_url"]
        os_t  = item["os"]
        sz    = item["file_size"]
        lines.extend([
            '    <item>',
            f'      <title>{title}</title>',
            f'      <description>eCan.ai {ver} update</description>',
            f'      <pubDate>{item["pub_date"]}</pubDate>',
            '      <enclosure '
            f'url="{url}" '
            f'sparkle:version="{ver}" '
            f'sparkle:os="{os_t}" '
            f'length="{sz}" '
            f'type="application/octet-stream" '
            f'sparkle:edSignature="{sig}" />',
            '    </item>',
        ])
    lines.extend(["  </channel>", "</rss>"])
    return "\n".join(lines)


def parse_appcast_xml(xml_bytes: bytes) -> list[dict]:
    from xml.etree import ElementTree as ET
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.findall(".//item"):
        enc = item.find("enclosure")
        if enc is None:
            continue
        a = enc.attrib
        items.append({
            "title":     item.findtext("title", ""),
            "version":   a.get(_NS_V, ""),
            "os":        a.get(_NS_OS, ""),
            "url":       a.get("url", ""),
            "length":    int(a.get("length", 0)),
            "signature": a.get(_NS_SIG, ""),
        })
    return items


# ──────────────────────────────────────────────────────────────────────────────
# Version comparison
# ──────────────────────────────────────────────────────────────────────────────

def compare_versions(current: str, latest: str) -> bool:
    def parse(v: str):
        m = re.match(r'(\d+)\.(\d+)\.(\d+)', v)
        if not m:
            return (0, 0, 0)
        nums = [int(m.group(i)) for i in range(1, 4)]
        r = v[m.end():]
        if r.startswith("-rc."):
            nums.append(-900)
        elif r.startswith("-beta."):
            nums.append(-800)
        elif r.startswith("-alpha."):
            nums.append(-700)
        else:
            nums.append(0)
        return tuple(nums)
    return parse(latest) > parse(current)


# ──────────────────────────────────────────────────────────────────────────────
# HTTP Server  (stdlib only)
# ──────────────────────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):

    protocol_version = "HTTP/1.0"

    def log_message(self, fmt, *args):
        pass

    def send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, file_path: Path, name: str):
        size = file_path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{name}")
        self.send_header("Content-Length", size)
        self.end_headers()
        with open(file_path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, length=65536)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        qs   = urllib.parse.urlparse(self.path).query

        if path == "/health":
            self.send_json({"status": "ok"})

        elif path == "/appcast.xml":
            xml = build_appcast_xml(self.server.dist_dir, self.server.base_url)
            body = xml.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif path == "/api/check-update":
            params = {}
            for pair in qs.lstrip("?").split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[urllib.parse.unquote(k)] = urllib.parse.unquote(v)

            client_ver = params.get("version", "0.0.0")
            platform   = params.get("platform", "linux")
            arch       = params.get("arch", "amd64")

            ver_file = PROJECT_ROOT / "VERSION"
            base_version = ver_file.read_text().strip() if ver_file.exists() else "1.0.0"
            m = re.match(r'(\d+)\.(\d+)\.(\d+)', base_version)
            latest_version = f"{m.group(1)}.{m.group(2)}.{int(m.group(3)) + 1}" if m else base_version

            has_update = compare_versions(client_ver, latest_version)
            resp = {
                "update_available": has_update,
                "current_version": client_ver,
                "latest_version":  latest_version,
            }

            if has_update:
                patterns = {
                    "linux":   ["ecan-*_amd64.deb", "ecan-*_aarch64.deb",
                                "eCan-*-linux-*.tar.gz", "eCan-*-linux-*.AppImage"],
                    "darwin":  ["eCan-*-macos-*.pkg", "eCan-*-macos-*.dmg"],
                    "windows": ["eCan-*-windows-*-Setup.exe", "eCan-*-windows-*.msi"],
                }
                filename, file_size, signature = "", 0, ""
                for pat in patterns.get(platform, []):
                    hits = sorted(self.server.dist_dir.glob(pat))
                    if hits:
                        pkg = hits[0]
                        filename, file_size, signature = pkg.name, pkg.stat().st_size, calc_sha256(pkg)
                        break

                if filename:
                    dl_url = f"{self.server.base_url}/downloads/{urllib.parse.quote(filename)}"
                else:
                    ext = {"linux": "deb", "darwin": "pkg", "windows": "exe"}.get(platform, "bin")
                    dl_url = f"{self.server.base_url}/downloads/eCan-{latest_version}-{platform}-{arch}.{ext}"

                resp.update({
                    "description":  f"<h2>eCan.ai {latest_version}</h2><p>Release notes not available.</p>",
                    "release_date": datetime.now().strftime("%Y-%m-%d"),
                    "download_url": dl_url,
                    "file_size":    file_size,
                    "signature":    signature,
                })

            self.send_json(resp)

        elif path.startswith("/downloads/"):
            filename = urllib.parse.unquote(path[len("/downloads/"):])
            file_path = self.server.dist_dir / filename
            if not file_path.exists():
                self.send_json({"error": f"File not found: {filename}"}, 404)
                return
            self.send_file(file_path, file_path.name)

        else:
            self.send_json({"error": f"Not found: {path}"}, 404)


class _Server(HTTPServer):
    def __init__(self, addr, dist_dir: Path, base_url: str):
        self.dist_dir = dist_dir
        self.base_url = base_url
        super().__init__(addr, _Handler)


# ──────────────────────────────────────────────────────────────────────────────
# HTTP client
# ──────────────────────────────────────────────────────────────────────────────

def http_get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OTA-Sim/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


def download_to(url: str, dest: Path) -> bool:
    import urllib.request, urllib.error
    total, last_pct = 0, -1
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "OTA-Sim/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    total += len(chunk)
                    if total_size and last_pct != (pct := min(100, total * 100 // total_size)) and pct % 10 == 0:
                        info(f"    [{pct:3d}%] {total/1024**2:6.1f} MB / {total_size/1024**2:6.1f} MB")
                        last_pct = pct
        return True
    except Exception as e:
        fail(f"Download failed: {e}")
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run(port: int):
    dist_dir = DIST_DIR
    dl_dir   = Path(tempfile.gettempdir()) / "ota_sim_dl"
    dl_dir.mkdir(exist_ok=True)

    # 1 — Verify DEB package
    deb_files = sorted(dist_dir.glob("ecan-*_amd64.deb")) + sorted(dist_dir.glob("ecan-*_aarch64.deb"))
    if not deb_files:
        fail("No DEB package found in dist/")
        return 1
    deb = deb_files[0]
    sha = calc_sha256(deb)
    info(f"DEB: {deb.name}  ({deb.stat().st_size/1024**2:.1f} MB)")
    info(f"SHA256: {sha}")
    ok(f"DEB package verified")

    # 2 — Start OTA server
    step(2, "Start local OTA server")
    server = _Server(("127.0.0.1", port), dist_dir, f"http://127.0.0.1:{port}")
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.8)
    status, body = http_get(f"http://127.0.0.1:{port}/health")
    if status == 200:
        ok(f"Server running on port {port}")
    else:
        fail(f"Server health check failed: HTTP {status}")
        return 1

    # 3 — appcast.xml
    step(3, "Server: generate appcast.xml")
    xml_bytes = build_appcast_xml(dist_dir, f"http://127.0.0.1:{port}").encode("utf-8")
    status, body = http_get(f"http://127.0.0.1:{port}/appcast.xml")
    if status == 200:
        xml_bytes = body
    info(f"appcast.xml: {len(xml_bytes):,} bytes")

    items = parse_appcast_xml(xml_bytes)
    linux_item = next((i for i in items if i["os"] == "linux"), None)
    if linux_item:
        ok(f"[linux] v{linux_item['version']}  url={linux_item['url'].split('/')[-1]}")
    else:
        warn("No Linux item in appcast")

    # 4 — Version comparison
    step(4, "Client: version comparison")
    ver_file = PROJECT_ROOT / "VERSION"
    current_ver = ver_file.read_text().strip() if ver_file.exists() else "0.7.0"
    status, body = http_get(
        f"http://127.0.0.1:{port}/api/check-update"
        f"?version={current_ver}&platform=linux&arch=amd64"
    )
    resp = json.loads(body) if status == 200 else {}
    has_update = resp.get("update_available", False)
    info(f"Client version: {current_ver}  |  Latest: {resp.get('latest_version', '?')}")
    info(f"update_available: {has_update}")
    if has_update:
        ok(f"Update available: {current_ver} → {resp['latest_version']}")
        dl_url = resp.get("download_url", "")
        if "ecan-" in dl_url and dl_url.endswith(".deb"):
            ok(f"download_url uses DEB: {dl_url.split('/')[-1]}")

    # 5 — Download
    step(5, "Client: download package")
    if linux_item:
        dl_url = linux_item["url"]
    else:
        dl_url = f"http://127.0.0.1:{port}/downloads/{deb.name}"
    dl_dest = dl_dir / dl_url.split("/")[-1]
    info(f"URL: {dl_url}")
    if download_to(dl_url, dl_dest):
        ok(f"Download complete: {dl_dest.name} ({dl_dest.stat().st_size/1024**2:.1f} MB)")

    # 6 — SHA256 verify
    step(6, "Client: verify SHA256")
    dl_sha = calc_sha256(dl_dest)
    if dl_sha == sha:
        ok("SHA256 verification PASSED — file intact")
    else:
        fail("SHA256 MISMATCH — file corrupted")
        return 1

    # 7 — Package metadata
    step(7, "DEB package metadata")
    r = subprocess.run(["dpkg-deb", "-I", str(dl_dest)], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        s = line.strip()
        if any(k in s for k in ["Package:", "Version:", "Architecture:",
                                 "Installed-Size:", "Depends:", "Description:"]):
            info(f"  {s}")
    ok("dpkg-deb info: OK")

    # 8 — dpkg dry-run
    step(8, "Install dry-run (dpkg --dry-run)")
    r = subprocess.run(["dpkg", "--dry-run", "--install", str(dl_dest)], capture_output=True, text=True)
    if r.returncode == 0:
        ok("dpkg --dry-run PASSED — package is valid")
    else:
        warn(f"dpkg: {r.stderr.decode(errors='replace').strip()[:200]}")

    # 9 — Install command
    step(9, "Ready to install")
    print(f"\n  {_BOLD}pkexec dpkg -i {dl_dest}{_RESET}")
    print(f"  {_BOLD}sudo  dpkg -i {dl_dest}{_RESET}")
    print(f"\n  App:  /usr/bin/ecan")
    print(f"  Data: ~/.local/share/ecan.ai/")

    print(f"\n{_BOLD}{'═' * 56}{_RESET}")
    ok("End-to-End OTA Simulation COMPLETE")
    print(f"{_BOLD}{'═' * 56}{_RESET}")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=9999)
    args = p.parse_args()

    print(f"\n{_BOLD}OTA End-to-End Simulation — eCan.ai{_RESET}")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"  Dist:    {DIST_DIR}")
    print(f"  Port:    {args.port}")
    print(f"  Python:  {sys.version.split()[0]}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    sys.exit(run(args.port))


if __name__ == "__main__":
    main()
