"""A skill that declares its inputs must report them to the task editor.

`get_agent_skills` serves skills from memory and lets the DB only backfill ids
that memory is missing. That is right for runtime state and wrong for
`need_inputs`/`objectives`, which are declarative and persisted: a skill edited
after the app started has them in the DB while the long-lived in-memory
EC_Skill still carries whatever it was built with.

The consequence is not cosmetic. TaskDetail's 任务变量 section is driven by
`skill.need_inputs`, so a stale empty list means the task editor offers no
fields, the task saves no values, and the run fails with "missing upstream
data" -- which is exactly what happened on 2026-09-18: etsy_after_sales0
declared docs_dir / printer_name / summary_emails in the DB, the editor showed
nothing, and the run sent no emails because summary_emails was never supplied.

Same family as the org_id staleness in get_all_org_agents: one merge, memory
winning a field it should not own.
"""

import pytest

from gui.ipc.w2p_handlers.skill_handler import _refresh_declared_inputs


NEED = [
    {"name": "docs_dir", "type": "string"},
    {"name": "printer_name", "type": "string"},
    {"name": "summary_emails", "type": "string"},
]


def _names(skill):
    return [i["name"] for i in (skill.get("need_inputs") or [])]


def test_a_stale_empty_declaration_is_refreshed_from_the_db():
    served = [{"id": "skill_a9e7", "name": "etsy_after_sales0", "need_inputs": []}]
    _refresh_declared_inputs(served, "skill_a9e7", "",
                             {"id": "skill_a9e7", "need_inputs": NEED})
    assert _names(served[0]) == ["docs_dir", "printer_name", "summary_emails"]


def test_a_missing_declaration_is_filled_in():
    served = [{"id": "s1", "name": "x"}]                    # no key at all
    _refresh_declared_inputs(served, "s1", "", {"id": "s1", "need_inputs": NEED})
    assert _names(served[0]) == ["docs_dir", "printer_name", "summary_emails"]


def test_objectives_travel_the_same_way():
    served = [{"id": "s1", "name": "x", "objectives": []}]
    _refresh_declared_inputs(served, "s1", "",
                             {"id": "s1", "objectives": [{"name": "o"}]})
    assert served[0]["objectives"] == [{"name": "o"}]


def test_an_empty_db_value_does_not_wipe_a_live_declaration():
    """The DB row for the duplicate twin has [] -- it must not win."""
    served = [{"id": "s1", "name": "x", "need_inputs": NEED}]
    _refresh_declared_inputs(served, "s1", "", {"id": "s1", "need_inputs": []})
    assert _names(served[0]) == ["docs_dir", "printer_name", "summary_emails"]


def test_only_the_matching_skill_is_touched():
    served = [
        {"id": "s1", "name": "a", "need_inputs": []},
        {"id": "s2", "name": "b", "need_inputs": []},
    ]
    _refresh_declared_inputs(served, "s2", "", {"id": "s2", "need_inputs": NEED})
    assert _names(served[0]) == []
    assert _names(served[1]) == ["docs_dir", "printer_name", "summary_emails"]


def test_it_can_match_on_askid_when_ids_differ():
    served = [{"id": "local_1", "askid": "ask_9", "name": "x", "need_inputs": []}]
    _refresh_declared_inputs(served, "", "ask_9", {"askid": "ask_9", "need_inputs": NEED})
    assert _names(served[0]) == ["docs_dir", "printer_name", "summary_emails"]


def test_nothing_else_about_the_memory_row_is_replaced():
    """Runtime state stays memory's; only the declaration is refreshed."""
    served = [{"id": "s1", "name": "live-name", "version": "9.9",
               "config": {"runtime": "keep me"}, "need_inputs": []}]
    _refresh_declared_inputs(served, "s1", "",
                             {"id": "s1", "name": "db-name", "version": "1.0",
                              "config": {}, "need_inputs": NEED})
    assert served[0]["name"] == "live-name"
    assert served[0]["version"] == "9.9"
    assert served[0]["config"] == {"runtime": "keep me"}
    assert _names(served[0]) == ["docs_dir", "printer_name", "summary_emails"]


def test_an_unknown_id_is_a_no_op():
    served = [{"id": "s1", "name": "x", "need_inputs": []}]
    _refresh_declared_inputs(served, "nope", "", {"id": "nope", "need_inputs": NEED})
    assert _names(served[0]) == []


def test_the_handler_still_calls_it():
    """Guard against the call being dropped in a future refactor."""
    import inspect
    from gui.ipc.w2p_handlers import skill_handler

    src = inspect.getsource(skill_handler.handle_get_agent_skills)
    assert "_refresh_declared_inputs(" in src, (
        "get_agent_skills no longer refreshes declared inputs from the DB; a "
        "stale in-memory skill will hide its own need_inputs again"
    )
