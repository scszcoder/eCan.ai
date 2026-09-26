"""A brand-new machine (e.g. a new Platoon) starts with no database: first start must build all of it."""

import sqlite3

from agent.db.ec_db_mgr import initialize_ecan_database


def test_a_fresh_machine_gets_every_table_and_service(tmp_path):
    mgr = initialize_ecan_database(str(tmp_path), auto_migrate=True)
    with sqlite3.connect(mgr.db_path) as conn:
        tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        version = conn.execute("select version from db_version order by rowid desc limit 1").fetchone()
    for needed in ("agents", "agent_tasks", "agent_skills", "agent_task_rels",
                   "agent_task_skill_rels", "agent_skill_rels", "store", "agent_vehicles",
                   "usage_event", "token_usage", "chats", "messages", "db_version"):
        assert needed in tables, f"fresh database is missing {needed!r}"
    assert version and version[0]
    for svc in ("agent_service", "task_service", "skill_service", "vehicle_service", "store_service"):
        assert getattr(mgr, svc, None) is not None, svc
    # a second start on the same file is a no-op, not a failure
    again = initialize_ecan_database(str(tmp_path), auto_migrate=True)
    assert again.task_service is not None
