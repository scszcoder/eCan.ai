"""The e-commerce L1 layer: storage, KB layering, report parsing, the A10 Google Ads rules,
tracking / feed / readiness audits and the upload files. All numbers come from code."""
from datetime import date

import pytest

from agent.ec_skills.ecom import bulk_files, kb, metrics, prepare, records, reports, rules, schemas
from agent.ec_skills.ecom.store import Store

TODAY = date(2026, 11, 9)

GADS_SEARCH_TERMS = """Search terms report
"November 1, 2026 - November 9, 2026"
Search term,Match type,Added/Excluded,Campaign,Ad group,Day,Currency code,Impr.,Clicks,Cost,Conversions,Conv. value
free widget pattern,Broad match,None,GADS-S1-SHOP-hero-roas,All,2026-11-05,USD,400,12,6.50,0.00,0.00
blue widget large,Phrase match,None,GADS-S1-SHOP-hero-roas,All,2026-11-06,USD,900,40,"1,02.00",0.00,0.00
widget gift set,Phrase match,None,GADS-S1-SHOP-hero-roas,All,2026-11-07,USD,300,20,18.00,3.00,150.00
cheap thing,Exact match,None,GADS-S1-SHOP-hero-roas,All,2026-11-07,USD,10,1,0.40,--,--
Total: Search terms,,,,,,,1610,73,126.90,3.00,150.00
"""


@pytest.fixture
def store(tmp_path):
    return Store("t1", path=tmp_path / "ec_data.db")


def _write(tmp_path, name, text, encoding="utf-8"):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return p


def test_schemas_validate_the_spec_shapes():
    ok = {"task_id": "t", "skill": "x", "requested_by": "manager", "store_id": "s", "platform": "shopify",
          "inputs": {}, "approval_level_max": 1}
    assert schemas.validate("TaskEnvelope", ok) == []
    assert schemas.validate("TaskEnvelope", {**ok, "platform": "myspace"})
    assert "SkillResult" in schemas.names()


def test_store_is_versioned_read_only_for_queries_and_idempotent(store):
    assert store.kb_put("store_profile", "s1", {"currency": "USD"}) == 1
    assert store.kb_put("store_profile", "s1", {"currency": "EUR"}) == 2
    assert store.kb_get("store_profile", "s1")["value"]["currency"] == "EUR"
    assert store.kb_get("store_profile", "s1", version=1)["value"]["currency"] == "USD"
    rows = [{"date": "2026-11-01", "campaign": "A", "cost": 5.0}, {"date": "2026-11-02", "campaign": "A", "cost": 7.0}]
    store.write_rows("gads_campaign_rows", rows, store_id="s1", source_file="a.csv")
    store.write_rows("gads_campaign_rows", rows[1:], store_id="s1", source_file="b.csv")   # same day again
    q = store.query("SELECT SUM(cost) FROM gads_campaign_rows WHERE _store_id=?", ["s1"])
    assert q["rows"][0][0] == 12.0
    for bad in ("DELETE FROM kb", "SELECT 1; DROP TABLE kb", "WITH x AS (SELECT 1) INSERT INTO kb VALUES (1,1,1,1,1,1)"):
        with pytest.raises(Exception):
            store.query(bad)


def test_kb_layers_instruction_over_learning_over_prior_and_core_is_owner_only(store):
    assert kb.resolve("thresholds.gads.zombie_clicks")["layer"] == "pack_prior"
    store.kb_put("learning", "L1", {"status": "validated", "scope": {"platform": "google_ads"},
                                    "applies_to": {"kb_key": "thresholds.gads.zombie_clicks", "value": 40}})
    store.kb_put("learning", "L2", {"status": "validated", "scope": {"store_id": "s1"},
                                    "applies_to": {"kb_key": "thresholds.gads.zombie_clicks", "value": 35}})
    assert kb.resolve("thresholds.gads.zombie_clicks", {"store_id": "s2", "platform": "google_ads"}, store)["value"] == 40
    r = kb.resolve("thresholds.gads.zombie_clicks", {"store_id": "s1", "platform": "google_ads"}, store)
    assert (r["value"], r["layer"], r["provenance_id"]) == (35, "learning_store", "L2")
    store.kb_put("user_instruction", "U1", {"status": "confirmed", "scope": {"store_id": "s1"},
                                            "kb_key": "thresholds.gads.zombie_clicks", "value": 60})
    assert kb.resolve("thresholds.gads.zombie_clicks", {"store_id": "s1"}, store)["layer"] == "user_instruction"
    assert kb.resolve("red_list")["layer"] == "immutable_core"
    with pytest.raises(PermissionError):
        kb.put_record(store, "core", "x", {"kb_key": "red_list", "value": []})


def _as_tsv(text):
    import csv
    import io
    lines = text.splitlines()
    body = ["\t".join(r) for r in csv.reader(io.StringIO("\n".join(lines[2:])))]
    return "\n".join(["Search terms report", lines[1].strip('"'), *body]) + "\n"


def test_google_ads_download_with_preamble_totals_and_utf16(tmp_path):
    for enc, text in (("utf-8", GADS_SEARCH_TERMS), ("utf-16", _as_tsv(GADS_SEARCH_TERMS))):
        out = reports.normalize(_write(tmp_path, f"st_{enc}.csv", text, enc))
        assert out["table"] == "gads_search_term_rows"
        assert out["detect"]["date_range"] == ["2026-11-01", "2026-11-09"]
        assert len(out["rows"]) == 4 and "skipped 1 total row(s)" in out["warnings"]
        by = {r["search_term"]: r for r in out["rows"]}
        assert by["blue widget large"]["cost"] == 102.0 and by["blue widget large"]["match_type"] == "phrase"
        assert by["cheap thing"]["conversions"] is None


def test_number_parsing():
    assert reports.number("< 10%", as_fraction=True) == 0.1
    assert reports.number("> 90%", as_fraction=True) == 0.9
    assert reports.number("US$1,234.50") == 1234.5
    assert reports.number("--") is None


def test_shopify_export_collapses_variant_rows(tmp_path):
    csv_text = ("Handle,Title,Body (HTML),Vendor,Type,Tags,Published,Variant SKU,Variant Price,Variant Inventory Qty,"
                "Variant Barcode,Cost per item,Image Src,Image Alt Text,SEO Title,Status\n"
                "mug,Big Mug,<p>x</p>,Acme,Mugs,a,TRUE,M-1,12.00,5,123456789012,3.20,http://i/1.jpg,,Mug,active\n"
                "mug,,,,,,,M-2,14.00,4,,,http://i/2.jpg,side,,\n")
    out = reports.normalize(_write(tmp_path, "products_export.csv", csv_text))
    assert out["table"] == "shopify_product_rows"
    (p,) = out["rows"]
    assert (p["price"], p["price_max"], p["inventory"], p["variant_count"], p["image_count"]) == (12.0, 14.0, 9.0, 2, 2)
    assert p["images_missing_alt"] == 1 and p["cost_coverage"] == 0.5


def test_unit_economics_breakeven():
    ue = metrics.unit_economics(40.0, 12.0, shipping=6.0, payment_fee_pct=0.029, payment_fee_fixed=0.30)
    assert ue["margin_before_ads"] == pytest.approx(40 - 12 - 6 - 1.46, abs=1e-6)
    assert ue["breakeven_roas"] == pytest.approx(40 / ue["margin_before_ads"], rel=1e-3)
    assert metrics.unit_economics(10.0, 12.0)["breakeven_roas"] is None


def _gads_store(store, tmp_path):
    st = reports.normalize(_write(tmp_path, "st.csv", GADS_SEARCH_TERMS))
    store.write_rows("gads_search_term_rows", st["rows"], store_id="s1", source_file="st.csv")
    camp = []
    for i in range(30):
        d = date(2026, 10, 11 + i) if i < 21 else date(2026, 11, i - 20)
        camp.append({"date": d.isoformat(), "campaign": "GADS-S1-SHOP-hero-roas", "type": "shopping",
                     "status": "enabled", "budget": 20.0, "bidding": "max_clicks", "cost": 20.0, "clicks": 30,
                     "conversions": 1.0, "conv_value": 90.0, "lost_is_budget": 0.3})
        camp.append({"date": d.isoformat(), "campaign": "GADS-S1-SRCH-new-roas", "type": "search",
                     "status": "enabled", "budget": 10.0, "bidding": "max_clicks", "cost": 10.0 if d >= date(2026, 11, 4) else 0,
                     "clicks": 5, "conversions": 0.0, "conv_value": 0.0})
    store.write_rows("gads_campaign_rows", [r for r in camp if r["cost"] or r["campaign"].endswith("hero-roas")],
                     store_id="s1", source_file="c.csv")
    prod = [{"date": "2026-09-20", "item_id": "z1", "title": "Zombie", "clicks": 60, "cost": 30.0, "conversions": 0.0,
             "conv_value": 0.0},
            {"date": "2026-11-05", "item_id": "z1", "title": "Zombie", "clicks": 55, "cost": 25.0, "conversions": 0.0,
             "conv_value": 0.0},
            {"date": "2026-11-06", "item_id": "n1", "title": "New", "clicks": 70, "cost": 9.0, "conversions": 0.0,
             "conv_value": 0.0}]
    store.write_rows("gads_product_rows", prod, store_id="s1", source_file="p.csv")


def test_a10_rules_on_fixtures(store, tmp_path):
    _gads_store(store, tmp_path)
    tables = prepare.gads_tables(store, "s1", window_days=14, today=TODAY, breakeven_roas=2.5)
    ctx = prepare.gads_context(store, "s1", breakeven_roas=2.5, aov=50.0)
    assert ctx["target_roas"] == 3.0 and ctx["target_cpa"] == pytest.approx(16.67, abs=0.01)
    ctx["in_learning"] = lambda c: tables["in_learning"].get(c, False)
    t = {k: v["value"] for k, v in kb.thresholds("thresholds.gads", {"store_id": "s1"}, store).items()}
    out = rules.run(rules.load_ruleset("gads_v1"), tables, t, ctx, mode="optimize_weekly")
    got = {(m["rule_id"], m["entity"]["id"]) for m in out["matches"]}
    assert ("gads.neg.no_conv_cost", "blue widget large") in got           # 102 >= 2 x 16.67, no conversion
    assert ("gads.neg.irrelevant_intent", "free widget pattern") in got
    neg = next(m for m in out["matches"] if m["rule_id"] == "gads.neg.irrelevant_intent")
    assert neg["action"]["after"]["term"] == "free"
    assert ("gads.harvest.exact", "widget gift set") in got                 # 3 conv, ROAS 8.3 >= 3
    assert ("gads.label.zombie", "z1") in got and ("gads.label.new", "n1") in got
    assert ("gads.label.zombie", "n1") not in got                          # new items are not zombies
    assert ("gads.bidding.to_value", "GADS-S1-SHOP-hero-roas") in got       # 30 conv in 30 days on max clicks
    up = next(m for m in out["matches"] if m["rule_id"] == "gads.budget.up")
    assert up["action"]["after"]["budget"] == 24.0                         # +20%, limited by budget, ROAS 4.5
    # the search campaign started 6 days ago: still learning, so only stop-loss may act on it
    assert tables["in_learning"]["GADS-S1-SRCH-new-roas"] is True
    assert ("gads.stop_loss", "GADS-S1-SRCH-new-roas") in got               # 60 spent, 0 conv >= 3 x CPA
    assert not any(m["entity"]["id"] == "GADS-S1-SRCH-new-roas" and m["rule_id"] != "gads.stop_loss"
                   for m in out["matches"])
    recs = records.to_actions(out["matches"], store_id="s1", platform="google_ads", window="14d",
                              source="gads_search_term_rows", today=TODAY)
    for d in recs["decisions"]:
        assert schemas.validate("DecisionRecord", d) == []
    for a in recs["actions"]:
        assert schemas.validate("ProposedAction", a) == []


def test_daily_mode_runs_only_stop_loss_and_cost_negatives(store, tmp_path):
    _gads_store(store, tmp_path)
    tables = prepare.gads_tables(store, "s1", window_days=7, today=TODAY, breakeven_roas=2.5)
    ctx = {**prepare.gads_context(store, "s1", breakeven_roas=2.5, aov=50.0),
           "in_learning": lambda c: tables["in_learning"].get(c, False)}
    t = {k: v["value"] for k, v in kb.thresholds("thresholds.gads").items()}
    out = rules.run(rules.load_ruleset("gads_v1"), tables, t, ctx, mode="optimize_daily")
    assert {m["rule_id"] for m in out["matches"]} <= {"gads.stop_loss", "gads.neg.no_conv_cost"}


def test_rule_expressions_are_sandboxed():
    for bad in ("__import__('os')", "row.__class__", "().__class__", "[x for x in y]", "lambda: 1"):
        with pytest.raises((ValueError, SyntaxError)):
            rules.evaluate(bad, {}, {}, {})
    assert rules.evaluate("cost >= t.k * ctx.cpa", {"cost": 10}, {"k": 2}, {"cpa": 5}) is True
    assert rules.evaluate("cost >= 1", {"cost": None}, {}, {}) is False


def test_tracking_audit_fails_on_missing_or_double_primary():
    rs = rules.load_ruleset("tracking_v1")
    t = {"tracking_gap_warn": 0.25}
    none = prepare.tracking_facts([{"name": "Purchase", "category": "purchase", "primary": False}])
    assert {m["rule_id"] for m in rules.run(rs, {"facts": [none]}, t)["matches"]} == {"trk.no_primary_purchase"}
    double = prepare.tracking_facts([{"name": "Google Shopping App Purchase", "category": "purchase", "primary": True},
                                     {"name": "GA4 purchase", "category": "purchase", "primary": True}])
    assert "trk.double_primary" in {m["rule_id"] for m in rules.run(rs, {"facts": [double]}, t)["matches"]}
    good = prepare.tracking_facts([{"name": "Purchase", "category": "purchase", "primary": True, "counting": "Every",
                                    "value_tracking": True, "status": "Active"}],
                                  shopify_orders=20, gads_conversions=18, ga4_purchases=17)
    assert rules.run(rs, {"facts": [good]}, t)["matches"] == []


def test_feed_audit_flags_identifiers_promo_titles_and_policy_pages(store):
    store.write_rows("gmc_product_rows", [
        {"item_id": "a", "title": "Acme Big Mug 11oz", "status": "approved", "gtin": "123", "image_link": "x",
         "google_product_category": "Mugs"},
        {"item_id": "b", "title": "BEST MUG SALE!!", "status": "disapproved", "issue": "Missing GTIN",
         "image_link": "x"}], store_id="s1", source_file="gmc.csv", date_col=None)
    ft = prepare.feed_tables(store, "s1", policy_pages={"refund": True, "shipping": False, "privacy": True,
                                                        "terms": True, "contact": True})
    assert ft["approval_rate"] == 0.5
    t = {"title_max": 150}
    got = {(m["rule_id"], m["entity"]["id"]) for m in rules.run(rules.load_ruleset("feed_v1"), ft, t)["matches"]}
    assert {("feed.item_disapproved", "b"), ("feed.no_identifier", "b"), ("feed.title_promo", "b"),
            ("feed.policy_pages_missing", "account")} <= got
    assert not any(e == "a" for _, e in got)


def test_readiness_blocks_until_every_gate_passes():
    rs = rules.load_ruleset("readiness_v1")
    t = {"feed_approval_min": 0.8}
    row = {"store_id": "s1", "tracking": "pass", "feed_approval_rate": 0.95, "feed_account_issues": 0,
           "policy_pages_ok": True, "auto_apply_off": True}
    assert rules.run(rs, {"summary": [row]}, t)["matches"] == []
    bad = {**row, "tracking": "fail", "auto_apply_off": None}
    assert {m["action"]["blocker"] for m in rules.run(rs, {"summary": [bad]}, t)["matches"]} == {"tracking", "settings"}


def test_bulk_files_only_write_approved_actions_and_never_shopify_price(tmp_path):
    acts = [
        {"action_id": "1", "type": "negate_keyword", "status": "approved", "target": {"type": "search_term", "id": "x"},
         "after": {"term": "blue widget large", "match": "exact", "level": "campaign", "campaign": "C1"}},
        {"action_id": "2", "type": "budget_change", "status": "approved", "target": {"type": "campaign", "id": "C1"},
         "after": {"budget": 24}},
        {"action_id": "3", "type": "negate_keyword", "status": "approved", "target": {"type": "search_term", "id": "y"},
         "after": {"term": "free", "match": "phrase", "level": "shared_list"}},
        {"action_id": "4", "type": "budget_change", "status": "proposed", "target": {"type": "campaign", "id": "C2"},
         "after": {"budget": 99}},
    ]
    out = bulk_files.build("google_ads", acts, tmp_path / "gads.csv")
    text = (tmp_path / "gads.csv").read_text(encoding="utf-8")
    assert out["rows"] == 2 and "Campaign negative exact" in text and "24.00" in text and "C2" not in text
    assert out["manual"][0]["term"] == "free" and out["skipped"][0]["action_id"] == "4"
    shop = [{"action_id": "s", "type": "listing_update", "status": "approved", "target": {"type": "product", "id": "mug"},
             "after": {"seo_title": "Big Mug", "price": 1}},
            {"action_id": "t", "type": "listing_update", "status": "approved", "target": {"type": "product", "id": "cup"},
             "after": {"seo_title": "Cup"}}]
    out = bulk_files.build("shopify_products", shop, tmp_path / "shop.csv")
    assert out["columns"] == ["Handle", "SEO Title"] and out["rows"] == 1 and out["skipped"][0]["action_id"] == "s"
    gmc = [{"action_id": "g", "type": "label_change", "status": "approved", "target": {"type": "product", "id": "z1"},
            "after": {"custom_label_0": "zombie"}}]
    bulk_files.build("gmc_supplemental", gmc, tmp_path / "supp.tsv")
    assert (tmp_path / "supp.tsv").read_text(encoding="utf-8") == "id\tcustom_label_0\nz1\tzombie\n"
