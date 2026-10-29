"""Product research crawler: status files, parsing of Amazon page data, coordinator/crawler passes."""
import asyncio
import contextlib
import json
import sys
import types
from pathlib import Path

import pytest

from agent.ec_skills.product_research import amazon, nodes, store


def queue(root: Path, *phrases: str) -> None:
    (root / "_queue").mkdir(parents=True, exist_ok=True)
    (root / "_queue" / "phrases.txt").write_text("\n".join(phrases) + "\n", encoding="utf-8")


def crawling(root: Path, phrase: str, asins: list[str]) -> Path:
    pdir = root / store.slug(phrase)
    (pdir / "raw").mkdir(parents=True, exist_ok=True)
    (pdir / "raw" / "search.json").write_text(json.dumps({"phrase": phrase, "searched_at": "t"}), encoding="utf-8")
    store.write_products(pdir, phrase, [{"asin": a} for a in asins])
    store.update_phrase(root, store.slug(phrase), state="crawling", products=len(asins))
    return pdir


def states(pdir: Path) -> dict:
    return {r["asin"]: r["state"] for r in store.read_table(store.status_path(pdir), store.PRODUCT_COLS)}


# ── store ──────────────────────────────────────────────────────────────────

def test_slug_joins_words_with_underscores():
    assert store.slug("garden hose reel") == "garden_hose_reel"
    assert store.slug("  Garden  Hose, Reel! ") == "garden_hose_reel"


def test_read_phrases_skips_comments_end_and_duplicates(tmp_path):
    queue(tmp_path, "garden hose reel", "# note", "Garden  hose reel", "dog bed  # big", "END")
    assert store.read_phrases(tmp_path) == ["garden hose reel", "dog bed"]


def test_queue_finished_only_when_every_phrase_is_done_or_failed(tmp_path):
    queue(tmp_path, "a b", "c")
    assert not store.queue_finished(tmp_path)
    store.update_phrase(tmp_path, "a_b", state="done")
    store.update_phrase(tmp_path, "c", state="failed")
    assert store.queue_finished(tmp_path)
    assert store.queue_rows(tmp_path)["a_b"]["state"] == "done"


def test_claim_prefers_own_unfinished_then_pending_then_stale(tmp_path, monkeypatch):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2", "A3"])
    assert store.claim(tmp_path, "w1")[1]["asin"] == "A1"
    assert store.claim(tmp_path, "w2")[1]["asin"] == "A2"
    assert store.claim(tmp_path, "w1")[1]["asin"] == "A1"        # its own unfinished one again
    assert store.claim(tmp_path, "w3")[1]["asin"] == "A3"
    assert store.claim(tmp_path, "w4") is None                  # everything is fresh and assigned
    monkeypatch.setattr(store, "STALE_ASSIGNED_S", -1)
    assert store.claim(tmp_path, "w4")[1]["asin"] in ("A1", "A2", "A3")
    assert states(pdir) == {"A1": "assigned", "A2": "assigned", "A3": "assigned"}


def test_claim_ignores_phrases_not_crawling(tmp_path):
    queue(tmp_path, "p")
    crawling(tmp_path, "p", ["A1"])
    store.update_phrase(tmp_path, "p", state="done")
    assert store.claim(tmp_path, "w1") is None


def test_finish_retries_failures_until_max_attempts(tmp_path):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2"])
    for _ in range(store.MAX_ATTEMPTS - 1):
        assert store.finish(pdir, "A1", "failed", "boom")["state"] == "pending"
    assert store.finish(pdir, "A1", "failed", "boom")["state"] == "failed"
    assert store.finish(pdir, "A2", "released", "blocked")["attempts"] == "0"
    assert store.finish(pdir, "A2", "done")["state"] == "done"
    assert store.read_table(store.status_path(pdir), store.PRODUCT_COLS)[0]["note"] == "boom"


def test_lock_is_exclusive(tmp_path):
    f = tmp_path / "status.md"
    with store.lock(f):
        with pytest.raises(TimeoutError):
            with store.lock(f, timeout=0.3):
                pass
    with store.lock(f, timeout=0.3):   # released again
        pass


def test_merge_orders_by_rank_and_lists_failures(tmp_path):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2", "A3"])
    (pdir / "raw" / "A2.json").write_text(json.dumps({"asin": "A2", "title": "two"}), encoding="utf-8")
    store.finish(pdir, "A2", "done")
    for _ in range(store.MAX_ATTEMPTS):
        store.finish(pdir, "A1", "failed", "gone")
    out = store.merge(pdir)
    assert [(p["rank"], p["asin"]) for p in out["products"]] == [(1, "A1"), (2, "A2")]   # A3 still pending
    assert out["products"][0]["error"] == "gone" and out["products"][1]["title"] == "two"
    assert json.loads((pdir / "texts" / "products.json").read_text(encoding="utf-8"))["slug"] == "p"


def test_mirror_uploads_changed_files_and_reports_missing(tmp_path, monkeypatch):
    pdir = tmp_path / "garden_hose_reel"
    (pdir / "texts").mkdir(parents=True)
    (pdir / "media" / "A1").mkdir(parents=True)
    (pdir / "texts" / "products.json").write_text("{}", encoding="utf-8")
    (pdir / "media" / "A1" / "img_01.jpg").write_bytes(b"12345")
    (pdir / "raw").mkdir()
    (pdir / "raw" / "A1.json").write_text("{}", encoding="utf-8")       # raw/ stays local
    remote = {"products/garden_hose_reel/texts": {"products.json": 2}}
    uploads = []

    def nas_list(folder, relative_to_base=True):
        assert relative_to_base is False
        if folder not in remote:
            raise FileNotFoundError(folder)
        return [{"name": n, "size": s} for n, s in remote[folder].items()]

    def nas_upload(local, rel, relative_to_base=True):
        uploads.append(rel)
        folder, name = rel.rsplit("/", 1)
        if not name.endswith(".jpg"):          # pretend the image upload got lost
            remote.setdefault(folder, {})[name] = Path(local).stat().st_size

    import agent.ec_skills.nas as nas_pkg
    fake = types.SimpleNamespace(nas_list=nas_list, nas_upload=nas_upload)
    monkeypatch.setitem(sys.modules, "agent.ec_skills.nas.ugreen_nas", fake)
    monkeypatch.setattr(nas_pkg, "ugreen_nas", fake, raising=False)
    r = store.mirror_to_nas(pdir)
    assert uploads == ["products/garden_hose_reel/media/A1/img_01.jpg"]   # products.json already there
    assert r == {"files": 2, "uploaded": 1, "missing": ["media/A1/img_01.jpg"]}


# ── amazon page parsing ────────────────────────────────────────────────────

def test_pick_organic_skips_ads_and_repeats():
    tiles = [{"asin": "A1", "sponsored": True}, {"asin": "A2", "sponsored": False},
             {"asin": "", "sponsored": False}, {"asin": "A1", "sponsored": False},
             {"asin": "A2", "sponsored": False}, {"asin": "A3", "sponsored": False}]
    assert [t["asin"] for t in amazon.pick_organic(tiles, 2)] == ["A2", "A1"]


@pytest.mark.parametrize("text,n", [("1K+ bought in past month", 1000), ("300+ bought in past month", 300),
                                    ("1.5K+ bought in past month", 1500), ("2M+ bought in past month", 2000000),
                                    ("", None), ("Best seller", None)])
def test_units_sold(text, n):
    assert amazon.units_sold(text) == n


def test_blocked_reason():
    assert amazon.blocked_reason({"url": "https://www.amazon.com/ap/signin?x", "title": "Sign in"}) == "sign-in required"
    assert amazon.blocked_reason({"url": "https://www.amazon.com/errors/validateCaptcha", "title": ""}) == "captcha"
    assert amazon.blocked_reason({"url": "https://www.amazon.com/s", "title": "Sorry! Something went wrong!"}) \
        == "bot check page"
    assert amazon.blocked_reason({"url": "https://www.amazon.com/dp/A1", "title": "Amazon.com : x", "captcha": False}) is None


MEDIA_SCRIPT = """P.when('A').register("ImageBlockATF", function(A){ var data = {
 'colorImages': { 'initial': A.$.parseJSON('[{"hiRes":"https://m.media-amazon.com/images/I/71a._AC_SL1500_.jpg","alt":"22 3\\\\/4\\\\\\" wide","large":"https://m.media-amazon.com/images/I/41a._AC_.jpg"},{"hiRes":null,"large":"https://m.media-amazon.com/images/I/41b._AC_.png"}]')},
 'colorToAsin': {'initial': '{}'},
 'videos': A.$.parseJSON('[{"isVideo":true,"title":"It\\'s easy \\\\/ fast","url":"https://m.media-amazon.com/images/S/v/default.jobtemplate.mp4.480.mp4","durationSeconds":11},{"isVideo":true,"title":"no url"}]'),
 };});"""


def test_media_urls_from_image_block_script():
    images, videos = amazon.media_urls(MEDIA_SCRIPT)
    assert images == ["https://m.media-amazon.com/images/I/71a._AC_SL1500_.jpg",
                      "https://m.media-amazon.com/images/I/41b._AC_.png"]
    assert videos == [{"url": "https://m.media-amazon.com/images/S/v/default.jobtemplate.mp4.480.mp4",
                       "title": "It's easy / fast", "duration": 11}]
    assert amazon.media_urls("") == ([], [])
    literal = "'colorImages': { 'initial': [{\"hiRes\": \"https://x/1.jpg\"}] },"
    assert amazon.media_urls(literal)[0] == ["https://x/1.jpg"]


def test_clean_specs_and_review():
    specs = amazon.clean_specs([["Brand", "Giraffe Tools"], ["ASIN ‏ : ‎", "B081W9LGL2"],
                                ["Customer Reviews", "4.2 out of 5 stars var x = 1;"],
                                ["Best Sellers Rank", "#2,157 in Patio\n #2 in Garden Hose Reels"],
                                ["Brand", "duplicate"]])
    assert specs == {"brand": "Giraffe Tools", "asin": "B081W9LGL2",
                     "best_sellers_rank": "#2,157 in Patio #2 in Garden Hose Reels"}
    r = amazon.clean_review({"id": "R1", "stars": "3.0 out of 5 stars", "title": "3.0 out of 5 stars\n Not sturdy",
                             "author": "A", "date": "Reviewed in the United States on June 26, 2026", "verified": True,
                             "helpful": "15 people found this helpful", "text": "Broke."})
    assert (r["title"], r["rating"], r["helpful"]) == ("Not sturdy", 3.0, 15)
    assert amazon.clean_review({**r, "stars": "5 out of 5 stars", "title": "Great",
                                "helpful": "One person found this helpful"})["helpful"] == 1


def test_normalize_product():
    raw = {"title": "Hose Reel", "brand": "Visit the Giraffe Tools Store", "price": "$179.99",
           "points": ["a", "b"], "description": "", "aplus": "From the brand\n \n \nGiraffe", "important": "",
           "rating": "4.2 out of 5 stars", "reviews": "(10,939)", "bought": "1K+ bought in past month",
           "specs": [["Item Type Name", "garden-hose-reels"]], "breadcrumbs": ["Patio, Lawn & Garden", "Reels"],
           "meta": {"title": "Amazon.com : Hose Reel", "description": "d",
                    "canonical": "https://www.amazon.com/Giraffe-Retractable-180%C2%B0Swivel/dp/B081W9LGL2"},
           "qa": ["Question: Does it leak?\nAnswer: No."]}
    p = amazon.normalize_product(raw, "B081W9LGL2")
    assert (p["brand"], p["rating"], p["reviews"], p["units_sold"]) == ("Giraffe Tools", "4.2", 10939, 1000)
    assert p["specs"] == {"item_type_name": "garden-hose-reels", "asin": "B081W9LGL2"}
    assert p["extra"] == "From the brand\nGiraffe"
    assert p["q_a"] == [{"q": "Does it leak?", "a": "No."}]
    assert p["meta"]["url_keywords"] == ["Giraffe", "Retractable", "180°Swivel"]
    assert p["meta"]["item_type"] == "garden-hose-reels"


def test_crawl_product_negatives_from_one_star_up_and_three_videos(tmp_path, monkeypatch):
    four_videos = MEDIA_SCRIPT.replace('{"isVideo":true,"title":"no url"}', ",".join(
        f'{{"isVideo":true,"title":"v{i}","url":"https://m.media-amazon.com/v{i}.mp4"}}' for i in range(2, 5)))
    raw = {"title": "Hose Reel", "brand": "", "price": "", "points": [], "description": "", "aplus": "",
           "important": "", "rating": "4.2 out of 5 stars", "reviews": "(500)", "bought": "", "specs": [],
           "breadcrumbs": [], "meta": {"title": "", "description": "", "canonical": ""}, "qa": [],
           "media_script": four_videos, "parent_asin": "B0PARENT01"}

    class Page:
        async def evaluate(self, js):
            return raw

    async def goto(page, url):
        return {"url": url, "title": "Amazon.com : Hose Reel"}
    have = {"one_star": 12, "two_star": 5, "three_star": 30, "positive": 40}
    asked = []

    async def collect(page, asin, star, n):
        asked.append((star, n))
        return [{"id": f"{star}{i}", "rating": star} for i in range(min(n, have[star]))]

    async def download(page, url, target):
        target.write_bytes(b"x")
        return True
    monkeypatch.setattr(amazon, "goto", goto)
    monkeypatch.setattr(amazon, "collect_reviews", collect)
    monkeypatch.setattr(amazon, "download", download)
    (tmp_path / "media" / "A1").mkdir(parents=True)
    (tmp_path / "media" / "A1" / "vid_05.mp4").write_bytes(b"old")

    rec = asyncio.run(amazon.crawl_product(Page(), "A1", tmp_path))
    assert asked == [("one_star", 20), ("two_star", 8), ("three_star", 3), ("positive", 10)]
    assert [r["rating"] for r in rec["neg_reviews"]] == ["one_star"] * 12 + ["two_star"] * 5 + ["three_star"] * 3
    assert len(rec["pos_reviews"]) == 10 and rec["parent_asin"] == "B0PARENT01"
    assert rec["media"]["videos"] == [f"media/A1/vid_0{i}.mp4" for i in (1, 2, 3)]
    assert len(rec["media"]["video_info"]) == 4                       # the 4th stays listed, not downloaded
    assert sorted(p.name for p in (tmp_path / "media" / "A1").glob("vid_*")) == ["vid_01.mp4", "vid_02.mp4",
                                                                                "vid_03.mp4"]


# ── passes ─────────────────────────────────────────────────────────────────

class FakePage:
    url = "https://www.amazon.com/dp/X"


@contextlib.asynccontextmanager
async def fake_browser(profile):
    yield FakePage()


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setattr(amazon, "browser", fake_browser)

    async def no_pause(lo, hi):
        pass
    monkeypatch.setattr(amazon, "pause", no_pause)
    monkeypatch.setattr(nodes, "IDLE_S", 0)


def test_worker_pass_saves_and_fails_products(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2", "A3"])

    async def crawl(page, asin, pd):
        if asin == "A2":
            raise RuntimeError("no product title on the page")
        return {"asin": asin, "neg_reviews": [1] * 20, "pos_reviews": [1] * 10,
                "media": {"images": ["x"], "videos": []}}
    monkeypatch.setattr(amazon, "crawl_product", crawl)
    r = asyncio.run(nodes.worker_pass(tmp_path, "w1", tmp_path / "prof", limit=5))
    assert (r["done"], r["failed"], r["idle"], r["blocked"]) == (2, 1, False, None)
    assert states(pdir) == {"A1": "done", "A2": "pending", "A3": "done"}   # A2 retried later
    assert json.loads((pdir / "raw" / "A3.json").read_text(encoding="utf-8"))["asin"] == "A3"


def test_worker_pass_stops_everyone_when_blocked(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2"])

    async def crawl(page, asin, pd):
        raise amazon.Blocked("captcha (x)")
    monkeypatch.setattr(amazon, "crawl_product", crawl)
    r = asyncio.run(nodes.worker_pass(tmp_path, "w1", tmp_path / "prof"))
    assert r["blocked"] == "captcha (x)"
    assert states(pdir) == {"A1": "pending", "A2": "pending"}
    assert "captcha" in store.blocked(tmp_path)
    r = asyncio.run(nodes.worker_pass(tmp_path, "w2", tmp_path / "prof"))
    assert r["blocked"] and r["done"] == 0


def test_worker_pass_gives_the_product_back_when_chrome_fails(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1"])

    @contextlib.asynccontextmanager
    async def broken(profile):
        raise RuntimeError("Chrome exited at once")
        yield
    monkeypatch.setattr(amazon, "browser", broken)
    with pytest.raises(RuntimeError):
        asyncio.run(nodes.worker_pass(tmp_path, "w1", tmp_path / "prof"))
    assert states(pdir) == {"A1": "pending"}


def test_coordinator_searches_waits_then_merges(tmp_path, monkeypatch, fast):
    queue(tmp_path, "garden hose reel", "dog bed")

    async def search(page, phrase):
        return {"phrase": phrase, "searched_at": "t", "organic": [{"asin": "A1"}, {"asin": "A2"}], "tiles": []}
    monkeypatch.setattr(amazon, "search", search)
    run = lambda: asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert "2 products" in run()["msg"]
    pdir = tmp_path / "garden_hose_reel"
    assert states(pdir) == {"A1": "pending", "A2": "pending"}
    assert run()["waiting"]
    for a in ("A1", "A2"):
        (pdir / "raw" / f"{a}.json").write_text(json.dumps({"asin": a}), encoding="utf-8")
        store.finish(pdir, a, "done")
    r = run()
    assert "done: 2/2 products" in r["msg"]
    assert store.queue_rows(tmp_path)["garden_hose_reel"]["state"] == "done"
    assert len(json.loads((pdir / "texts" / "products.json").read_text(encoding="utf-8"))["products"]) == 2
    assert "products to crawl" in run()["msg"]                 # next phrase: dog bed searched
    assert store.queue_rows(tmp_path)["dog_bed"]["state"] == "crawling"


def test_coordinator_blocked_search_sets_the_flag(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")

    async def search(page, phrase):
        raise amazon.Blocked("bot check page (x)")
    monkeypatch.setattr(amazon, "search", search)
    r = asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert r["blocked"] and store.blocked(tmp_path)
    assert store.queue_rows(tmp_path)["p"]["state"] == "pending"


def test_worker_main_ends_when_the_queue_is_finished(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    state = {"prompt_refs": {"research_root": str(tmp_path), "worker": "crawler2"}}
    r = nodes.worker_main(state)["result"]["llm_result"]
    assert r["all_done"] is False                      # phrase still pending: wait for the coordinator
    store.update_phrase(tmp_path, "p", state="done")
    r = nodes.worker_main(state)["result"]["llm_result"]
    assert r["all_done"] is True and "queue finished" in r["summary"]
