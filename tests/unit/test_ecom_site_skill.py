"""site_skill: recipes from an exploration, a guarded replay, checks from files, notes that keep what was proven."""
import asyncio
import json
import time

import pytest

from agent.ec_skills.ecom import site_skill as S

CAMPAIGNS = """Campaign report
"October 10, 2026 - November 8, 2026"
Campaign,Campaign type,Impr.,Clicks,Cost,Conversions,Conv. value
Search A,Search,1200,200,120.00,3.00,250.00
"""
TERMS_7D = """Search terms report
"November 2, 2026 - November 8, 2026"
Search term,Match type,Campaign,Impr.,Clicks,Cost,Conversions
led sign,Phrase match,Search A,400,90,60.00,0.00
"""


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ECAN_ECOM_HOME", str(tmp_path / "ecom"))
    return tmp_path


def explorer_answer():
    return json.dumps({"flow": "date, campaigns, conversions", "parts": [
        {"part": "campaigns", "url": "https://ads.google.com/aw/campaigns?ocid=1",
         "steps": [{"click": "Download"}, {"wait": 2}, {"click": ".csv"}], "findings": "download icon above the table"},
        {"part": "conversion_actions", "url": "https://ads.google.com/aw/conversions/all",
         "extract_js": "[...document.querySelectorAll('tr')].map(r => ({name: r.cells[0].innerText}))"},
        {"part": "search_terms", "steps": [], "findings": "menu moved; not found"},
        {"part": "not_a_part", "steps": [{"click": "x"}]}]})


def test_new_site_is_explored_whole_first_and_recipes_are_kept():
    plan = S.prepare("google_ads", "Last 30 days")
    assert plan["explore_first"] and "campaigns" in plan["explore_parts"]
    task = S.explore_task("google_ads", "Last 30 days", plan["explore_parts"])
    assert "Read-only" in task and "conversion_actions" in task
    saved = S.save_recipes("google_ads", {"final": explorer_answer(), "turns": 30}, plan["explore_parts"])
    assert saved["recipes"] == ["campaigns", "conversion_actions"]
    assert not S.prepare("google_ads", "Last 30 days")["explore_first"]       # the whole pass is done
    assert "menu moved" in S._xs("google_ads").findings("search_terms")


def test_explorer_without_a_model_answer_gives_its_try_back():
    parts = S.prepare("google_ads", "Last 30 days")["explore_parts"]
    S.save_recipes("google_ads", {"final": "", "error": "no reply"}, parts)
    assert S.prepare("google_ads", "Last 30 days")["explore_first"]


class FakePage:
    """Enough of PageSession for a replay: clicks by text, a download on '.csv'."""
    def __init__(self, folder, labels):
        self.folder, self.labels, self.clicked, self.went = folder, labels, [], []

    @classmethod
    async def open(cls, port, url, reuse=""):
        return cls.instance

    async def allow_downloads(self, folder):
        return True

    async def url(self):
        return "https://ads.google.com/aw/overview?ocid=777&__u=9&other=x"

    async def evaluate(self, js, timeout=30):
        if js == "document.title":
            return "Overview - Test account"
        if js.startswith("[...document"):
            return [{"name": "Purchase", "status": "Active", "optimization": "Primary"}]
        text = json.loads(js.split("})(", 1)[1].split(", ", 1)[0])
        return {"x": 1, "y": 1, "label": text} if text in self.labels else {"error": "no " + text}

    async def mouse_click(self, x, y):
        self.clicked.append(self.labels_last)

    async def navigate(self, url):
        self.went.append(url)
        return url

    async def press(self, key):
        pass

    async def close(self):
        pass


def test_replay_runs_recipes_guarded_and_checks_judge_the_files(home, monkeypatch):
    real_sleep = asyncio.sleep
    monkeypatch.setattr(S.asyncio, "sleep", lambda *_: real_sleep(0))
    dl = home / "dl"
    dl.mkdir()
    pack = S.load_site("google_ads")
    recipes = {"campaigns": {"part": "campaigns", "status": "candidate", "url": "https://ads.google.com/aw/campaigns?ocid=1",
                             "steps": [{"click": "Download"}, {"click": ".csv"}]},
               "search_terms": {"part": "search_terms", "status": "verified", "steps": [{"click": "Apply"}]},
               "conversion_actions": {"part": "conversion_actions", "status": "candidate",
                                      "extract_js": "[...document.querySelectorAll('tr')]"}}
    page = FakePage(str(dl), {"Download", ".csv", "Apply"})

    async def click(x, y):
        (dl / "Campaign report.csv").write_text(CAMPAIGNS, encoding="utf-8")
    page.mouse_click = click
    FakePage.instance = page
    since = time.time()
    out = asyncio.run(S._replay(pack, recipes, 1, str(dl), "Last 30 days", page_cls=FakePage))
    assert page.went[0].startswith("https://ads.google.com/aw/campaigns?") and "ocid=777" in page.went[0]
    assert out["campaigns"]["files"] == ["Campaign report.csv"]
    assert "refused" in out["search_terms"]["error"]                     # Apply is never pressed
    assert out["conversion_actions"]["rows"][0]["name"] == "Purchase"
    res = S.check("google_ads", "Last 30 days", str(dl), since, out, {})
    assert res["campaigns"][0] and res["date_range"][0] and res["conversion_actions"][0]
    assert not res["search_terms"][0] and "refused" in res["search_terms"][1]
    assert S.todo("google_ads", "Last 30 days", str(dl), since, out) == ["search_terms", "products"]


def test_wrong_period_fails_the_date_range(home):
    dl = home / "dl2"
    dl.mkdir()
    since = time.time()
    (dl / "Search terms.csv").write_text(TERMS_7D, encoding="utf-8")
    res = S.check("google_ads", "Last 30 days", str(dl), since, {}, {})
    assert res["search_terms"][0] and not res["date_range"][0] and "[7]" in res["date_range"][1]


def test_two_failed_checks_in_a_row_trigger_an_exploration():
    S.prepare("google_ads", "Last 30 days")
    S.save_recipes("google_ads", {"final": explorer_answer()}, [p["part"] for p in S.load_site("google_ads")["parts"]])
    bad = {"search_terms": (False, "no file arrived"), "campaigns": (True, "x.csv")}
    assert S.grade("google_ads", bad, {}) is None
    assert S.grade("google_ads", bad, {}) == "search_terms"


def test_a_failed_run_never_drops_verified_notes():
    old = "## How\n- Open Campaigns, click Download, pick .csv [verified]\n- Wait 6 s"
    worse = "## How\n- Click Reports"
    merged = S.merge_notes(old, worse, run_ok=False)
    assert "[verified]" in merged and "Click Reports" in merged and "unverified" in merged
    rewritten = S.merge_notes(old, worse, run_ok=True)
    assert "Kept verified entries" in rewritten and "[verified]" in rewritten


def test_learn_writes_notes_from_the_agent_steps():
    out = S.learn("google_ads", "1. clicked Download\n2. chose .csv", {"campaigns": (True, "ok")},
                  ask=lambda prompt: "## How\n- Download is the icon above the table [verified]")
    assert out["run_ok"] and "[verified]" in S.notes("google_ads")
    assert S.learn("google_ads", "", {})["skipped"]


def test_replay_thread_works_after_nest_asyncio_is_applied(monkeypatch):
    monkeypatch.setattr(asyncio, "run", lambda main, **_: asyncio.get_event_loop_policy().get_event_loop().run_until_complete(main))

    async def ok():
        await asyncio.sleep(0)
        return {"done": True}
    assert S._run(ok) == {"done": True}


def test_a_sign_in_page_is_found_before_anything_works_on_it(monkeypatch):
    from agent.ec_skills.explorer import page as P
    real_sleep = asyncio.sleep
    monkeypatch.setattr(S.asyncio, "sleep", lambda *_: real_sleep(0))
    monkeypatch.setattr(P, "browser_port", lambda store, profile: 9)

    class Landing(FakePage):
        landed = ""

        async def url(self):
            return self.landed
    page = Landing("", set())
    Landing.instance = page
    page.landed = "https://accounts.google.com/v3/signin/accountchooser?continue=x"
    assert S.signin_needed("google_ads", "p", page_cls=Landing) == {"needed": True, "host": "accounts.google.com"}
    page.landed = "https://ads.google.com/aw/overview?ocid=1"
    assert S.signin_needed("google_ads", "p", page_cls=Landing)["needed"] is False
    monkeypatch.setattr(P, "browser_port", lambda store, profile: 0)
    assert "not running" in S.signin_needed("google_ads", "p")["error"]
