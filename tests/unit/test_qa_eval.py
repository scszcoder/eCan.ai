"""qa.eval (2026-10-23): a fake buyer turn with a picture reaches a Q&A agent
shaped like the front desk's hand-off; its reply comes back to the caller and
is never sent on."""
import json
import struct
import types
import zlib

import pytest

from agent.ec_skills import qa_eval


def _png():
    raw = b"".join(b"\x00" + bytes((200, 30, 30)) * 2 for _ in range(2))
    ck = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + ck(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
            + ck(b"IDAT", zlib.compress(raw)) + ck(b"IEND", b""))


def test_an_eval_turn_is_recognised_wherever_the_input_sits():
    payload = json.dumps({"latest_message": "有同款吗", qa_eval.MARK: "ev123"}, ensure_ascii=False)
    assert qa_eval.eval_id_of({"input": payload}) == "ev123"
    assert qa_eval.eval_id_of({"input": json.dumps({"msg": payload})}) == "ev123"     # nested / escaped
    assert qa_eval.eval_id_of({"input": {"x": 1}, "attributes": {qa_eval.MARK: "ev9"}}) == "ev9"
    assert qa_eval.eval_id_of({"input": "普通买家的问题"}) == ""


def test_send_response_back_sends_nothing_for_an_eval_turn(monkeypatch):
    import agent.ec_skills.llm_utils.llm_utils as lu
    looked_up = []
    monkeypatch.setattr(lu, "get_agent_by_id", lambda aid: looked_up.append(aid))
    ev = qa_eval.register("evA")
    state = {"input": json.dumps({qa_eval.MARK: "evA"}), "messages": ["qa-agent-id"],
             "result": {"llm_result": {"response_text": "有的亲，这款是红色纯棉T恤"}}}
    assert lu.send_response_back(state) is state
    assert looked_up == []                                    # never got as far as the sender
    assert ev.is_set() and qa_eval.take("evA")["llm_result"]["response_text"].startswith("有的亲")
    # A stale eval turn (nobody waiting any more) is still never sent.
    assert lu.send_response_back({"input": json.dumps({qa_eval.MARK: "gone"}), "messages": ["x"]})
    assert looked_up == []


def test_the_handler_hands_over_a_front_desk_shaped_turn(tmp_path, monkeypatch):
    from gui.ipc.w2p_handlers import qa_eval_handler as h
    import agent.ec_skills.llm_utils.llm_utils as lu
    import agent.mcp.server.chat_utils.chat_tools as ct
    pic = tmp_path / "buyer.png"
    pic.write_bytes(_png())
    ag = lambda i, n: types.SimpleNamespace(card=types.SimpleNamespace(id=i, name=n))
    agents = [ag("fd1", "前台-小店一号"), ag("qa1", "客服小慧")]
    monkeypatch.setattr(h, "_agents", lambda: (agents, object()))
    seen = {}

    def fake_send_chat(mainwin, cfg):             # the Q&A agent runs, then hands its answer back
        seen.update(cfg)
        lu.send_response_back({"input": cfg["message"], "messages": ["qa1"],
                               "result": {"llm_result": {"response_text": "这款我们有，红色纯棉圆领"}}})
        return {"success": True}
    monkeypatch.setattr(ct, "send_chat", fake_send_chat)
    out = h._run({"agent": "客服小慧", "text": "这个有吗", "images": [str(pic)], "store_id": "douyin-小店一号"})
    turn = json.loads(seen["message"])
    assert seen["sender_agent_id"] == "fd1" and seen["recipient_agent_id"] == "qa1"
    assert turn["latest_message"] == "这个有吗" and turn["store_id"] == "douyin-小店一号"
    att = turn["latest_message_attachments"][0]
    assert att["kind"] == "image" and att["data_uri"].startswith("data:image/png;base64,")
    assert turn["customer_id"].startswith("eval-")                # no real buyer can be reached
    assert out["finished"] and out["reply"]["llm_result"]["response_text"].startswith("这款我们有")
    with pytest.raises(ValueError):
        h._run({"agent": "nobody", "text": "x"})


def test_send_chat_holds_an_eval_reply_but_lets_the_eval_hand_off_through(monkeypatch):
    import agent.mcp.server.chat_utils.chat_tools as ct
    ev = qa_eval.register("evB")
    reply = json.dumps({"customer_id": "eval-evB", "customer_name": "测试买家",
                        "response_text": "有的亲，这款牛仔短裤还有货"}, ensure_ascii=False)
    out = ct.send_chat(object(), {"sender_agent_id": "qa1", "recipient_agent_id": "fd1",
                                   "chat_id": "eval-evB", "message": reply})
    assert out["eval_captured"] and ev.is_set()
    assert qa_eval.take("evB")["response_text"].startswith("有的亲")
    hand_off = json.dumps({"customer_id": "eval-evC", qa_eval.MARK: "evC", "latest_message": "x"})
    assert qa_eval.capture_send(hand_off) is None                  # the turn itself goes through
    assert qa_eval.capture_send(json.dumps({"customer_id": "张三", "response_text": "x"})) is None


def test_the_turn_comes_from_the_q_and_a_tasks_own_front_desk(monkeypatch):
    from gui.ipc.w2p_handlers import qa_eval_handler as h
    import agent.mcp.server.chat_utils.chat_tools as ct
    ag = lambda i, n, tasks=(): types.SimpleNamespace(card=types.SimpleNamespace(id=i, name=n), tasks=list(tasks))
    task = types.SimpleNamespace(metadata={"task_vars": {"front_desk_agent_id": "fd2"}})
    agents = [ag("fd1", "前台小张"), ag("fd2", "前台-小店一号"), ag("qa1", "客服小敏", [task])]
    monkeypatch.setattr(h, "_agents", lambda: (agents, object()))
    seen = {}
    monkeypatch.setattr(ct, "send_chat", lambda mw, cfg: seen.update(cfg) or {"success": True})
    h._run({"agent": "客服小敏", "text": "在吗", "timeout_s": 0.1})
    assert seen["sender_agent_id"] == "fd2"
