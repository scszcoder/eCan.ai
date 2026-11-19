"""The cloud Manager can read each store's latest saved store check (store_reports tool): folders
are matched to store records, failures stay failures, and no buyer details leave."""
import json
from datetime import date, timedelta

from agent.ec_skills.reports import store_report
from agent.ec_skills.reports import store_checks as R

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def _save(root, platform, folder, day, files):
    d = root / platform / folder / day
    d.mkdir(parents=True)
    for name, content in files.items():
        (d / name).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def _report(**kw):
    rep = {"store": "x", "checked_at": "now", "login_required": False, "orders": [], "customer_messages": [],
           "red_flags": []}
    rep.update(kw)
    return rep


STORES = [
    {"store_id": "shop_a_000", "name": "shop_a_0", "platform": "shopify",
     "store_urls": ["https://admin.shopify.com/store/shopa/orders"]},
    {"store_id": "shop_b_000", "name": "shop_b_0", "platform": "shopify",
     "store_urls": ["https://admin.shopify.com/store/shopb/"]},
    {"store_id": "eb_000", "name": "eb_0", "platform": "ebay", "store_urls": ["https://www.ebay.com/sh/ord"]},
    {"store_id": "amz_000", "name": "amz_0", "platform": "amazon", "store_urls": []},
]


def test_folders_match_stores_by_url_handle_name_or_being_the_only_one(tmp_path):
    _save(tmp_path, "shopify", "shopa", TODAY, {"report.json": _report()})
    _save(tmp_path, "shopify", "shopb", TODAY, {"report.json": _report()})
    _save(tmp_path, "ebay", "seller-77", TODAY, {"report.json": _report()})     # a seller id: only one there
    _save(tmp_path, "amazon", "amz_0", TODAY, {"report.json": _report()})
    found = R.match_folders(STORES, tmp_path)
    assert {k: v.name for k, v in found.items()} == {"shop_a_000": "shopa", "shop_b_000": "shopb",
                                                     "eb_000": "seller-77", "amz_000": "amz_0"}


def test_run_json_names_the_store_even_when_the_folder_does_not(tmp_path):
    _save(tmp_path, "shopify", "label-1", TODAY, {"report.json": _report(), "run.json": {"store_id": "shop_b_000"}})
    _save(tmp_path, "shopify", "label-2", TODAY, {"report.json": _report()})
    found = R.match_folders(STORES, tmp_path)
    assert found["shop_b_000"].name == "label-1" and "shop_a_000" not in found     # two stores: no guessing


def test_the_latest_report_gives_counts_and_red_flags_but_no_buyer_details(tmp_path):
    flags = [{"severity": "high", "type": "Payments not active", "detail": "needs business info"}]
    _save(tmp_path, "shopify", "shopa", YESTERDAY, {"report.json": _report()})
    _save(tmp_path, "shopify", "shopa", TODAY, {
        "report.json": _report(red_flags=flags, orders=[{"order_id": "1", "buyer": "Jane Roe", "action_needed": True}],
                               customer_messages=[{"buyer": "Jane Roe", "request": "where is it"}]),
        "upload_status.json": {"status": "pending"}})
    out = R.latest_reports(STORES, store_id="shop_a_000", root=tmp_path)
    assert len(out) == 1 and out[0]["checked"] is True
    r = out[0]["reports"][0]
    assert r["date"] == TODAY and r["complete"] and r["red_flags"] == flags and r["cloud_upload"] == "pending"
    assert r["orders_needing_action"] == 1 and r["messages_awaiting_reply"] == 1
    assert "Jane Roe" not in json.dumps(out)
    assert [x["date"] for x in R.latest_reports(STORES, "shop_a_000", days=5, root=tmp_path)[0]["reports"]] == [TODAY, YESTERDAY]


def test_a_failed_check_is_reported_as_not_complete_never_as_clean(tmp_path):
    _save(tmp_path, "amazon", "amz_0", TODAY, {"raw_result.json": {"status": "failed"},
                                               "report.md": "# x\n\n**Error:** the page did not load\n"})
    r = R.latest_reports(STORES, "amz_000", root=tmp_path)[0]["reports"][0]
    assert r["complete"] is False and r["title"] == "CHECK DID NOT COMPLETE" and r["error"] == "the page did not load"
    assert "red_flags" not in r


def test_a_store_with_no_saved_check_says_so(tmp_path):
    out = R.latest_reports(STORES, "eb_000", root=tmp_path)
    assert out == [{"store_id": "eb_000", "name": "eb_0", "platform": "ebay", "checked": False,
                    "note": "no saved store check for this store yet"}]


def test_a_store_check_records_which_store_it_was(tmp_path, monkeypatch):
    monkeypatch.setattr(store_report, "save_and_upload", lambda platform, store, files, date: {"files": files})
    monkeypatch.setattr(store_report, "report_dir", lambda *a: tmp_path)
    state = {"attributes": {"task_vars": {"store_id": "shop_a_000"}},
             "tool_result": {"triage": {"final": _report()}}}
    out = store_report.save_store_run_report(state, "shopify", "shopa")
    assert out["files"]["run.json"] == {"store_id": "shop_a_000"}
    assert "run.json" not in store_report.save_store_run_report({"tool_result": state["tool_result"]},
                                                                "shopify", "shopa")["files"]


def test_a_stores_ads_report_and_its_drafted_proposals_come_with_its_store_check(tmp_path):
    _save(tmp_path, "shopify", "shopa", TODAY, {"report.json": _report()})
    props = [{"id": "p1", "kind": "budget", "summary": "cut Brand budget 20%", "numbers": {"from": 10, "to": 8}}]
    _save(tmp_path, "google_ads", "shop_a_000", TODAY, {"report.json": {"proposals": props, "red_flags": []},
                                                         "run.json": {"store_id": "shop_a_000", "kind": "google_ads"}})
    _save(tmp_path, "google_ads", "other", TODAY, {"report.json": {"proposals": []}, "run.json": {"store_id": "shop_b_000"}})
    out = R.latest_reports(STORES, "shop_a_000", root=tmp_path)[0]
    assert out["checked"] and list(out["other_reports"]) == ["google_ads"]
    assert out["other_reports"]["google_ads"][0]["proposals"] == props


def test_save_store_report_files_a_failed_run_as_not_complete_with_its_reason(tmp_path, monkeypatch):
    from agent.ec_skills.reports import report_tools as T
    saved = {}
    monkeypatch.setattr(T, "save_and_upload", lambda kind, store, files: saved.update(kind=kind, store=store, files=files)
                        or {"folder": str(tmp_path), "upload": {"status": "uploaded"}})
    monkeypatch.setattr(T, "report_dir", lambda *a: tmp_path)
    out = T.save_store_report(None, {"store_id": "shop_a_000", "kind": "google_ads", "complete": False,
                                     "error": "Google showed a sign-in page"})
    assert out["success"] and out["title"] == "CHECK DID NOT COMPLETE" and saved["kind"] == "google_ads"
    assert "report.json" not in saved["files"] and "sign-in page" in saved["files"]["report.md"]
    assert saved["files"]["run.json"] == {"store_id": "shop_a_000", "kind": "google_ads"}
    ok = T.save_store_report(None, {"store_id": "shop_a_000", "kind": "google_ads", "complete": True,
                                    "report": {"proposals": [{"id": "p1"}]}, "report_md": "# fine"})
    assert ok["complete"] and saved["files"]["report.json"] == {"proposals": [{"id": "p1"}]}
    assert T.save_store_report(None, {"store_id": "", "kind": "google_ads"})["success"] is False
