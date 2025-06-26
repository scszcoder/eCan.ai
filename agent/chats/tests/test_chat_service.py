import pytest
from agent.chats.chat_service import ChatService
from agent.chats.chats_db import Base, get_engine

@pytest.fixture(scope="function")
def chat_service():
    # 使用内存数据库，测试后清理所有表
    engine = get_engine(':memory:')
    Base.metadata.create_all(engine)
    service = ChatService(engine=engine)
    yield service
    Base.metadata.drop_all(engine)

def test_create_chat_and_add_message(chat_service):
    # 创建会话
    members = [
        {"id": "user-1", "role": "user", "name": "用户1"},
        {"id": "assistant-1", "role": "assistant", "name": "助手1"}
    ]
    chat_name = "测试会话"
    resp = chat_service.create_chat(members=members, name=chat_name)
    assert resp["success"] is True
    chat_id = resp["id"]
    # 添加消息
    msg_resp = chat_service.add_message(
        chat_id=chat_id,
        role="user",
        content={"type": "text", "text": "你好"},
        senderId="user-1",
        createAt=1710000000000
    )
    assert msg_resp["success"] is True
    assert msg_resp["data"]["content"]["text"] == "你好"

def test_query_chats_by_user(chat_service):
    # 创建会话
    members = [
        {"id": "user-2", "role": "user", "name": "用户2"},
        {"id": "assistant-2", "role": "assistant", "name": "助手2"}
    ]
    chat_name = "会话2"
    resp = chat_service.create_chat(members=members, name=chat_name)
    chat_id = resp["id"]
    # 查询 user-2 的会话
    result = chat_service.query_chats_by_user(user_id="user-2")
    assert result["success"] is True
    assert any(chat["id"] == chat_id for chat in result["data"])
    # user_id 为空
    result2 = chat_service.query_chats_by_user(user_id=None)
    assert result2["success"] is False
    assert result2["error"] == "user_id is required"

def test_query_messages_by_chat(chat_service):
    # 创建会话并添加多条消息
    members = [
        {"id": "user-3", "role": "user", "name": "用户3"},
        {"id": "assistant-3", "role": "assistant", "name": "助手3"}
    ]
    resp = chat_service.create_chat(members=members, name="会话3")
    chat_id = resp["id"]
    msg_ids = []
    for i in range(5):
        msg = chat_service.add_message(
            chat_id=chat_id,
            role="user",
            content={"type": "text", "text": f"消息{i}"},
            senderId="user-3",
            createAt=1710000000000 + i
        )
        msg_ids.append(msg["id"])
    # 查询消息，limit=3
    result = chat_service.query_messages_by_chat(chat_id=chat_id, limit=3)
    assert result["success"] is True
    assert len(result["data"]) == 3
    # chat_id 为空
    result2 = chat_service.query_messages_by_chat(chat_id=None)
    assert result2["success"] is False
    assert result2["error"] == "chat_id is required"
    # 批量标记为已读
    mark_result = chat_service.mark_message_as_read(message_ids=msg_ids[:3], user_id="user-3")
    assert mark_result["success"] is True
    assert set(mark_result["data"]) == set(msg_ids[:3])
    # 检查消息 is_read 字段
    all_msgs = chat_service.query_messages_by_chat(chat_id=chat_id, limit=10)["data"]
    for i, msg in enumerate(all_msgs):
        if i < 3:
            assert msg["is_read"] is True
        else:
            assert msg["is_read"] is False
    # 检查 chat 的 unread 数量
    chat_info = chat_service.query_chats_by_user(user_id="user-3", deep=True)["data"]
    for chat in chat_info:
        if chat["id"] == chat_id:
            assert chat["unread"] == 2

def test_delete_chat(chat_service):
    # 创建会话
    members = [
        {"id": "user-4", "role": "user", "name": "用户4"},
        {"id": "assistant-4", "role": "assistant", "name": "助手4"}
    ]
    resp = chat_service.create_chat(members=members, name="会话4")
    chat_id = resp["id"]
    # 删除会话
    del_resp = chat_service.delete_chat(chat_id=chat_id)
    assert del_resp["success"] is True
    # 再次删除应报错
    del_resp2 = chat_service.delete_chat(chat_id=chat_id)
    assert del_resp2["success"] is False
    assert "not found" in del_resp2["error"] 