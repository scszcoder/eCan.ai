import os
import json
import tempfile
import shutil
from agent.chats.chat_service import ChatService
from agent.chats.chats_db import get_engine, Base, Chat, Member, Message, Attachment

def test_chatservice_import_demo():
    # 创建临时数据库和 demo 数据
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_chat_app.db')
    demo_path = os.path.join(temp_dir, 'chats_demo.json')

    # 构造更复杂的 demo 数据
    demo_data = [
        {
            "id": "chat-1",
            "type": "user-agent",
            "name": "AI助手",
            "avatar": "avatar1.png",
            "members": [
                {"id": "user-1", "role": "user", "name": "用户", "avatar": "user1.png"},
                {"id": "assistant-1", "role": "assistant", "name": "AI助手", "avatar": "ai1.png"}
            ],
            "messages": [
                {"id": "msg-1", "role": "user", "createAt": 1710000000000, "content": "你好", "status": "complete"},
                {"id": "msg-2", "role": "assistant", "createAt": 1710000001000, "content": {"type": "text", "text": "您好，有什么可以帮您？"}, "status": "complete"},
                {"id": "msg-3", "role": "user", "createAt": 1710000002000, "content": {"type": "image", "imageUrl": "img1.png"}, "status": "complete", "attachment": [
                    {"uid": "att-1", "name": "图片1", "status": "done", "url": "img1.png", "size": 12345, "type": "image/png"}
                ]},
                {"id": "msg-4", "role": "assistant", "createAt": 1710000003000, "content": {"type": "code", "code": {"lang": "python", "value": "print('hello')"}}, "status": "complete"}
            ],
            "lastMsg": "print('hello')",
            "lastMsgTime": 1710000003000,
            "unread": 2
        },
        {
            "id": "chat-2",
            "type": "group",
            "name": "项目群",
            "avatar": "group.png",
            "members": [
                {"id": "user-2", "role": "user", "name": "张三", "avatar": "user2.png"},
                {"id": "user-3", "role": "user", "name": "李四", "avatar": "user3.png"},
                {"id": "assistant-2", "role": "assistant", "name": "群助手", "avatar": "ai2.png"}
            ],
            "messages": [
                {"id": "msg-5", "role": "user", "createAt": 1710000010000, "content": "大家好！", "status": "complete"},
                {"id": "msg-6", "role": "user", "createAt": 1710000011000, "content": {"type": "file", "fileUrl": "file1.pdf", "fileName": "需求文档.pdf", "fileSize": 204800}, "status": "complete", "attachment": [
                    {"uid": "att-2", "name": "需求文档.pdf", "status": "done", "url": "file1.pdf", "size": 204800, "type": "application/pdf"}
                ]},
                {"id": "msg-7", "role": "assistant", "createAt": 1710000012000, "content": {"type": "text", "text": "收到文件，已保存。"}, "status": "complete"}
            ],
            "lastMsg": "收到文件，已保存。",
            "lastMsgTime": 1710000012000,
            "unread": 0,
            "pinned": True
        },
        {
            "id": "chat-3",
            "type": "user-agent",
            "name": "客服对话",
            "avatar": "cs.png",
            "members": [
                {"id": "user-4", "role": "user", "name": "客户A", "avatar": "user4.png"},
                {"id": "agent-1", "role": "agent", "name": "客服1", "avatar": "agent1.png"}
            ],
            "messages": [
                {"id": "msg-8", "role": "user", "createAt": 1710000020000, "content": "订单查询", "status": "complete"},
                {"id": "msg-9", "role": "agent", "createAt": 1710000021000, "content": {"type": "text", "text": "您的订单号是多少？"}, "status": "complete"},
                {"id": "msg-10", "role": "user", "createAt": 1710000022000, "content": "123456", "status": "complete"},
                {"id": "msg-11", "role": "agent", "createAt": 1710000023000, "content": {"type": "text", "text": "已为您查询到订单。"}, "status": "complete"}
            ],
            "lastMsg": "已为您查询到订单。",
            "lastMsgTime": 1710000023000,
            "unread": 1,
            "muted": True
        }
    ]
    with open(demo_path, 'w', encoding='utf-8') as f:
        json.dump(demo_data, f)

    # monkeypatch: patch ChatService.initialize to accept demo_path
    orig_initialize = ChatService.initialize
    def patched_initialize(db_path=None, import_demo=True, demo_path=None):
        service = ChatService(db_path=db_path)
        if import_demo and demo_path and os.path.exists(demo_path):
            with open(demo_path, 'r', encoding='utf-8') as f:
                demo_chats = json.load(f)
            if not service.query_chats_by_user():
                service.import_demo_chats_from_json(demo_chats)
        return service
    ChatService.initialize = staticmethod(patched_initialize)

    # 初始化服务并导入 demo
    service = ChatService.initialize(db_path=db_path, import_demo=True, demo_path=demo_path)
    chats = service.query_chats_by_user()
    assert len(chats) == 3
    assert chats[0]['id'] == 'chat-1'
    assert chats[1]['id'] == 'chat-2'
    assert chats[2]['id'] == 'chat-3'
    # 检查群聊成员
    assert len(chats[1]['members']) == 3
    # 检查附件
    assert any(msg['attachments'] for msg in chats[0]['messages'] if msg['id'] == 'msg-3')
    assert any(msg['attachments'] for msg in chats[1]['messages'] if msg['id'] == 'msg-6')
    # 检查不同类型消息
    assert any(isinstance(msg['content'], dict) and msg['content'].get('type') == 'code' for msg in chats[0]['messages'])
    assert any(isinstance(msg['content'], dict) and msg['content'].get('type') == 'file' for msg in chats[1]['messages'])
    assert chats[1]['pinned'] is True
    assert chats[2]['muted'] is True

    # 恢复原始 initialize
    ChatService.initialize = orig_initialize
    shutil.rmtree(temp_dir) 