"""get_all_agents_runtime_status names agents that are not loaded in memory
(2026-10-28: right after login every agent was nameless, so `ecan agents stop
<name>` found nothing)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from gui.ipc.types import IPCRequest
from gui.ipc.w2p_handlers import agent_handler as ah


def test_unloaded_agents_get_their_db_name():
    loaded = SimpleNamespace(card=SimpleNamespace(id="a1", name="Loaded"), task_lock=MagicMock(), active_tasks={},
                             tasks=[])
    mainwin = SimpleNamespace(agents=[loaded], get_username=lambda: "me")
    db = MagicMock()
    db.agent_service.get_agents_by_owner.return_value = {"success": True, "data": [
        {"id": "a1", "name": "Loaded", "status": "active"},
        {"id": "a2", "name": "ChipCrawler1", "status": "active"},
        {"id": "a3", "name": "Off", "status": "disabled"}]}
    ah._batch_status_db_cache["timestamp"] = 0.0
    with patch.object(ah, "get_handler_context", return_value=mainwin), \
            patch.object(ah, "_get_main_window", return_value=None), \
            patch.object(ah.AppContext, "get_ec_db_mgr", return_value=db):
        resp = ah.handle_get_all_agents_runtime_status(IPCRequest(id="1", type="request", method="m", params={}), {})
    ah._batch_status_db_cache["timestamp"] = 0.0
    rows = {a["agent_id"]: a for a in resp["result"]["agents"]}
    assert rows["a2"]["agent_name"] == "ChipCrawler1" and rows["a2"]["runtime_status"] == "stopped"
    assert rows["a3"]["agent_name"] == "Off" and rows["a3"]["runtime_status"] == "disabled"
    assert rows["a1"]["agent_name"] == "Loaded"
