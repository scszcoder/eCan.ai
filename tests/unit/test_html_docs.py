import json

from agent.ec_skills.chip_docs.crawl_executor import render_status
from agent.ec_skills.chip_docs.html_docs import BACKFILL_LOG, merge_html_urls, parts_to_backfill


def test_merge_matches_on_pdf_url_then_type_and_title():
    old = [{"type": "Data Sheets", "title": "DS", "url": "u1"},
           {"type": "Errata", "title": "E", "url": "old-u2"},
           {"type": "Application Notes", "title": "AN", "url": "u3"},
           {"type": "User Guides", "title": "UG", "url": "u4", "html_url": "keep"}]
    new = [{"type": "Data Sheets", "title": "DS renamed", "url": "u1", "html_url": "h1"},
           {"type": "Errata", "title": "E", "url": "new-u2", "html_url": "h2"},
           {"type": "Application Notes", "title": "AN", "url": "u3"},
           {"type": "User Guides", "title": "UG", "url": "u4", "html_url": "other"}]
    assert merge_html_urls(old, new) == 2
    assert [d.get("html_url") for d in old] == ["h1", "h2", None, "keep"]


def test_parts_to_backfill_skips_undone_logged_and_already_linked(tmp_path):
    def row(part, state):
        return {"part": part, "product page URL": f"https://x/{part}", "sub_plan": "s", "state": state,
                "worker": "", "docs": "", "updated": "", "attempts": "", "note": ""}
    rows = [row("A", "done"), row("B", "done"), row("C", "pending"), row("D", "done"), row("E", "done")]
    (tmp_path / "status.md").write_text(render_status(rows, {}, "V"), encoding="utf-8")
    docs = tmp_path / "raw" / "docs"
    docs.mkdir(parents=True)
    for p in "ABCD":
        (docs / f"{p}.json").write_text(json.dumps([{"url": "u"}]), encoding="utf-8")
    (docs / "B.json").write_text(json.dumps({"docs": [{"url": "u", "html_url": "h"}]}), encoding="utf-8")
    (tmp_path / "raw" / BACKFILL_LOG).write_text("D\n", encoding="utf-8")
    # A: needs it; B: already linked; C: not done; D: logged; E: no doc list
    assert parts_to_backfill(tmp_path) == [("A", "https://x/A")]


# ── crawl ──────────────────────────────────────────────────────────────────
import asyncio

import pytest

from agent.ec_skills.chip_docs import html_docs as hd

GUID = "GUID-0B644D8F-67E7-49E6-82C9-1B2B9ABE6A0D"
BASE = f"https://onlinedocs.microchip.com/oxy/{GUID}-en-US-19/"


def test_html_jobs_dedupes_shared_documents_and_lists_their_parts(tmp_path):
    docs = tmp_path / "raw" / "docs"
    docs.mkdir(parents=True)
    shared = {"type": "Reference Manual", "title": "AVR ISM", "url": "p", "html_url": BASE + "index.html"}
    (docs / "ATtiny25.json").write_text(json.dumps([shared, {"url": "q"}]), encoding="utf-8")
    (docs / "ATtiny45.json").write_text(json.dumps({"docs": [dict(shared, html_url=BASE)]}), encoding="utf-8")
    jobs = hd.html_jobs(tmp_path)
    assert list(jobs) == [GUID]
    assert jobs[GUID]["parts"] == ["ATtiny25", "ATtiny45"]


def test_html_jobs_take_only_onlinedocs_editions(tmp_path):
    # 2026-10-16: ST's HTML editions (www.st.com) are saved per part by download_docs_to_nas
    docs = tmp_path / "raw" / "docs"
    docs.mkdir(parents=True)
    (docs / "STM32F103C8.json").write_text(json.dumps(
        [{"url": "p", "html_url": "https://www.st.com/resource/en/application_note/an4879-usb.html"}]), encoding="utf-8")
    assert hd.html_jobs(tmp_path) == {}


def test_crawl_with_nothing_to_do_opens_no_browser(tmp_path, monkeypatch):
    import playwright.async_api as pw
    monkeypatch.setattr(pw, "async_playwright", lambda: (_ for _ in ()).throw(AssertionError("browser opened")))
    (tmp_path / "raw" / "docs").mkdir(parents=True)
    asyncio.run(hd.crawl(tmp_path, tmp_path / "profile"))


def test_doc_id_base_and_paths():
    assert hd.doc_id(BASE + "index.html") == GUID
    assert hd.doc_id("https://onlinedocs.microchip.com/g/" + GUID.lower()) == GUID
    assert hd.doc_base(BASE + "index.html") == BASE
    assert hd.in_doc(BASE + "GUID-1.html#sec?x", BASE) == BASE + "GUID-1.html"
    assert hd.in_doc(BASE + "img/a.png", BASE) is None
    assert hd.in_doc("https://onlinedocs.microchip.com/oxy/other/index.html", BASE) is None
    assert hd.rel_path(BASE, BASE) == "index.html"
    assert hd.rel_path(BASE + "sub/page", BASE) == "sub/page.html"
    assert hd.rel_path(BASE + "../../x.html", BASE) == "x.html"


class FakeResp:
    def __init__(self, status, body=b""):
        self.status, self.ok, self._body = status, status < 400, body

    async def body(self):
        return self._body


class FakePage:
    """pages: url -> (status, links, images). Redirects the landing URL like /g/ links do."""

    def __init__(self, pages, redirect=None):
        self.pages, self.url, self.visits = pages, "", []
        self.redirect = {"https://onlinedocs.microchip.com/g/" + GUID: BASE + "index.html", **(redirect or {})}
        self.body = {}
        page = self

        class Req:
            async def get(self, url, timeout=None):
                return FakeResp(200 if url in page.images() else 404, b"img")
        self.request = Req()

    def images(self):
        return {i for _, _, imgs in self.pages.values() for i in imgs}

    async def goto(self, url, timeout=None, wait_until=None):
        self.url = self.redirect.get(url, url)
        self.visits.append(self.url)
        return FakeResp(self.pages.get(self.url.split("#")[0], (404, [], []))[0])

    async def wait_for_load_state(self, state, timeout=None):
        pass

    async def evaluate(self, js):
        _, links, imgs = self.pages[self.url.split("#")[0]]
        return {"links": links, "images": imgs, "title": self.url}

    async def content(self):
        return f"<html>{self.url}</html>"

    async def inner_text(self, selector):
        return self.body.get(self.url, "topic text")


def test_crawl_doc_follows_in_document_links_and_saves_pages_and_images(tmp_path):
    site = {
        BASE + "index.html": (200, [BASE + "a.html#x", BASE + "b.html", "https://www.microchip.com/"],
                              [BASE + "img/fig1.png", "https://cdn/x.png"]),
        BASE + "a.html": (200, [BASE + "index.html", BASE + "missing.html"], [BASE + "img/fig1.png"]),
        BASE + "b.html": (200, [], []),
    }
    page = FakePage(site, redirect={"https://onlinedocs.microchip.com/g/" + GUID: BASE + "index.html"})
    m = asyncio.run(hd.crawl_doc(page, {"url": "https://onlinedocs.microchip.com/g/" + GUID}, tmp_path))
    assert [p["file"] for p in m["pages"]] == ["index.html", "a.html", "b.html"]
    assert (tmp_path / "a.html").read_text(encoding="utf-8") == f"<html>{BASE}a.html</html>"
    assert (tmp_path / "img" / "fig1.png").read_bytes() == b"img"
    assert m["images"] == 1 and m["failed"] == [f"{BASE}missing.html: HTTP 404"] and not m["truncated"]
    assert json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["base"] == BASE


def test_crawl_doc_raises_when_the_site_is_down(tmp_path):
    page = FakePage({BASE + "index.html": (503, [], [])})
    with pytest.raises(hd.SiteUnavailable):
        asyncio.run(hd.crawl_doc(page, {"url": BASE + "index.html"}, tmp_path))


def test_crawl_doc_raises_on_the_maintenance_page(tmp_path):
    # 2026-10-13: served with status 200 once the 503s stopped
    page = FakePage({BASE + "index.html": (200, [], [])})
    page.body[BASE + "index.html"] = "404 | Microchip Technology The site is currently down for maintenance."
    with pytest.raises(hd.SiteUnavailable):
        asyncio.run(hd.crawl_doc(page, {"url": BASE + "index.html"}, tmp_path))
    assert not (tmp_path / "manifest.json").exists()


def test_crawl_doc_fails_a_missing_landing_page_and_lands_versioned_urls_via_g(tmp_path):
    # 2026-10-27: /pr/ and /oxy/<GUID>-en-US-<old ver>/ editions 404; /g/<GUID> redirects to the current one
    g = "https://onlinedocs.microchip.com/g/" + GUID
    for old in (f"https://onlinedocs.microchip.com/pr/{GUID}-en-US-3/index.html", BASE + "index.html"):
        page = FakePage({BASE + "index.html": (200, [], [])}, redirect={g: BASE + "index.html"})
        m = asyncio.run(hd.crawl_doc(page, {"url": old}, tmp_path / "ok"))
        assert page.visits[0] == BASE + "index.html" and [p["file"] for p in m["pages"]] == ["index.html"]
    assert hd.landing_url("https://onlinedocs.microchip.com/downloads/x.html") == \
        "https://onlinedocs.microchip.com/downloads/x.html"
    with pytest.raises(RuntimeError, match="HTTP 404"):
        asyncio.run(hd.crawl_doc(FakePage({}), {"url": BASE + "gone.html"}, tmp_path / "gone"))
    assert not (tmp_path / "gone" / "manifest.json").exists()
