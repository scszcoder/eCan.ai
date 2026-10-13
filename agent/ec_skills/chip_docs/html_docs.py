"""HTML editions of crawled chip documents (code only, no LLM).

Newer Microchip documents have an HTML edition on onlinedocs.microchip.com next
to the PDF; it parses far better for RAG (register tables, multi-page tables).
``raw/collect_docs.js`` records it as ``html_url`` on each document.

``backfill`` adds ``html_url`` to the ``raw/docs/<part>.json`` lists of parts
crawled before the collect script knew about it, by re-reading each product
page in a real Chrome (Microchip's CDN refuses plain HTTP clients).

    python -m agent.ec_skills.chip_docs.html_docs backfill C:/chip_docs/Microchip
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from agent.ec_skills.chip_docs.crawl_executor import parse_status

BACKFILL_LOG = "html_backfill_done.txt"


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill", help="add html_url to doc lists of parts already crawled")
    b.add_argument("root", type=Path, help="vendor folder, e.g. C:/chip_docs/Microchip")
    b.add_argument("--profile", type=Path, help="Chrome profile dir (default <root>/raw/_html_browser_profile)")
    b.add_argument("--limit", type=int, default=0)
    b.add_argument("--headless", action="store_true", help="the product pages never load headless (2026-10-13)")
    a = ap.parse_args()
    if a.cmd == "backfill":
        asyncio.run(backfill(a.root, a.profile or a.root / "raw" / "_html_browser_profile", a.limit, a.headless))


if __name__ == "__main__":
    main()
