"""HTML editions of crawled chip documents (code only, no LLM).

Newer Microchip documents have an HTML edition on onlinedocs.microchip.com next
to the PDF; it parses far better for RAG (register tables, multi-page tables).
``raw/collect_docs.js`` records it as ``html_url`` on each document.

``backfill`` adds ``html_url`` to the ``raw/docs/<part>.json`` lists of parts
crawled before the collect script knew about it, by re-reading each product
page in a real Chrome (Microchip's CDN refuses plain HTTP clients).

``crawl`` saves each HTML edition (one per unique ``html_url``; parts share
them) under ``<root>/html/<doc id>/``: every page reachable by links that stay
inside the document's folder, its images, and a ``manifest.json`` naming the
parts that list it. Each finished document is mirrored to the NAS.

    python -m agent.ec_skills.chip_docs.html_docs backfill C:/chip_docs/Microchip
    python -m agent.ec_skills.chip_docs.html_docs crawl C:/chip_docs/Microchip
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import urllib.parse
from pathlib import Path, PurePosixPath

from agent.ec_skills.chip_docs.crawl_executor import parse_status

BACKFILL_LOG = "html_backfill_done.txt"
CRAWL_LOG = "html_crawl_done.txt"
MAX_PAGES = 3000
# 2026-10-13: onlinedocs.microchip.com answered 503 to every client for hours;
# stop the run instead of marking every document failed
MAX_UNAVAILABLE = 3
MAINTENANCE = "down for maintenance"


def merge_html_urls(old: list[dict], new: list[dict]) -> int:
    """Copy ``html_url`` from a fresh collect into an older doc list, matching on
    the PDF url, else on type + title. Mutates ``old``; returns how many were set."""
    by_url = {d.get("url"): d for d in new if d.get("html_url")}
    by_title = {(d.get("type"), d.get("title")): d for d in new if d.get("html_url")}
    n = 0
    for d in old:
        if d.get("html_url"):
            continue
        hit = by_url.get(d.get("url")) or by_title.get((d.get("type"), d.get("title")))
        if hit:
            d["html_url"] = hit["html_url"]
            n += 1
    return n


def parts_to_backfill(root: Path) -> list[tuple[str, str]]:
    """(part, product page URL) for done parts not yet backfilled whose doc list
    has no html_url (parts collected by the new script already have them)."""
    rows, _ = parse_status((root / "status.md").read_text(encoding="utf-8"))
    log = root / "raw" / BACKFILL_LOG
    finished = set(log.read_text(encoding="utf-8").split()) if log.exists() else set()
    out = []
    for r in rows:
        f = root / "raw" / "docs" / f"{r['part']}.json"
        if r["state"] != "done" or r["part"] in finished or not f.exists():
            continue
        if any(d.get("html_url") for d in _load_docs(f)):
            continue
        out.append((r["part"], r["product page URL"]))
    return out


def _load_docs(f: Path) -> list[dict]:
    data = json.loads(f.read_text(encoding="utf-8"))
    return data.get("docs", []) if isinstance(data, dict) else data


async def backfill(root: Path, profile: Path, limit: int = 0, headless: bool = False) -> None:
    from playwright.async_api import async_playwright

    js = (root / "raw" / "collect_docs.js").read_text(encoding="utf-8")
    todo = parts_to_backfill(root)
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} parts to backfill", flush=True)
    log = root / "raw" / BACKFILL_LOG
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(profile), channel="chrome", headless=headless)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, (part, url) in enumerate(todo, 1):
            try:
                # "load" never fires on these pages (third-party scripts); the collect script waits for the table itself.
                await page.goto(url, timeout=90000, wait_until="domcontentloaded")
                fresh = await page.evaluate(js)
            except Exception as e:
                print(f"[{i}/{len(todo)}] {part}: FAILED {str(e).splitlines()[0][:200]}", flush=True)
                continue
            f = root / "raw" / "docs" / f"{part}.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            docs = data.get("docs", []) if isinstance(data, dict) else data
            n = merge_html_urls(docs, fresh)
            if n:
                f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            with log.open("a", encoding="utf-8") as fh:
                fh.write(part + "\n")
            print(f"[{i}/{len(todo)}] {part}: {n} html links", flush=True)
        await ctx.close()


def html_jobs(root: Path) -> dict[str, dict]:
    """Unique HTML editions across all doc lists: doc id -> {url, type, title, parts}."""
    jobs: dict[str, dict] = {}
    for f in sorted((root / "raw" / "docs").glob("*.json")):
        for d in _load_docs(f):
            url = d.get("html_url")
            # other vendors' editions (ST) are saved per part by download_docs_to_nas
            if not url or "onlinedocs.microchip.com" not in url:
                continue
            job = jobs.setdefault(doc_id(url), {"url": url, "type": d.get("type"), "title": d.get("title"),
                                                "parts": []})
            if f.stem not in job["parts"]:
                job["parts"].append(f.stem)
    return jobs


def doc_id(url: str) -> str:
    """The GUID in an onlinedocs URL (version suffix dropped), else a filesystem-safe path."""
    m = re.search(r"GUID-[0-9A-F-]{36}", url, re.I)
    if m:
        return m.group(0).upper()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", urllib.parse.urlparse(url).path.strip("/")) or "doc"


def doc_base(final_url: str) -> str:
    """The folder a document's pages live in: the landing page's URL up to its last '/'."""
    u = urllib.parse.urlparse(final_url)
    return f"{u.scheme}://{u.netloc}{u.path[:u.path.rfind('/') + 1]}"


def in_doc(link: str, base: str) -> str | None:
    """``link`` without query and fragment if it is a page of the document at ``base``."""
    u = urllib.parse.urlparse(link)
    clean = f"{u.scheme}://{u.netloc}{u.path}"
    if not clean.startswith(base):
        return None
    return clean if PurePosixPath(u.path).suffix.lower() in ("", ".html", ".htm") else None


def rel_path(url: str, base: str) -> str:
    """Where a document URL is saved, relative to the document's folder."""
    rel = urllib.parse.unquote(urllib.parse.urlparse(url[len(base):]).path) or "index.html"
    if rel.endswith("/"):
        rel += "index.html"
    elif not PurePosixPath(rel).suffix:
        rel += ".html"
    parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
    return "/".join(re.sub(r'[<>:"\\|?*]', "_", p) for p in parts)


class SiteUnavailable(Exception):
    pass


_PAGE_JS = """() => ({
  links: [...document.querySelectorAll('a[href]')].map(a => a.href),
  images: [...document.querySelectorAll('img[src]')].map(i => i.src),
  title: document.title,
})"""


async def crawl_doc(page, job: dict, out: Path) -> dict:
    """Save every page of one HTML document under ``out``. Returns its manifest."""
    resp = await page.goto(job["url"], timeout=90000, wait_until="domcontentloaded")
    if resp is not None and resp.status >= 500:
        raise SiteUnavailable(f"{resp.status} for {job['url']}")
    # 2026-10-13: after the 503s, onlinedocs served a "down for maintenance" page with status 200
    if MAINTENANCE in (await page.inner_text("body")).lower():
        raise SiteUnavailable(f"maintenance page for {job['url']}")
    base = doc_base(page.url)
    queue, seen, pages, images, failed = [in_doc(page.url, base) or page.url], set(), [], set(), []
    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            if page.url.split("#")[0] != url:
                resp = await page.goto(url, timeout=90000, wait_until="domcontentloaded")
                if resp is not None and resp.status >= 400:
                    failed.append(f"{url}: HTTP {resp.status}")
                    continue
            # the table of contents and the topic body are filled in by scripts
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception as e:
            if "Timeout" not in type(e).__name__:
                failed.append(f"{url}: {str(e).splitlines()[0][:200]}")
                continue
        info = await page.evaluate(_PAGE_JS)
        target = out / rel_path(url, base)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(await page.content(), encoding="utf-8")
        pages.append({"url": url, "file": rel_path(url, base), "title": info["title"]})
        for link in info["links"]:
            page_url = in_doc(link, base)
            if page_url and page_url not in seen:
                queue.append(page_url)
        images.update(i for i in info["images"] if i.startswith(base))
    for img in sorted(images):
        target = out / rel_path(img, base)
        if target.exists():
            continue
        try:
            r = await page.request.get(img, timeout=60000)
            if r.ok:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(await r.body())
            else:
                failed.append(f"{img}: HTTP {r.status}")
        except Exception as e:
            failed.append(f"{img}: {str(e).splitlines()[0][:200]}")
    manifest = {**job, "base": base, "pages": pages, "images": len(images), "failed": failed,
                "truncated": bool(queue)}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return manifest


def mirror_to_nas(out: Path, nas_dir: str) -> int:
    """Upload a document's folder; files already there with the same size are skipped."""
    from agent.ec_skills.nas import ugreen_nas

    listings: dict[str, dict] = {}
    n = 0
    for f in sorted(p for p in out.rglob("*") if p.is_file()):
        remote = f"{nas_dir}/{f.relative_to(out).as_posix()}"
        folder = str(PurePosixPath(remote).parent)
        if folder not in listings:
            listings[folder] = {e["name"]: e["size"] for e in ugreen_nas.nas_list(folder)}
        if listings[folder].get(f.name) != f.stat().st_size:
            ugreen_nas.nas_upload(str(f), remote)
            n += 1
    return n


async def crawl(root: Path, profile: Path, limit: int = 0, nas: bool = True) -> None:
    from playwright.async_api import async_playwright

    log = root / "raw" / CRAWL_LOG
    finished = set(log.read_text(encoding="utf-8").split()) if log.exists() else set()
    todo = [(k, j) for k, j in html_jobs(root).items() if k not in finished]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} HTML documents to crawl", flush=True)
    if not todo:
        return
    unavailable = 0
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(profile), channel="chrome", headless=False)
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for i, (key, job) in enumerate(todo, 1):
            out = root / "html" / key
            try:
                m = await crawl_doc(page, job, out)
                unavailable = 0
            except SiteUnavailable as e:
                unavailable += 1
                print(f"[{i}/{len(todo)}] {key}: site unavailable ({e})", flush=True)
                if unavailable >= MAX_UNAVAILABLE:
                    print("onlinedocs is unavailable; stopping. Re-run later to resume.", flush=True)
                    break
                continue
            except Exception as e:
                print(f"[{i}/{len(todo)}] {key}: FAILED {str(e).splitlines()[0][:200]}", flush=True)
                continue
            uploaded = 0
            if nas:
                try:
                    uploaded = await asyncio.to_thread(mirror_to_nas, out, f"{root.name}/html/{key}")
                except Exception as e:  # the local copy is kept; a re-run retries the upload
                    print(f"[{i}/{len(todo)}] {key}: NAS mirror failed: {e}", flush=True)
                    continue
            with log.open("a", encoding="utf-8") as fh:
                fh.write(key + "\n")
            print(f"[{i}/{len(todo)}] {key}: {len(m['pages'])} pages, {m['images']} images, "
                  f"{len(m['failed'])} failed, {uploaded} uploaded{' (truncated)' if m['truncated'] else ''}",
                  flush=True)
        await ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="add html_url to doc lists of parts already crawled")
    b.add_argument("root", type=Path, help="vendor folder, e.g. C:/chip_docs/Microchip")
    b.add_argument("--profile", type=Path, help="Chrome profile dir (default <root>/raw/_html_browser_profile)")
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--headless", action="store_true", help="the product pages never load headless (2026-10-13)")
    c = sub.add_parser("crawl", help="save every HTML edition's pages and images, mirrored to the NAS")
    c.add_argument("root", type=Path, help="vendor folder, e.g. C:/chip_docs/Microchip")
    c.add_argument("--profile", type=Path, help="Chrome profile dir (default <root>/raw/_html_browser_profile)")
    c.add_argument("--limit", type=int, default=0)
    c.add_argument("--no-nas", action="store_true", help="keep the local copy only")
    a = ap.parse_args()
    # the NAS upload roots (ECAN_NAS_UPLOAD_ROOTS) live in run.env, which only main.py loads
    from dotenv import load_dotenv
    from utils.run_env import run_env_path
    load_dotenv(run_env_path(), override=False)
    profile = a.profile or a.root / "raw" / "_html_browser_profile"
    if a.cmd == "backfill":
        asyncio.run(backfill(a.root, profile, a.limit, a.headless))
    elif a.cmd == "crawl":
        asyncio.run(crawl(a.root, profile, a.limit, not a.no_nas))


if __name__ == "__main__":
    main()
