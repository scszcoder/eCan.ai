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


def test_write_table_waits_for_a_reader_holding_the_file(tmp_path, monkeypatch):
    # 2026-10-29: a status read outside the lock made the replace fail with WinError 5 and a
    # crawled product was counted as failed
    f = tmp_path / "status.md"
    real, calls = Path.replace, []

    def busy_twice(self, target):
        calls.append(target)
        if len(calls) <= 2:
            raise PermissionError(5, "Access is denied")
        return real(self, target)
    monkeypatch.setattr(Path, "replace", busy_twice)
    store.write_table(f, store.PRODUCT_COLS, [{"rank": 1, "asin": "A1", "state": "done"}], "p")
    assert len(calls) == 3 and store.read_table(f, store.PRODUCT_COLS)[0]["state"] == "done"


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
    uploads.clear()
    store.mirror_to_nas(pdir, ("texts",), refresh=True)      # rewritten in place: same size, still sent
    assert uploads == ["products/garden_hose_reel/texts/products.json"]


def search_file(f: Path, phrase: str, tiles: list[tuple[str, bool]]) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"phrase": phrase, "searched_at": "t",
                             "tiles": [{"asin": a, "sponsored": ad, "title": f"t {a}"} for a, ad in tiles]}),
                 encoding="utf-8")


def test_rank_comparison_of_a_seed_and_its_related_phrases(tmp_path):
    pdir = tmp_path / "garden_hose_reel"
    search_file(pdir / "raw" / "search.json", "garden hose reel",
                [("A1", True), ("A2", False), ("A1", False), ("", False), ("A3", False)])
    store.write_related(pdir, ["retractable hose reel", "hose reel cart"])     # the cart one not searched yet
    search_file(pdir / "raw" / "related" / "retractable_hose_reel.json", "retractable hose reel",
                [("A3", False), ("A2", True), ("A4", False), ("A2", False)])
    out = store.rank_comparison(pdir)
    assert out == pdir / "texts" / "rank_comparison.json"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert [p["phrase"] for p in data["phrases"]] == ["garden hose reel", "retractable hose reel"]
    assert [p["organic_results"] for p in data["phrases"]] == [3, 3]
    by = {p["asin"]: p for p in data["products"]}
    assert by["A2"]["ranks"] == {"garden hose reel": {"organic": 1, "ad": False},
                                 "retractable hose reel": {"organic": 3, "ad": True}}
    assert by["A1"]["ranks"]["garden hose reel"] == {"organic": 2, "ad": True}   # ad first, organic later
    assert [p["asin"] for p in data["products"]] == ["A2", "A3", "A1", "A4"]   # 2 phrases first, then best rank
    csv_lines = (pdir / "texts" / "rank_comparison.csv").read_text(encoding="utf-8-sig").splitlines()
    assert csv_lines[0] == "asin,title,phrases_ranked,best_rank,garden hose reel,retractable hose reel"
    assert csv_lines[1] == "A2,t A2,2,1,1,3+ad"
    assert csv_lines[4] == "A4,t A4,1,2,,2"


def test_pick_related_prefers_phrases_from_both_sources_and_drops_duplicates():
    suggestions = ["garden hose reel", "garden hose reel wall mount", "Garden Hose Reels Retractable",
                   "garden hose reel cart", "garden hose", "reel garden hose wall mount"]
    related = ["garden hose holder", "garden hose reels cart", "garden hose reel retractable", "hose reel box"]
    assert store.pick_related("garden hose reel", suggestions, related, n=10) == [
        "garden hose reels retractable", "garden hose reel cart",   # suggested and linked (plural ignored)
        "garden hose reel wall mount",              # then suggestion order
        "garden hose holder", "hose reel box"]      # then related; seed, broader and reordered ones dropped
    assert len(store.pick_related("garden hose reel", suggestions, related, n=2)) == 2


def test_related_phrases_retry_then_fail(tmp_path):
    store.write_related(tmp_path, ["a b", "c d"])
    assert store.next_related(tmp_path)["phrase"] == "a b"
    for _ in range(store.MAX_ATTEMPTS):
        store.finish_related(tmp_path, "a_b", "failed", note="x")
    store.finish_related(tmp_path, "c_d", "done", organic=48)
    rows = store.read_table(store.related_path(tmp_path), store.RELATED_COLS)
    assert [(r["state"], r["attempts"], r["organic"]) for r in rows] == [("failed", "3", ""), ("done", "0", "48")]
    assert store.next_related(tmp_path) is None


def test_reuse_copies_a_recent_crawl_with_its_media(tmp_path):
    from datetime import datetime, timedelta
    old, new, here = tmp_path / "hose_reel_cart", tmp_path / "garden_hose_reel", tmp_path / "wall_hose_reel"
    for d, days in ((old, 9), (new, 1)):
        (d / "raw").mkdir(parents=True)
        (d / "media" / "A1").mkdir(parents=True)
        (d / "media" / "A1" / "img_01.jpg").write_bytes(d.name.encode())
        at = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        (d / "raw" / "A1.json").write_text(json.dumps({"asin": "A1", "crawled_at": at}), encoding="utf-8")
    rec = store.reuse_product(tmp_path, here, "A1")
    assert rec["reused_from"] == "garden_hose_reel"
    assert (here / "media" / "A1" / "img_01.jpg").read_bytes() == b"garden_hose_reel"
    assert store.reuse_product(tmp_path, here, "A2") is None
    assert store.reuse_product(tmp_path, here, "A1", max_age_days=0.5) is None      # both too old


def test_video_topups_pick_the_most_reviewed(tmp_path):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2", "A3", "A4"])
    for asin, reviews, saved, listed in (("A1", 50, 1, 4), ("A2", 900, 1, 1), ("A3", 300, 3, 5), ("A4", 120, 1, 2)):
        rec = {"asin": asin, "reviews": reviews,
               "media": {"videos": [f"v{i}" for i in range(saved)], "video_info": [{}] * listed}}
        (pdir / "raw" / f"{asin}.json").write_text(json.dumps(rec), encoding="utf-8")
        store.finish(pdir, asin, "done")
    # top 3: A2 (only 1 video exists), A3 (has 3), A4 (1 of 2) -> only A4 needs more; A1 isn't a top seller
    assert store.video_topups(pdir, 3, 3) == ["A4"]


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


def test_crawl_product_negatives_from_one_star_up_and_one_video_then_more(tmp_path, monkeypatch):
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

    rec = asyncio.run(amazon.crawl_product(Page(), "A1", tmp_path))
    assert asked == [("one_star", 20), ("two_star", 8), ("three_star", 3), ("positive", 10)]
    assert [r["rating"] for r in rec["neg_reviews"]] == ["one_star"] * 12 + ["two_star"] * 5 + ["three_star"] * 3
    assert len(rec["pos_reviews"]) == 10 and rec["parent_asin"] == "B0PARENT01"
    assert rec["media"]["videos"] == ["media/A1/vid_01.mp4"]          # one when crawled
    assert len(rec["media"]["video_info"]) == 4                       # the rest stay listed
    assert asyncio.run(amazon.add_videos(Page(), tmp_path, rec, amazon.TOP_VIDEOS)) == 2   # a top seller: 3
    assert rec["media"]["videos"] == [f"media/A1/vid_0{i}.mp4" for i in (1, 2, 3)]
    assert sorted(p.name for p in (tmp_path / "media" / "A1").glob("vid_*")) == ["vid_01.mp4", "vid_02.mp4",
                                                                                "vid_03.mp4"]
    assert asyncio.run(amazon.add_videos(Page(), tmp_path, rec, amazon.TOP_VIDEOS)) == 0


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
    monkeypatch.setattr(store, "SEARCH_GAP_S", 0)


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


def test_worker_pass_reuses_a_recent_crawl(tmp_path, monkeypatch, fast):
    from datetime import datetime
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1"])
    (tmp_path / "other" / "raw").mkdir(parents=True)
    (tmp_path / "other" / "raw" / "A1.json").write_text(json.dumps(
        {"asin": "A1", "neg_reviews": [], "pos_reviews": [], "media": {"images": [], "videos": []},
         "crawled_at": datetime.now().isoformat(timespec="seconds")}), encoding="utf-8")

    async def crawl(page, asin, pd):
        raise AssertionError("crawled again")
    monkeypatch.setattr(amazon, "crawl_product", crawl)
    assert asyncio.run(nodes.worker_pass(tmp_path, "w1", tmp_path / "prof"))["done"] == 1
    assert json.loads((pdir / "raw" / "A1.json").read_text(encoding="utf-8"))["reused_from"] == "other"
    assert "reused from other" in store.read_table(store.status_path(pdir), store.PRODUCT_COLS)[0]["note"]


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


def fake_nas(monkeypatch) -> dict:
    """An in-memory NAS: {folder: {name: size}}."""
    remote: dict[str, dict] = {}

    def nas_list(folder, relative_to_base=True):
        if folder not in remote:
            raise FileNotFoundError(folder)
        return [{"name": n, "size": s} for n, s in remote[folder].items()]

    def nas_upload(local, rel, relative_to_base=True):
        folder, name = rel.rsplit("/", 1)
        remote.setdefault(folder, {})[name] = Path(local).stat().st_size
    import agent.ec_skills.nas as nas_pkg
    fake = types.SimpleNamespace(nas_list=nas_list, nas_upload=nas_upload)
    monkeypatch.setitem(sys.modules, "agent.ec_skills.nas.ugreen_nas", fake)
    monkeypatch.setattr(nas_pkg, "ugreen_nas", fake, raising=False)
    return remote


def test_coordinator_seed_flow(tmp_path, monkeypatch, fast):
    queue(tmp_path, "garden hose reel", "dog bed")
    remote = fake_nas(monkeypatch)
    calls, topped = [], []
    tiles = {"retractable garden hose reel": ["N1", "N2", "G1"], "garden hose reel cart": ["G1"]}

    async def search(page, phrase, max_pages=3):
        calls.append((phrase, max_pages))
        a = phrase[0].upper()
        return {"phrase": phrase, "searched_at": "t", "organic": [{"asin": f"{a}1"}, {"asin": f"{a}2"}],
                "tiles": [{"asin": x, "sponsored": False, "title": "x", "bought": "1K+ bought in past month"}
                          for x in tiles.get(phrase, [f"{a}1"])],
                "suggestions": ["garden hose reel cart"] if phrase == "garden hose reel" else [], "related": [],
                "ideas": ["retractable garden hose reel"] if phrase == "garden hose reel" else []}

    async def add_videos(page, pdir, rec, n):
        topped.append((rec["asin"], n))
        rec["media"]["videos"].append(f"media/{rec['asin']}/vid_02.mp4")
        return 1
    monkeypatch.setattr(amazon, "search", search)
    monkeypatch.setattr(amazon, "add_videos", add_videos)
    run = lambda: asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof"))
    pdir = tmp_path / "garden_hose_reel"

    assert run()["msg"] == "'garden hose reel': 2 products to crawl, 1 subcategories, 1 related phrases"
    assert states(pdir) == {"G1": "pending", "G2": "pending"}
    assert "related 'retractable garden hose reel' searched (3 organic)" in run()["msg"]   # the probe first
    assert "related 'garden hose reel cart' searched (1 organic)" in run()["msg"]
    assert calls[-1] == ("garden hose reel cart", 1)                       # rank only: first page
    assert run()["waiting"]                                                 # products still pending
    store.claim(tmp_path, "crawler1"), store.claim(tmp_path, "crawler2")
    assert "products to crawl" in run()["msg"]          # all handed out: dog bed searched meanwhile
    assert store.queue_rows(tmp_path)["dog_bed"]["state"] == "crawling"
    for a, reviews in (("G1", 10), ("G2", 99)):
        rec = {"asin": a, "reviews": reviews, "media": {"images": [], "videos": [f"media/{a}/vid_01.mp4"],
                                                         "video_info": [{"url": "1.mp4"}, {"url": "2.mp4"}],
                                                         "failed": []}}
        (pdir / "raw" / f"{a}.json").write_text(json.dumps(rec), encoding="utf-8")
        (pdir / "media" / a).mkdir(parents=True, exist_ok=True)
        (pdir / "media" / a / "vid_01.mp4").write_bytes(b"12345")
        store.finish(pdir, a, "done")
    msg = run()["msg"]
    assert msg.startswith("'garden hose reel' done: 2/2 products, 1 related phrases, 1/1 subcategories queued, NAS")
    assert sorted(topped) == [("G1", 3), ("G2", 3)]                         # both among the top 3
    merged = json.loads((pdir / "texts" / "products.json").read_text(encoding="utf-8"))
    assert [len(p["media"]["videos"]) for p in merged["products"]] == [2, 2]
    ranks = json.loads((pdir / "texts" / "rank_comparison.json").read_text(encoding="utf-8"))
    assert [p["phrase"] for p in ranks["phrases"]] == ["garden hose reel", "retractable garden hose reel",
                                                         "garden hose reel cart"]
    # the subcategory: 2 of its 3 top products are new -> queued after phrases.txt, a level-2 phrase
    node = store.tree_rows(tmp_path)["retractable_garden_hose_reel"]
    assert (node["state"], node["level"], node["parent"], node["new_share"], node["demand"]) == \
        ("queued", "2", "garden hose reel", "0.67", "3000")
    assert list(store.queue_rows(tmp_path)) == ["garden_hose_reel", "dog_bed", "retractable_garden_hose_reel"]
    # uploaded, verified, then the local media removed; its size counts against the budget
    assert remote["products/garden_hose_reel/media/G1"] == {"vid_01.mp4": 5}
    assert not (pdir / "media").exists()
    assert store.bytes_used(tmp_path) > 10
    assert run()["waiting"]                                                 # dog bed products pending


def test_a_subcategory_doesnt_expand_further(tmp_path, monkeypatch, fast):
    queue(tmp_path)
    store.add_tree_node(tmp_path, "retractable garden hose reel", "garden hose reel", level=2, state="queued",
                        demand=5)

    async def search(page, phrase, max_pages=3):
        return {"phrase": phrase, "searched_at": "t", "organic": [{"asin": "A1"}], "tiles": [],
                "suggestions": [], "related": [], "ideas": ["retractable garden hose reel 100 ft"]}
    monkeypatch.setattr(amazon, "search", search)
    r = asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert r["msg"] == "'retractable garden hose reel': 1 products to crawl, 0 subcategories, 0 related phrases"


def test_older_seeds_get_their_subcategories_searched_once(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1"])          # its search.json has no 'ideas' (older version)
    calls = []

    async def search(page, phrase, max_pages=3):
        calls.append((phrase, max_pages))
        return {"phrase": phrase, "searched_at": "t", "organic": [], "tiles": [], "suggestions": [],
                "related": [], "ideas": ["p q"]}
    monkeypatch.setattr(amazon, "search", search)
    run = lambda: asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert run()["msg"] == "'p': 1 subcategories to probe"
    assert calls == [("p", 1)]
    assert [(r["phrase"], r["kind"]) for r in store.read_table(store.related_path(pdir), store.RELATED_COLS)] == \
        [("p q", "sub")]
    assert "related 'p q' searched" in run()["msg"]
    assert calls == [("p", 1), ("p q", 1)]                                   # not searched again


def test_no_new_phrase_past_the_data_budget(tmp_path, monkeypatch, fast):
    queue(tmp_path, "a", "b")
    store.update_phrase(tmp_path, "a", state="done", bytes=600)
    monkeypatch.setattr(store, "BUDGET_BYTES", 500)
    r = asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert r["finished"] and r["msg"].startswith("data budget reached")
    assert store.queue_rows(tmp_path)["b"]["state"] == "pending"


def test_tables_written_before_a_column_was_added_still_read(tmp_path):
    f = tmp_path / "related.md"
    f.write_text("# x\n\n| phrase | slug | state | organic | attempts | updated | note |\n|---|---|---|---|---|---|---|\n"
                 "| a b | a_b | pending |  | 0 |  |  |\n", encoding="utf-8")
    assert store.read_table(f, store.RELATED_COLS) == [{"phrase": "a b", "slug": "a_b", "state": "pending",
                                                        "organic": "", "attempts": "0", "updated": "", "note": "",
                                                        "kind": ""}]


def test_queued_subcategories_follow_phrases_txt_biggest_demand_first(tmp_path):
    queue(tmp_path, "seed one", "seed two")
    for phrase, demand, state in (("small sub", 100, "queued"), ("big sub", 9000, "queued"),
                                  ("overlapping sub", 99999, "rank-only")):
        store.add_tree_node(tmp_path, phrase, "seed one", level=2, state=state, demand=demand)
    assert store.read_phrases(tmp_path) == ["seed one", "seed two", "big sub", "small sub"]
    assert store.phrase_level(tmp_path, "big_sub") == 2 and store.phrase_level(tmp_path, "seed_two") == 1


def test_coordinator_spaces_out_searches(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    monkeypatch.setattr(store, "SEARCH_GAP_S", 3600)
    store.mark_searched(tmp_path)
    r = asyncio.run(nodes.coordinator_pass(tmp_path, tmp_path / "prof", nas=False))
    assert r["waiting"] and r["msg"] == "'p' to search"


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


def test_a_long_pass_keeps_reporting_progress_to_the_app(monkeypatch):
    # 2026-10-29: the runner cancelled every crawler after 300 s without progress, i.e. after
    # its first pass of 3 products
    from utils.log_scope import _SCOPE
    from agent.ec_tasks.progress import seconds_since_progress
    monkeypatch.setattr(nodes, "HEARTBEAT_S", 0.02)
    seen = []

    async def long_pass():
        await asyncio.sleep(0.03)
        seen.append(seconds_since_progress("task_pr_test"))
        await asyncio.sleep(0.03)
        seen.append(seconds_since_progress("task_pr_test"))
        return "ok"
    token = _SCOPE.set({"task_id": "task_pr_test"})
    try:
        assert nodes._run(long_pass()) == "ok"
    finally:
        _SCOPE.reset(token)
    assert all(s is not None and s < 0.03 for s in seen)


def test_worker_main_retries_after_a_failed_pass(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    crawling(tmp_path, "p", ["A1"])

    @contextlib.asynccontextmanager
    async def no_chrome(profile):
        raise RuntimeError("Chrome exited at once")
        yield
    monkeypatch.setattr(amazon, "browser", no_chrome)
    r = nodes.worker_main({"prompt_refs": {"research_root": str(tmp_path), "worker": "crawler1"}})
    assert r["result"]["llm_result"]["all_done"] is False                 # the skill loop goes on
    assert "pass failed, retrying" in r["result"]["llm_result"]["summary"]
    assert states(tmp_path / "p") == {"A1": "pending"}                    # the product was given back


def test_a_page_script_that_never_returns_is_given_up(monkeypatch):
    # 2026-10-29: page.evaluate never returned on one product page and held crawler3 for good
    class Hung:
        async def evaluate(self, script):
            await asyncio.sleep(3600)
    monkeypatch.setattr(amazon, "JS_TIMEOUT_S", 0.05)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(amazon.js(Hung(), "() => 1"))


def test_worker_pass_gives_up_a_product_that_hangs_and_ends_the_pass(tmp_path, monkeypatch, fast):
    queue(tmp_path, "p")
    pdir = crawling(tmp_path, "p", ["A1", "A2"])

    async def crawl(page, asin, pd):
        await asyncio.sleep(3600)
    monkeypatch.setattr(amazon, "crawl_product", crawl)
    monkeypatch.setattr(nodes, "PRODUCT_TIMEOUT_S", 0.05)
    r = asyncio.run(nodes.worker_pass(tmp_path, "w1", tmp_path / "prof", limit=5))
    assert (r["done"], r["failed"]) == (0, 1)               # A2 is left for the next pass (fresh Chrome)
    rows = {x["asin"]: x for x in store.read_table(store.status_path(pdir), store.PRODUCT_COLS)}
    assert (rows["A1"]["state"], rows["A1"]["attempts"]) == ("pending", "1")
    assert rows["A1"]["note"].startswith("no result within")
    assert rows["A2"]["state"] == "pending"
