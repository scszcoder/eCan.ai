"""Unit tests for KB mining: candidate service + propose/query MCP tools."""

import asyncio
import json

from sqlalchemy import create_engine

from agent.db.core.base import Base
from agent.db.services.db_qa_history_service import DBQaHistoryService
from agent.db.services.db_kb_candidate_service import DBKbCandidateService
from agent.mcp.server.kb import kb_mining_tools as kb


class _Mgr:
    """Stand-in for ec_db_mgr with both services on one in-memory DB."""
    def __init__(self):
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        self.qa_history_service = DBQaHistoryService(engine=eng)
        self.kb_candidate_service = DBKbCandidateService(engine=eng)


class _Mainwin:
    def __init__(self, mgr, user="owner@test.com"):
        self.ec_db_mgr = mgr
        self.auth_manager = type("AM", (), {"get_current_user": lambda self: user})()


def _meta(res):
    return getattr(res[0], "meta", {})


# --- candidate service --------------------------------------------------------

def test_candidate_lifecycle():
    svc = _Mgr().kb_candidate_service
    rid = svc.add_candidate(question="发货多久?", answer="48小时内", owner="o@x.com")["id"]
    assert len(svc.list_candidates("pending")) == 1
    svc.set_status(rid, "promoted", promoted_ref="pol_1", answer="48小时内发货")
    assert svc.list_candidates("pending") == []
    promoted = svc.list_candidates("promoted")[0]
    assert promoted["promoted_ref"] == "pol_1"
    assert promoted["answer"] == "48小时内发货"


def test_candidate_requires_both_fields():
    svc = _Mgr().kb_candidate_service
    assert svc.add_candidate(question="q", answer="")["success"] is False


# --- query_qa_history tool ----------------------------------------------------

def test_query_qa_history_tool():
    mgr = _Mgr()
    mgr.qa_history_service.add_qa(store_id="douyin-店B", question="q1", answer="a1")
    mw = _Mainwin(mgr)
    m = _meta(asyncio.run(kb.query_qa_history(mw, {"input": {"status": "new"}})))
    assert m["status"] == "success"
    assert m["count"] == 1
    assert m["rows"][0]["question"] == "q1"


# --- propose_kb_candidate tool ------------------------------------------------

def test_propose_marks_sources_mined_and_creates_candidate():
    mgr = _Mgr()
    qid = mgr.qa_history_service.add_qa(store_id="douyin-店B", question="发货?", answer="48h")["id"]
    mw = _Mainwin(mgr)
    res = asyncio.run(kb.propose_kb_candidate(mw, {"input": {
        "question": "多久发货?", "answer": "48小时内发货",
        "store_id": "douyin-店B", "source_ids": [qid], "confidence": 0.9,
    }}))
    m = _meta(res)
    assert m["status"] == "success" and m["ok"] is True
    # candidate created, owner + platform filled
    cand = mgr.kb_candidate_service.list_candidates("pending")[0]
    assert cand["owner"] == "owner@test.com"
    assert cand["platform"] == "douyin"
    assert cand["store_id"] == "douyin-店B"
    # source qa_history turn retired so it won't be mined again
    assert mgr.qa_history_service.count_by_status("new") == 0
    assert len(mgr.qa_history_service.list_by_status("mined")) == 1


def test_propose_requires_question_and_answer():
    mw = _Mainwin(_Mgr())
    m = _meta(asyncio.run(kb.propose_kb_candidate(mw, {"input": {"question": "q"}})))
    assert m["status"] == "error"


def test_tools_degrade_without_db():
    mw = type("MW", (), {"ec_db_mgr": None})()
    m = _meta(asyncio.run(kb.query_qa_history(mw, {"input": {}})))
    assert m["status"] == "not_available"
