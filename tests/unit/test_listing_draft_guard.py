import json

from agent.ec_skills.listing import draft_guard as dg

ENTRY = {
    "model": "KX100",
    "upc": "000000000001",
    "owner_confirmed": {"wattage": "900 W", "color": "Red", "weight": "4.2 lb"},
    "features": ["Five speeds", "Pulse mode", "Dishwasher-safe jar"],
}


def _proposal(**kw):
    p = {
        "model": "Acme KX100",
        "title": "Acme KX100 Blender",
        "title_length": 3,
        "item_specifics": {"Brand": "Acme", "Wattage": "1000 W"},
        "condition_description": "Open box, never used. Please review the photos of the packaging.",
        "description": "The Acme KX100 is a blender in red. The box indicates fast blending. Open box, never used.",
        "selling_points": ["Five speeds", "Five speeds (per box)"],
        "flags": ["Owner-confirmed 900 W supersedes the web value.", "Only two selling points."],
    }
    p.update(kw)
    return p


def test_confirmed_values_become_item_specifics_under_one_name():
    p = dg.guard_proposal(_proposal(), ENTRY)
    assert p["item_specifics"]["Power"] == "900 W"
    assert "Wattage" not in p["item_specifics"]
    assert p["item_specifics"]["Color"] == "Red"
    assert p["item_specifics"]["UPC"] == "000000000001"


def test_description_drops_source_sentences_and_states_missing_values_before_condition():
    p = dg.guard_proposal(_proposal(), ENTRY)
    d = p["description"]
    assert "box indicates" not in d.lower()
    assert "Power: 900 W; Weight: 4.2 lb." in d
    assert d.endswith("Open box, never used.")
    assert "red" in d.lower() and "Color:" not in d  # already stated, not repeated


def test_a_value_stated_in_other_word_order_is_not_added_again():
    entry = {"model": "KX100", "owner_confirmed": {"warranty": "Two-year limited manufacturer warranty"}}
    p = dg.guard_proposal(_proposal(description="The manufacturer warranty is two-year limited. Open box, never used."), entry)
    assert "Warranty:" not in p["description"]


def test_condition_is_one_plain_sentence():
    assert dg.guard_proposal(_proposal(), ENTRY)["condition_description"] == "Open box, never used."


def test_features_become_selling_points_and_stale_flags_are_rebuilt():
    p = dg.guard_proposal(_proposal(), ENTRY)
    assert p["selling_points"] == ENTRY["features"]
    assert p["flags"] == ["3 selling points; add sourced features to reach 7."]


def test_without_features_selling_points_are_deduplicated():
    p = dg.guard_proposal(_proposal(selling_points=["Pulse mode", "Pulse mode", "Not verified speed"]), {})
    assert p["selling_points"] == ["Pulse mode"]


def test_title_is_measured_and_cut_at_a_word():
    long = "Acme KX100 " + "Blender " * 12
    p = dg.guard_proposal(_proposal(title=long), ENTRY)
    assert len(p["title"]) <= 80 and not p["title"].endswith(" ")
    assert p["title_length"] == len(p["title"])


def test_main_guards_the_report_and_drops_settled_conflicts(tmp_path):
    (tmp_path / "products.json").write_text(json.dumps({"models": [ENTRY]}), encoding="utf-8")
    report = {"proposals": [_proposal()],
              "conflicts": ["Web lists 900 W while the manual says 850 W.", "Two UPCs found."],
              "gaps": ["Only two selling points.", "No video."]}
    state = {"result": {"llm_result": {"next_tool_input": {"report": report, "report_md": "# Acme KX100 Blender"},
                                       "chat_brief": {"per_model": [{"title": "Acme KX100 Blender"}]}}},
             "prompt_refs": {"run_context": {"product_folder": str(tmp_path)}}}
    dg.main(state)
    out = state["result"]["llm_result"]["next_tool_input"]["report"]
    assert out["proposals"][0]["item_specifics"]["Power"] == "900 W"
    assert out["proposals"][0]["guard_fixes"]
    assert out["conflicts"] == ["Two UPCs found."]
    assert out["gaps"] == ["No video."]


def test_report_md_lines_are_rewritten_with_guarded_values():
    p = dg.guard_proposal(_proposal(), ENTRY)
    md = ("## Acme KX100\n- **Title:** Acme KX100 Blender\n- **Selling points:** Five speeds.\n"
          "- **Flags:** Only two selling points.\n## Gaps\n- **Flags:** keep me")
    out = dg.patch_md(md, p)
    assert "- **Selling points:** Five speeds; pulse mode; dishwasher-safe jar." in out
    assert "- **Flags:** 3 selling points; add sourced features to reach 7." in out
    assert out.endswith("- **Flags:** keep me")


def test_main_leaves_a_report_without_proposals_alone():
    state = {"result": {"llm_result": {"next_tool_input": {"report": {"proposals": []}}}}}
    assert dg.main(state) is state
    assert state["result"]["llm_result"]["next_tool_input"]["report"] == {"proposals": []}
