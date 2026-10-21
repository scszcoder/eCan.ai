"""Unit tests for Q&A capture (model + service + record_qa helper)."""

from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.services.db_qa_history_service import DBQaHistoryService
from agent.ec_skills import qa_capture


def _service():
    # In-memory DB; BaseService.__init__ runs create_all, so qa_history exists.
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return DBQaHistoryService(engine=eng)


# --- service ------------------------------------------------------------------

def test_add_and_list():
    svc = _service()
    res = svc.add_qa(store_id="douyin-店B", agent_id="agent_x", task_id="task_y",
                     product_id="123456", question="多久发货?", answer="48小时内发货")
    assert res["success"] is True
    rows = svc.list_by_status("new")
    assert len(rows) == 1
    r = rows[0]
    assert r["store_id"] == "douyin-店B"
    assert r["agent_id"] == "agent_x"
    assert r["task_id"] == "task_y"
    assert r["product_id"] == "123456"
    assert r["question"] and r["answer"]
    assert r["status"] == "new"
    assert r["created_at"]  # timestamp populated by BaseModel


def test_empty_qa_rejected():
    svc = _service()
    assert svc.add_qa(store_id="s", question="", answer="")["success"] is False


def test_mark_status_moves_rows():
    svc = _service()
    rid = svc.add_qa(store_id="s", question="q", answer="a")["id"]
    assert svc.mark_status([rid], "mined") == 1
    assert svc.count_by_status("new") == 0
    assert len(svc.list_by_status("mined")) == 1


# --- record_qa helper (scope derivation + full key set) -----------------------

class _Ctx:
    def __init__(self, mgr, calling_agent_id=""):
        self.mainwin = type("MW", (), {"ec_db_mgr": mgr})()
        self.calling_agent_id = calling_agent_id


class _Mgr:
    def __init__(self, svc):
        self.qa_history_service = svc


def test_record_qa_populates_all_keys():
    svc = _service()
    ctx = _Ctx(_Mgr(svc))
    # 商品ID lives in the buyer's product-card text inside state; scope_from_state
    # extracts it. store_id is seeded into prompt_refs by apply_task_vars.
    state = {
        "attributes": {"agent_id": "agent_7ca0", "task_id": "task_33e6", "chat_id": "talk_1"},
        "prompt_refs": {"store_id": "douyin-店B"},
        "messages": ["商品ID：7654321 这个有货吗"],
    }
    payload = {
        "response_text": "有货，48小时内发货",
        "source_latest_message": "这个什么时候发货?",
        "customer_name": "张三",
        "customer_id": "cust_9",
    }
    qa_capture.record_qa(state, payload, ctx)

    rows = svc.list_by_status("new")
    assert len(rows) == 1
    r = rows[0]
    assert r["store_id"] == "douyin-店B"
    assert r["product_id"] == "7654321"
    assert r["platform"] == "douyin"          # derived from store_id prefix
    assert r["agent_id"] == "agent_7ca0"
    assert r["task_id"] == "task_33e6"
    assert r["chat_id"] == "talk_1"
    assert r["customer_name"] == "张三"
    assert r["customer_id"] == "cust_9"
    assert r["question"] == "这个什么时候发货?"
    assert r["answer"] == "有货，48小时内发货"


def test_record_qa_agent_id_falls_back_to_ctx():
    svc = _service()
    ctx = _Ctx(_Mgr(svc), calling_agent_id="agent_fallback")
    state = {"attributes": {}, "prompt_refs": {"store_id": "qianniu-shopA"}}
    payload = {"response_text": "a", "source_latest_message": "q"}
    qa_capture.record_qa(state, payload, ctx)
    r = svc.list_by_status("new")[0]
    assert r["agent_id"] == "agent_fallback"
    assert r["platform"] == "qianniu"


def test_record_qa_never_raises_without_db():
    # No ec_db_mgr reachable -> must swallow and not raise.
    ctx = type("C", (), {"mainwin": None, "calling_agent_id": ""})()
    qa_capture.record_qa({"attributes": {}}, {"response_text": "a",
                         "source_latest_message": "q"}, ctx)  # no exception
