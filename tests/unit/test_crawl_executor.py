"""Chip-docs crawl Execute phase as code (2026-10-12: the LLM executor drifted and cost 100-660k tokens a round)."""
from datetime import datetime, timedelta, timezone

from agent.ec_skills.chip_docs import crawl_executor as ex

NOW = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)
PLAN = [{"part": f"P{i}", "url": f"https://x/P{i}", "sub_plan": "sp_a" if i < 5 else "sp_b",
         "category": "8-bit PIC MCU"} for i in range(1, 8)]


def _round(rows, workers, report=None, names=("W1", "W2"), sent=None, fail_send=(), now=NOW):
    sent = [] if sent is None else sent

    def send(w, batch):
        if w in fail_send:
            return False
        sent.append((w, batch))
        return True

    res = ex.run_round(rows, workers, PLAN, report, list(names), 3, "Microchip", "C:/chip_docs", "Coord", send, now)
    return res, sent


def _state(rows, part):
    return next(r for r in rows if r["part"] == part)


def test_first_round_builds_status_and_sends_one_batch_per_worker():
    rows, workers = [], {}
    res, sent = _round(rows, workers)
    assert len(rows) == 7
    assert [(w, [p["part"] for p in b["parts"]]) for w, b in sent] == [("W1", ["P1", "P2", "P3"]), ("W2", ["P4"])]
    assert sent[0][1]["parts"][0] == {"part": "P1", "url": "https://x/P1", "category": "8-bit PIC MCU"}
    assert workers["W2"]["batch"] == "sp_a-P4" and res["assigned"] == 4 and not res["all_done"]


def test_report_marks_done_and_failed_and_frees_worker():
    rows, workers = [], {}
    _, sent = _round(rows, workers, names=("W1",))
    report = {"type": "scrape_report", "batch_id": sent[0][1]["batch_id"], "parts": [
        {"part": "P1", "state": "done", "docs": 5},
        {"part": "P2", "state": "done", "docs": 0},  # done with 0 docs is a failure
        {"part": "P3", "state": "failed", "error": "timeout | page"}]}
    res, sent2 = _round(rows, workers, report=report, names=("W1",))
    assert _state(rows, "P1")["state"] == "done" and _state(rows, "P1")["docs"] == "5"
    assert _state(rows, "P2")["attempts"] == "1" and _state(rows, "P3")["note"] == "timeout / page"
    assert [p["part"] for p in sent2[0][1]["parts"]] == ["P4"]  # pending parts before failed ones
    assert res["done"] == 1


def test_failed_parts_are_retried_only_after_every_pending_part():
    rows, workers = [], {}
    _round(rows, workers, names=())
    for r in rows:
        r["state"] = "done"
    _state(rows, "P1").update(state="failed", attempts="2")
    _state(rows, "P6").update(state="pending")
    _, sent = _round(rows, workers, names=("W1",))
    assert [p["part"] for p in sent[0][1]["parts"]] == ["P6"]
    report = {"type": "scrape_report", "batch_id": sent[0][1]["batch_id"],
              "parts": [{"part": "P6", "state": "done", "docs": 4}]}
    _, sent = _round(rows, workers, report=report, names=("W1",), sent=sent)
    assert [p["part"] for p in sent[-1][1]["parts"]] == ["P1"]  # third and last attempt


def test_aborted_runs_requeue_without_using_attempts():
    # 2026-10-12: an internet outage aborted every crawler run within a minute and
    # marked 203 parts failed after 2 "attempts" that never reached a page
    rows, workers = [], {}
    _, sent = _round(rows, workers, names=("W1",))
    for n in range(1, ex.MAX_ABORTS + 1):
        report = {"type": "scrape_report", "batch_id": sent[-1][1]["batch_id"], "parts": [
            {"part": p["part"], "state": "failed", "docs": 0, "error": "crawler run aborted before reporting"}
            for p in sent[-1][1]["parts"]]}
        _round(rows, workers, report=report, names=("W1",), sent=sent)
        if n < ex.MAX_ABORTS:
            assert _state(rows, "P1")["state"] == "assigned" and _state(rows, "P1")["attempts"] == ""
            assert _state(rows, "P1")["note"] == f"aborted x{n}"
    assert _state(rows, "P1")["state"] == "failed"


def test_duplicate_report_is_ignored():
    rows, workers = [], {}
    _, sent = _round(rows, workers, names=("W1",))
    report = {"type": "scrape_report", "batch_id": "sp_a-P99", "parts": [{"part": "P1", "state": "done", "docs": 3}]}
    res, _ = _round(rows, workers, report=report, names=("W1",))
    assert _state(rows, "P1")["state"] == "assigned" and "ignored" in res["summary"]


def test_failed_max_attempts_is_not_retried():
    rows, workers = [], {}
    _round(rows, workers, names=())
    for r in rows:
        r["state"], r["attempts"] = "done", "0"
    _state(rows, "P1").update(state="failed", attempts=str(ex.MAX_ATTEMPTS))
    res, sent = _round(rows, workers, names=("W1",))
    assert sent == [] and res["all_done"]


def test_stale_batch_and_drifted_rows_are_reclaimed():
    rows, workers = [], {}
    _round(rows, workers, names=("W1",))
    _state(rows, "P5").update(state="assigned", worker="W9")  # drift: no busy worker owns it
    later = NOW + timedelta(minutes=31)
    res, sent = _round(rows, workers, names=("W1",), now=later)
    assert "reclaimed" in res["summary"]
    assert [p["part"] for p in sent[0][1]["parts"]] == ["P1", "P2", "P3"]
    assert _state(rows, "P5")["state"] == "pending"


def test_failed_send_leaves_parts_pending():
    rows, workers = [], {}
    res, _ = _round(rows, workers, names=("W1",), fail_send=("W1",))
    assert res["assigned"] == 0 and workers["W1"]["state"] == "idle"


def test_hand_typed_report_with_stray_escapes_is_read():
    # 2026-10-12: a worker wrote `{\"part"` mid-report; json.loads failed and the report was dropped
    text = ('{"type":"scrape_report","batch_id":"sp_a-P1","parts":[{"part":"P1","state":"done","docs":4},'
            '{\\"part\\":\\"P2\\",\\"state\\":\\"done\\",\\"docs\\":5}]}')
    msg = ex.parse_message(text)
    assert [p["part"] for p in msg["parts"]] == ["P1", "P2"] and msg["parts"][1]["docs"] == 5
    assert ex.parse_message("plan complete") is None


def test_status_round_trips_through_markdown(tmp_path):
    rows, workers = [], {}
    _round(rows, workers)
    text = ex.render_status(rows, workers, "Microchip")
    rows2, workers2 = ex.parse_status(text)
    assert rows2 == rows and workers2 == workers


def test_reads_the_existing_seven_column_status_and_sub_plans(tmp_path):
    (tmp_path / "sp.md").write_text(
        "# x\n\n| # | part | product page URL | category |\n|---:|---|---|---|\n"
        "| 1 | PIC10F322 | https://x/pic10f322 | Products > MCUs > PIC10 |\n", encoding="utf-8")
    plan = ex.load_sub_plans(tmp_path)
    assert plan == [{"part": "PIC10F322", "url": "https://x/pic10f322", "sub_plan": "sp", "category": "PIC10"}]
    old = ("# Microchip crawl status\n\n| part | product page URL | sub_plan | state | worker | docs | updated |\n"
           "|---|---|---|---|---|---|---|\n| PIC10F322 | https://x | sp | done | W1 | 21 | t |\n\n"
           "## Workers\n| worker | state | batch id | assigned at |\n|---|---|---|---|\n| W1 | idle |  | t |\n")
    rows, workers = ex.parse_status(old)
    assert rows[0]["state"] == "done" and rows[0]["docs"] == "21" and rows[0]["attempts"] == ""
    assert workers == {"W1": {"state": "idle", "batch": "", "at": "t"}}


def test_html_crawl_starts_once_while_running(tmp_path, monkeypatch):
    import threading
    from agent.ec_skills.chip_docs import html_docs

    release, calls = threading.Event(), []

    async def fake_crawl(root, profile):
        calls.append(root)
        release.wait(5)

    monkeypatch.setattr(html_docs, "crawl", fake_crawl)
    monkeypatch.setattr(ex, "_html_crawl", None)
    assert ex.start_html_crawl(tmp_path)
    assert not ex.start_html_crawl(tmp_path)  # still running
    release.set()
    ex._html_crawl.join(5)
    assert ex.start_html_crawl(tmp_path)  # finished: a later round resumes it
    ex._html_crawl.join(5)
    assert calls == [tmp_path, tmp_path]


def test_html_crawl_loop_can_start_chrome_under_the_apps_selector_policy(tmp_path, monkeypatch):
    # 2026-10-15: main.py sets WindowsSelectorEventLoopPolicy, whose loops can't start
    # subprocesses, so Playwright failed to launch Chrome (NotImplementedError).
    import asyncio
    import sys
    from agent.ec_skills.chip_docs import html_docs

    loops = []

    async def fake_crawl(root, profile):
        loops.append(type(asyncio.get_running_loop()))

    monkeypatch.setattr(html_docs, "crawl", fake_crawl)
    monkeypatch.setattr(ex, "_html_crawl", None)
    if sys.platform == "win32":
        old = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            assert ex.start_html_crawl(tmp_path)
            ex._html_crawl.join(5)
        finally:
            asyncio.set_event_loop_policy(old)
        assert loops == [asyncio.ProactorEventLoop]
    else:
        assert ex.start_html_crawl(tmp_path)
        ex._html_crawl.join(5)
        assert len(loops) == 1
