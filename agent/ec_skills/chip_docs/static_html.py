"""Save a document's static HTML edition (code only, no browser).

ST publishes HTML editions of some documents next to the PDF
(``/resource/en/application_note/an4879-....html``). The landing page holds the
first section; the other sections (``chunk-NNN-....html``) and the images sit
under ``<stem>_asset/`` next to it, and all of it is plain static files.

The edition is saved as ``<out_root>/<doc id>/index.html`` plus ``asset/...``, with the
links rewritten to match, so it still reads offline. ST's stems run to ~100 characters
and appear twice in a path, past Windows' 260-character limit. Site pages, scripts
and styles are left out.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DONE = ".complete"
# 2026-10-16: st.com drops requests that don't look like a browser's
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
           "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
_REF = re.compile(rb"""(?:href|src|data-src)\s*=\s*["']([^"'#]+)|srcset\s*=\s*["']([^"']+)""", re.I)


def fetch(url: str) -> tuple[str, bytes]:
    """(final URL after redirects, body)."""
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r:
        return r.geturl(), r.read()


def _refs(page: bytes) -> list[str]:
    out = []
    for ref, srcset in _REF.findall(page):
        if ref:
            out.append(ref.decode("utf-8", "replace"))
        else:  # "a.png 1x, b.png 2x"
            out += [c.strip().split()[0] for c in srcset.decode("utf-8", "replace").split(",") if c.strip()]
    return out


def doc_id(url: str) -> str:
    """'an4879' for .../an4879-introduction-to-usb-....html."""
    return Path(urllib.parse.urlparse(url).path).stem.split("-")[0][:40]


def save_edition(url: str, out_root: Path, fetch=fetch) -> tuple[Path, list[str]]:
    """Save the edition at ``url``; returns its folder and the files saved (none if it
    was already complete). A link to a missing file (404) is skipped; any other failure
    raises and leaves the edition unfinished."""
    dest = Path(out_root) / doc_id(url)
    if (dest / DONE).exists():
        return dest, []
    final, body = fetch(url)
    name = Path(urllib.parse.urlparse(final).path).name
    prefix = urllib.parse.urljoin(final, Path(name).stem + "_asset/")
    files = {"index.html": body}
    pages, seen, missing = [(final, body)], {final}, []
    while pages:
        page_url, page = pages.pop()
        for ref in _refs(page):
            u = urllib.parse.urljoin(page_url, ref).split("?")[0]
            if not u.startswith(prefix) or u in seen:
                continue
            seen.add(u)
            rel = "asset/" + urllib.parse.unquote(u[len(prefix):])
            try:
                data = fetch(u)[1]
            except urllib.error.HTTPError as e:
                if e.code != 404:  # 2026-10-16: AN4879 links a page ST never published
                    raise
                missing.append(rel)
                continue
            files[rel] = data
            if u.endswith(".html"):
                pages.append((u, data))
    stem = Path(name).stem.encode()
    for rel, data in files.items():
        if rel.endswith(".html"):
            data = data.replace(stem + b"_asset/", b"asset/").replace(b"../" + stem + b".html", b"../index.html")
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    (dest / DONE).write_text(json.dumps({"url": url, "files": sorted(files), "missing": missing},
                                                indent=1), encoding="utf-8")
    return dest, sorted(files)
