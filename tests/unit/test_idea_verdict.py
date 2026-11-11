"""The idea verdict says no when the numbers lose money, and shows them."""
from agent.ec_skills.reports import idea_verdict as iv

THIN = {"idea": "silicone phone case", "sale_price": 12.99, "unit_cost": 2.5, "freight_per_unit": 0.8,
        "monthly_units": 300, "cash_available": 3000}
STRONG = {"idea": "premium tool kit", "sale_price": 79.0, "unit_cost": 14.0, "freight_per_unit": 2.0,
          "fulfillment_fee": 7.5, "monthly_units": 200, "first_order_units": 300, "cash_available": 20000,
          "launch_budget": 2000}


def test_a_thin_margin_idea_is_dropped_with_its_loss():
    r = iv.evaluate(THIN)
    assert r["verdict"] == "DROP" and r["expected_loss"] > 0
    assert any("lose $" in s for s in r["reasons"])
    assert r["break_even_price"] > THIN["sale_price"] * 0.9
    assert r["loss_kind"] == "expected" and r["expected_loss"] == -r["scenarios"]["base"]["profit"]


def test_a_base_profit_with_a_conservative_loss_is_a_possible_loss():
    r = iv.evaluate(dict(STRONG, sale_price=55.0))
    assert r["scenarios"]["base"]["profit"] > 0 > r["scenarios"]["conservative"]["profit"]
    assert r["verdict"] == "DROP" and r["loss_kind"] == "possible"
    assert "you could lose" in iv.render_markdown(STRONG, r)


def test_a_strong_idea_works_on_paper():
    r = iv.evaluate(STRONG)
    assert r["verdict"] == "WORKS ON PAPER", r["reasons"]
    assert r["scenarios"]["conservative"]["profit"] >= 0


def test_not_enough_cash_is_a_reason_to_drop():
    r = iv.evaluate(dict(STRONG, cash_available=1000))
    assert r["verdict"] == "DROP" and any("in cash" in s for s in r["reasons"])


def test_missing_core_numbers_gives_no_verdict():
    r = iv.evaluate({"idea": "x", "sale_price": "$19.99"})
    assert r["verdict"] == "INCOMPLETE" and set(r["missing"]) == {"unit_cost", "monthly_units"}


def test_the_report_leads_with_the_loss_and_lists_assumptions():
    r = iv.evaluate(THIN)
    md = iv.render_markdown(THIN, r, {"median_competitor_price": "$9.99"})
    assert md.startswith("# DROP IT: expect to lose $") and "across the scenarios" in md
    assert "| Profit over the period |" in md and "median competitor price: $9.99" in md
    assert "referral pct" in md   # assumed, since the customer did not give it


def test_the_market_check_adds_its_own_reasons():
    market = {"price_median": "$29.99", "competition": "high", "ratings_count_median": 4200}
    r = iv.evaluate(dict(STRONG, sale_price=45.0), market)
    assert any("50% above the median" in s for s in r["reasons"])
    assert any("4,200 ratings" in s for s in r["reasons"]) and r["verdict"] == "DROP"


def test_the_verdict_step_saves_the_report_and_writes_the_chat_message(tmp_path, monkeypatch):
    import json
    from agent.ec_skills.reports import report_store as rs
    monkeypatch.setattr(rs, "reports_root", lambda: tmp_path)
    monkeypatch.setattr(rs, "_request_upload_url", lambda *a: {"error": "not deployed"})
    mined = {"niche": "phone case", "listings": [{"asin": "B1"}], "market": {"price_median": "$9.99"},
             "themes": [{"theme": "yellows", "kind": "complaint"}]}
    state = {"attributes": {"idea_answers": dict(THIN, customer_name="Kim")},
             "tool_result": {"market_check": {"final": json.dumps(mined)}}}
    out = iv.run_idea_check(state, node="market_check", date="2026-11-06")
    assert out["verdict"] == "DROP" and out["message"].startswith("DROP IT: expect to lose $")
    md = (tmp_path / "idea_check" / "Kim" / "2026-11-06" / "report.md").read_text(encoding="utf-8")
    assert "top buyer complaints: yellows" in md and "median $9.99" in md
