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
