"""An agent bound to a department must appear in that department.

The Agents page filters a flat agent list by `agent.org_id`, and that list comes
from `get_all_org_agents`, which merges two sources:

    memory : EC_Agent objects, authoritative for RUNTIME state
    DB     : agent dicts, authoritative for PERSISTED state

Membership is persisted state -- it lives in `agent_org_rels`, and
`DBAgent.to_dict()` derives `org_id` from it. But an EC_Agent carries whatever
`org_id` it was constructed with, and only the bind handler updates it in
place. Any other route into that table leaves the runtime copy stale, and
because memory wins the whole row, a stale copy used to shadow the DB -- so an
agent that really was in Sales showed up nowhere.

Observed 2026-09-18: 李四0 and 李四2 both had active `org_sales_001` rows and
`get_agents_by_owner` returned `org_id='org_sales_001'` for both, yet neither
appeared under Sales in the GUI.
"""

import pytest


def merge_org_ids(mem_agents_map, db_rows):
    """The merge rule under test, in isolation.

    Mirrors the loop in `handle_get_all_org_agents`: DB rows refresh `org_id`
    on agents already in memory, and backfill agents that are not.
    """
    db_backfill = {}
    for row in db_rows:
        aid = row.get("id")
        if not aid:
            continue
        if aid in mem_agents_map:
            mem_agents_map[aid]["org_id"] = row.get("org_id")
        else:
            db_backfill[aid] = row
    return list(mem_agents_map.values()) + list(db_backfill.values())


def _by_name(agents):
    return {a["name"]: a for a in agents}


def test_a_stale_memory_copy_does_not_hide_department_membership():
    """The reported bug: bound in the DB, org_id=None in memory."""
    memory = {
        "agent_d0d1": {"id": "agent_d0d1", "name": "lisi0", "org_id": None},
        "agent_1142": {"id": "agent_1142", "name": "lisi2", "org_id": None},
    }
    db_rows = [
        {"id": "agent_d0d1", "name": "lisi0", "org_id": "org_sales_001"},
        {"id": "agent_1142", "name": "lisi2", "org_id": "org_sales_001"},
    ]

    merged = _by_name(merge_org_ids(memory, db_rows))

    in_sales = [n for n, a in merged.items() if a["org_id"] == "org_sales_001"]
    assert sorted(in_sales) == ["lisi0", "lisi2"], (
        "an agent with an active rel to Sales must come back in Sales"
    )


def test_a_move_between_departments_is_picked_up():
    """Stale the other way: memory says Sales, the DB has moved it."""
    memory = {"a1": {"id": "a1", "name": "x", "org_id": "org_sales_001"}}
    db_rows = [{"id": "a1", "name": "x", "org_id": "org_marketing_001"}]

    merged = _by_name(merge_org_ids(memory, db_rows))
    assert merged["x"]["org_id"] == "org_marketing_001"


def test_an_unbind_is_picked_up():
    """And a removal must not leave the agent stuck in its old department."""
    memory = {"a1": {"id": "a1", "name": "x", "org_id": "org_sales_001"}}
    db_rows = [{"id": "a1", "name": "x", "org_id": None}]

    merged = _by_name(merge_org_ids(memory, db_rows))
    assert merged["x"]["org_id"] is None


def test_memory_only_agents_keep_their_org():
    """Runtime-only agents (MyTwinAgent, helper) are not in the DB result.

    They must pass through untouched -- the fix must not blank them just
    because no DB row mentions them.
    """
    memory = {
        "twin": {"id": "twin", "name": "MyTwin", "org_id": "org_root_001"},
        "a1": {"id": "a1", "name": "x", "org_id": None},
    }
    db_rows = [{"id": "a1", "name": "x", "org_id": "org_sales_001"}]

    merged = _by_name(merge_org_ids(memory, db_rows))
    assert merged["MyTwin"]["org_id"] == "org_root_001"
    assert merged["x"]["org_id"] == "org_sales_001"


def test_db_only_agents_are_still_backfilled():
    """The pre-existing behaviour the fix must not break."""
    memory = {}
    db_rows = [{"id": "a1", "name": "x", "org_id": "org_sales_001"}]

    merged = _by_name(merge_org_ids(memory, db_rows))
    assert merged["x"]["org_id"] == "org_sales_001"


def test_the_handler_uses_this_rule():
    """Guard against the handler drifting away from the rule tested above."""
    import inspect

    try:
        from gui.ipc.w2p_handlers import agent_handler
    except Exception as exc:                       # pragma: no cover
        pytest.skip("handler stack unavailable: {}".format(exc))

    src = inspect.getsource(agent_handler.handle_get_all_org_agents)
    assert "mem_agents_map[aid]['org_id'] = db_org_id" in src, (
        "handle_get_all_org_agents no longer refreshes org_id from the DB; "
        "a stale memory copy will hide department membership again."
    )
