"""amazon.com pages, driven in a real Chrome (own profile, over CDP) the way a shopper uses them.

Findings behind this (C:/product_research/raw/NOTES.md): a direct /s?k= search URL gets the
"Something went wrong" bot page, so searches go through the search box; product and review pages
need a signed-in shopper account in the profile. The user signs in; this code never does, and
stops (Blocked) on a sign-in, captcha or bot page.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import random
import re
import socket
import subprocess
import urllib.parse
from datetime import datetime
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HOME = "https://www.amazon.com/"
POS_REVIEWS, NEG_REVIEWS = 10, 20


class Blocked(Exception):
    """Amazon wants a human: sign-in, captcha or bot page."""


class Gone(Exception):
    """The product page doesn't exist (any more)."""


async def pause(lo: float, hi: float) -> None:
    await asyncio.sleep(random.uniform(lo, hi))


@contextlib.asynccontextmanager
async def browser(profile: Path):
    """A page in Chrome started on ``profile``. Fails if another Chrome holds the profile: Chrome
    would hand our window to it and exit, and no debugging port would open."""
    from playwright.async_api import async_playwright

    profile.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen([CHROME, f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                             "--no-first-run", "--no-default-browser-check", "--window-size=1280,900",
                             "about:blank"])
    try:
        for _ in range(60):
            if proc.poll() is not None:
                raise RuntimeError(f"Chrome exited at once: is the profile open in another window? {profile}")
            try:
                socket.create_connection(("127.0.0.1", port), 0.5).close()
                break
            except OSError:
                await asyncio.sleep(0.5)
        else:
            raise RuntimeError(f"Chrome debugging port never opened ({profile})")
        async with async_playwright() as p:
            b = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = b.contexts[0]
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            page.set_default_timeout(60000)
            try:
                yield page
            finally:
                with contextlib.suppress(Exception):
                    await b.close()
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(10)


# ── page checks ────────────────────────────────────────────────────────────

_STATE_JS = """() => ({url: location.href, title: document.title,
  captcha: !!document.querySelector('form[action*="validateCaptcha"]')})"""


def blocked_reason(info: dict) -> str | None:
    if "/ap/signin" in info["url"] or "/ap/mfa" in info["url"]:
        return "sign-in required"
    if info.get("captcha") or "/errors/validateCaptcha" in info["url"]:
        return "captcha"
    if "something went wrong" in info.get("title", "").lower():
        return "bot check page"
    return None


async def goto(page, url: str) -> dict:
    await page.goto(url, wait_until="domcontentloaded")
    await pause(3, 6)
    info = await page.evaluate(_STATE_JS)
    reason = blocked_reason(info)
    if reason:
        raise Blocked(f"{reason} ({info['url'][:120]})")
    return info


# ── search ─────────────────────────────────────────────────────────────────

_SEARCH_JS = """() => [...document.querySelectorAll('div[data-component-type="s-search-result"]')].map(t => ({
  asin: t.dataset.asin || '', index: Number(t.dataset.index),
  sponsored: !!t.querySelector('.puis-sponsored-label-text, .s-sponsored-label-text') || /AdHolder/.test(t.className),
  title: ((t.querySelector('h2') || {}).innerText || '').trim(),
  rating: ((t.querySelector('i[class*="a-icon-star"] span, span.a-icon-alt') || {}).innerText || '').trim(),
  price: ((t.querySelector('.a-price .a-offscreen') || {}).textContent || '').trim(),
  bought: [...t.querySelectorAll('span')].map(s => s.innerText).find(s => /bought in past/i.test(s || '')) || ''}))"""


def pick_organic(tiles: list[dict], n: int) -> list[dict]:
    """First ``n`` organic tiles in page order, each ASIN once (ads repeat organic ASINs)."""
    seen, out = set(), []
    for t in tiles:
        if t["sponsored"] or not t["asin"] or t["asin"] in seen:
            continue
        seen.add(t["asin"])
        out.append(t)
    return out[:n]


async def search(page, phrase: str, n: int = 20, max_pages: int = 3) -> dict:
    await goto(page, HOME)
    box = page.locator("#twotabsearchtextbox")
    await box.focus()          # a click can land on the sign-in popover
    await box.fill("")
    for ch in phrase:
        await box.type(ch, delay=random.randint(60, 160))
    await pause(0.5, 1.2)
    await page.keyboard.press("Enter")
    await page.wait_for_load_state("domcontentloaded")
    await pause(4, 6)
    tiles: list[dict] = []
    for pg in range(1, max_pages + 1):
        info = await page.evaluate(_STATE_JS)
        reason = blocked_reason(info)
        if reason:
            raise Blocked(f"{reason} ({info['url'][:120]})")
        tiles += [t | {"page": pg} for t in await page.evaluate(_SEARCH_JS)]
        nxt = page.locator("a.s-pagination-next")
        if len(pick_organic(tiles, n)) >= n or not await nxt.count():
            break
        await nxt.first.click()
        await page.wait_for_load_state("domcontentloaded")
        await pause(4, 7)
    return {"phrase": phrase, "url": page.url, "searched_at": datetime.now().isoformat(timespec="seconds"),
            "organic": pick_organic(tiles, n), "tiles": tiles}


# ── product page ───────────────────────────────────────────────────────────

_PRODUCT_JS = """() => {
  const q = s => document.querySelector(s), tx = s => ((q(s) || {}).innerText || '').trim();
  const meta = n => ((q(`meta[name="${n}"]`) || {}).content || '');
  const specs = [];
  for (const r of document.querySelectorAll('#productOverview_feature_div tr, #prodDetails tr, #productDetails_techSpec_section_1 tr, #productDetails_detailBullets_sections1 tr')) {
    const k = r.querySelector('th') || r.querySelector('td'), v = r.querySelector('td:last-child');
    if (k && v && k !== v) specs.push([k.innerText, v.innerText]);
  }
  for (const li of document.querySelectorAll('#detailBullets_feature_div li')) {
    const s = li.querySelectorAll('span.a-list-item > span');
    if (s.length >= 2) specs.push([s[0].innerText, s[1].innerText]);
  }
  const media = [...document.scripts].map(s => s.textContent).find(s => s.includes("'colorImages'")) || '';
  return {url: location.href, title: tx('#productTitle'), brand: tx('#bylineInfo'),
    price: ((q('#corePrice_feature_div .a-offscreen') || q('#corePriceDisplay_desktop_feature_div .a-offscreen') || {}).textContent || '').trim(),
    points: [...document.querySelectorAll('#feature-bullets li')].map(l => l.innerText.trim()).filter(Boolean),
    description: tx('#productDescription'), aplus: tx('#aplus'), important: tx('#important-information'),
    rating: (q('#acrPopover') || {}).title || '', reviews: tx('#acrCustomerReviewText'),
    bought: tx('#social-proofing-faceout-title-tk_bought'), specs,
    breadcrumbs: [...document.querySelectorAll('#wayfinding-breadcrumbs_feature_div a')].map(a => a.innerText.trim()),
    meta: {title: meta('title'), description: meta('description'), canonical: (q('link[rel="canonical"]') || {}).href || ''},
    media_script: media,
    qa: [...document.querySelectorAll('[id^="question-"]')].map(e => e.innerText.trim()).slice(0, 20)}}"""

_REVIEWS_JS = """() => [...document.querySelectorAll('[data-hook="review"]')].map(r => {
  const t = s => ((r.querySelector(s) || {}).innerText || '').trim();
  return {id: r.id, stars: t('[data-hook$="review-star-rating"]'), title: t('[data-hook="review-title"]'),
    author: t('.a-profile-name'), date: t('[data-hook="review-date"]'), verified: !!r.querySelector('[data-hook="avp-badge"]'),
    helpful: t('[data-hook="helpful-vote-statement"]'), text: t('[data-hook="review-body"]')}})"""


def _num(s: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s or "")
    return float(m.group().replace(",", "")) if m else None


def units_sold(text: str) -> int | None:
    """'1K+ bought in past month' -> 1000 (a lower bound; Amazon shows no real sales count)."""
    m = re.search(r"([\d.,]+)\s*([KM]?)\+?\s*bought", text or "", re.I)
    if not m:
        return None
    return int(float(m.group(1).replace(",", "")) * {"": 1, "K": 1000, "M": 1000000}[m.group(2).upper()])


def _js_json(script: str, key: str) -> list:
    """The list in ``'<key>': A.$.parseJSON('[...]')`` (or a literal ``'<key>': [...]``)."""
    m = re.search(rf"'{key}'\s*:\s*(?:\{{\s*'initial'\s*:\s*)?A\.\$\.parseJSON\('((?:[^'\\]|\\.)*)'\)", script)
    try:
        if m:
            # undo the JS string literal's own escapes (\\ \' \"); JSON's escapes stay
            return json.loads(re.sub(r"\\([\\'\"])", r"\1", m.group(1)))
        m = re.search(rf"'{key}'\s*:\s*\{{\s*'initial'\s*:\s*(\[.*?\])\s*\}}", script, re.S)
        return json.loads(m.group(1)) if m else []
    except ValueError:
        return []


def media_urls(script: str) -> tuple[list[str], list[dict]]:
    """Hi-res gallery images and the product's own videos from the image block script."""
    images = [i.get("hiRes") or i.get("large") for i in _js_json(script, "colorImages")]
    videos = [{"url": v["url"], "title": v.get("title", ""), "duration": v.get("durationSeconds")}
              for v in _js_json(script, "videos") if v.get("isVideo", True) and v.get("url")]
    return [u for u in images if u], videos


def clean_specs(pairs: list[list[str]]) -> dict:
    out = {}
    for k, v in pairs:
        k = re.sub(r"[\s\u200e\u200f:]+", " ", k).strip().lower().replace(" ", "_")
        v = re.sub(r"\s+", " ", v.replace("\u200e", "").replace("\u200f", "")).strip()
        if k and v and k != "customer_reviews" and k not in out:
            out[k] = v
    return out


def clean_review(r: dict) -> dict:
    title = re.sub(r"^\s*\d(\.\d)? out of 5 stars\s*", "", r["title"]).strip()
    helpful = r["helpful"]
    votes = 1 if helpful.lower().startswith("one person") else int(_num(helpful) or 0)
    return {"id": r["id"], "title": title, "rating": _num(r["stars"]), "author": r["author"],
            "date": r["date"], "verified": r["verified"], "helpful": votes, "text": r["text"]}


def normalize_product(raw: dict, asin: str) -> dict:
    """The page's raw strings -> the products.json record (without reviews and media files)."""
    specs = clean_specs(raw["specs"])
    specs.setdefault("asin", asin)
    canonical = raw["meta"]["canonical"]
    m = re.search(r"amazon\.com/([^/]+)/dp/", canonical)
    extra = "\n\n".join(re.sub(r"\n\s*\n+", "\n", x).strip() for x in (raw["aplus"], raw["important"]) if x.strip())
    qa = []
    for block in raw.get("qa") or []:
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        if len(lines) >= 2:
            qa.append({"q": re.sub(r"^Question:\s*", "", lines[0]), "a": re.sub(r"^Answer:\s*", "", lines[1])})
    rating = _num(raw["rating"])
    return {"asin": asin, "url": f"https://www.amazon.com/dp/{asin}", "title": raw["title"],
            "brand": re.sub(r"^(Visit the |Brand: )|( Store)$", "", raw["brand"]).strip(), "price": raw["price"],
            "points": raw["points"], "description": raw["description"],
            "rating": str(rating) if rating is not None else "", "reviews": int(_num(raw["reviews"]) or 0),
            "units_sold": units_sold(raw["bought"]), "units_sold_text": raw["bought"], "specs": specs,
            "extra": extra, "q_a": qa,
            "meta": {"title": raw["meta"]["title"], "description": raw["meta"]["description"], "canonical": canonical,
                     "url_keywords": [w for w in re.split(r"[-_]+", urllib.parse.unquote(m.group(1))) if w]
                                     if m else [],
                     "breadcrumbs": raw["breadcrumbs"], "item_type": specs.get("item_type_name", "")}}


async def collect_reviews(page, asin: str, star: str, n: int) -> list[dict]:
    """Most helpful ``n`` reviews of ``star`` (critical = 1-3, positive = 4-5): 10 per page load,
    then "Show 10 more reviews" (the pageNumber URL parameter is ignored)."""
    await goto(page, f"https://www.amazon.com/product-reviews/{asin}/?filterByStar={star}"
                     f"&sortBy=helpful&reviewerType=all_reviews")
    items = await page.evaluate(_REVIEWS_JS)
    while len(items) < n:
        more = page.locator('[data-hook="show-more-button"]')
        if not await more.count():
            break
        before = len(items)
        await more.first.click()
        for _ in range(30):
            await asyncio.sleep(0.5)
            items = await page.evaluate(_REVIEWS_JS)
            if len(items) > before:
                break
        else:
            break
        await pause(2, 4)
    seen, out = set(), []
    for r in items:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(clean_review(r))
    return out[:n]


async def download(page, url: str, target: Path) -> bool:
    if target.exists() and target.stat().st_size > 0:
        return True
    r = await page.context.request.get(url, timeout=120000)
    if not r.ok:
        return False
    target.write_bytes(await r.body())
    return True


async def crawl_product(page, asin: str, pdir: Path) -> dict:
    """Product page + critical/positive reviews + media files -> the product's record."""
    info = await goto(page, f"https://www.amazon.com/dp/{asin}")
    if "page not found" in info["title"].lower():
        raise Gone("product page not found")
    raw = await page.evaluate(_PRODUCT_JS)
    if not raw["title"]:
        raise RuntimeError("no product title on the page")
    rec = normalize_product(raw, asin)
    images, videos = media_urls(raw["media_script"])
    rec["neg_reviews"] = await collect_reviews(page, asin, "critical", NEG_REVIEWS) if rec["reviews"] else []
    rec["pos_reviews"] = await collect_reviews(page, asin, "positive", POS_REVIEWS) if rec["reviews"] else []
    mdir = pdir / "media" / asin
    mdir.mkdir(parents=True, exist_ok=True)
    saved_imgs, saved_vids, failed = [], [], []
    for i, u in enumerate(images, 1):
        ext = (re.search(r"\.(jpe?g|png|webp|gif)$", u, re.I) or [None, "jpg"])[1].lower()
        name = f"img_{i:02d}.{ext}"
        if await download(page, u, mdir / name):
            saved_imgs.append(f"media/{asin}/{name}")
        else:
            failed.append(u)
    for i, v in enumerate(videos, 1):
        name = f"vid_{i:02d}.mp4"
        if v["url"].split("?")[0].endswith(".mp4") and await download(page, v["url"], mdir / name):
            saved_vids.append(f"media/{asin}/{name}")
        else:
            failed.append(v["url"])
    rec["media"] = {"images": saved_imgs, "videos": saved_vids, "video_info": videos, "image_urls": images,
                    "failed": failed}
    rec["crawled_at"] = datetime.now().isoformat(timespec="seconds")
    return rec
