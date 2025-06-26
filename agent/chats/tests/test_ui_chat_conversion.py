import pytest
import os
import tempfile
import json
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from agent.chats.chats_db import (
    Base, ChatUser, Conversation, Message, ChatSession,
    ConversationMember, Attachment, MessageRead,
    MessageType, MessageStatus
)
from agent.chats.chat_service import ChatService


@pytest.fixture(scope="function")
def db_engine():
    """创建内存数据库引擎"""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="function")
def db_session(db_engine):
    """创建数据库会话"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def chat_service(db_engine):
    """创建聊天服务实例"""
    service = ChatService(engine=db_engine)
    return service


@pytest.fixture(scope="function")
def sample_data(chat_service):
    """创建测试数据"""
    # 创建用户
    user1 = chat_service.create_user(
        username="user1",
        display_name="User One",
        avatar_url="/assets/user1.png"
    )
    user1.role = "user"
    
    user2 = chat_service.create_user(
        username="assistant1",
        display_name="AI Assistant",
        avatar_url="/assets/assistant1.png"
    )
    user2.role = "assistant"
    
    user3 = chat_service.create_user(
        username="agent1",
        display_name="Agent One",
        avatar_url="/assets/agent1.png"
    )
    user3.role = "agent"
    
    # 创建会话
    conv1 = chat_service.create_conversation(
        name="Test Chat 1",
        is_group=False,
        description="One-on-one chat"
    )
    
    conv2 = chat_service.create_conversation(
        name="Group Discussion",
        is_group=True,
        description="Group chat for testing"
    )
    
    # 添加成员到会话
    chat_service.add_user_to_conversation(conv1.id, user1.id, "member")
    chat_service.add_user_to_conversation(conv1.id, user2.id, "assistant")
    
    chat_service.add_user_to_conversation(conv2.id, user1.id, "member")
    chat_service.add_user_to_conversation(conv2.id, user2.id, "assistant")
    chat_service.add_user_to_conversation(conv2.id, user3.id, "agent")
    
    # 发送消息
    msg1 = chat_service.send_message(
        conversation_id=conv1.id,
        sender_id=user1.id,
        content="Hello, AI!",
        message_type=MessageType.TEXT
    )
    
    msg2 = chat_service.send_message(
        conversation_id=conv1.id,
        sender_id=user2.id,
        content="Hello! How can I help you today?",
        message_type=MessageType.TEXT
    )
    
    # 发送带附件的消息
    msg3 = chat_service.send_message(
        conversation_id=conv2.id,
        sender_id=user1.id,
        content="Check out this image",
        message_type=MessageType.TEXT
    )
    
    # 添加附件
    attachment = Attachment(
        message_id=msg3.id,
        file_name="test_image.jpg",
        file_size=1024,
        mime_type="image/jpeg",
        file_path="/path/to/test_image.jpg"
    )
    chat_service._session.add(attachment)
    
    # 发送代码消息
    code_content = json.dumps({
        "lang": "python",
        "value": "print('Hello, World!')"
    })
    msg4 = chat_service.send_message(
        conversation_id=conv2.id,
        sender_id=user2.id,
        content=code_content,
        message_type=MessageType.TEXT  # 使用TEXT类型，因为我们在导出时会特殊处理
    )
    
    chat_service._session.commit()
    
    return {
        "users": [user1, user2, user3],
        "conversations": [conv1, conv2],
        "messages": [msg1, msg2, msg3, msg4]
    }


class TestUIChatConversion:
    """测试UI聊天数据转换功能"""
    
    def test_export_chats_for_ui(self, chat_service, sample_data):
        """测试导出聊天数据为UI格式"""
        # 导出所有会话
        ui_chats = chat_service.export_chats_for_ui()
        
        # 验证基本结构
        assert isinstance(ui_chats, list)
        assert len(ui_chats) == 2  # 应该有两个会话
        
        # 验证第一个会话
        chat1 = ui_chats[0]
        assert chat1["id"] == str(sample_data["conversations"][0].id)
        assert chat1["name"] == "Test Chat 1"
        assert chat1["type"] == "user-agent"  # 非群组会话
        assert len(chat1["members"]) == 2
        assert len(chat1["messages"]) == 2
        
        # 验证第二个会话
        chat2 = ui_chats[1]
        assert chat2["id"] == str(sample_data["conversations"][1].id)
        assert chat2["name"] == "Group Discussion"
        assert chat2["type"] == "group"  # 群组会话
        assert len(chat2["members"]) == 3
        assert len(chat2["messages"]) == 2
        
        # 验证消息格式
        message = chat1["messages"][0]
        assert "id" in message
        assert "role" in message
        assert "createAt" in message
        assert "content" in message
        assert "status" in message
        
        # 验证附件
        has_attachment = False
        for chat in ui_chats:
            for message in chat["messages"]:
                if "attachment" in message and message["attachment"]:
                    has_attachment = True
                    attachment = message["attachment"][0]
                    assert "uid" in attachment
                    assert "name" in attachment
                    assert "status" in attachment
                    assert attachment["name"] == "test_image.jpg"
        
        assert has_attachment, "附件应该被正确导出"
        
        # 验证代码消息
        has_code = False
        for chat in ui_chats:
            for message in chat["messages"]:
                content = message["content"]
                if isinstance(content, dict) and "code" in content:
                    has_code = True
                    assert content["code"]["lang"] == "python"
                    assert "print('Hello, World!')" in content["code"]["value"]
        
        assert has_code, "代码消息应该被正确处理"
    
    def test_export_user_specific_chats(self, chat_service, sample_data):
        """测试导出特定用户的聊天数据"""
        user1_id = sample_data["users"][0].id
        
        # 导出用户1的会话
        ui_chats = chat_service.export_chats_for_ui(user_id=user1_id)
        
        # 验证
        assert len(ui_chats) == 2  # 用户1参与了两个会话
        
        # 验证未读消息计数
        for chat in ui_chats:
            assert "unread" in chat
            assert isinstance(chat["unread"], int)
    
    def test_import_chats_from_ui(self, chat_service):
        """测试从UI格式导入聊天数据"""
        # 准备UI格式的聊天数据
        ui_chats = [
            {
                "id": "new_chat_1",  # 非数字ID，应该创建新会话
                "type": "user-agent",
                "name": "Imported Chat",
                "avatar": "/assets/imported.png",
                "members": [
                    {
                        "id": "user_new",
                        "role": "user",
                        "name": "New User",
                        "avatar": "/assets/new_user.png",
                        "agentName": "New User"
                    },
                    {
                        "id": "assistant_new",
                        "role": "assistant",
                        "name": "New Assistant",
                        "avatar": "/assets/new_assistant.png",
                        "agentName": "New Assistant"
                    }
                ],
                "messages": [
                    {
                        "id": "msg_1",
                        "role": "user",
                        "createAt": int(datetime.now().timestamp() * 1000),
                        "content": "Hello from imported chat!",
                        "status": "complete",
                        "senderId": "user_new",
                        "senderName": "New User"
                    },
                    {
                        "id": "msg_2",
                        "role": "assistant",
                        "createAt": int(datetime.now().timestamp() * 1000) + 1000,
                        "content": "Hello! I'm an imported assistant.",
                        "status": "complete",
                        "senderId": "assistant_new",
                        "senderName": "New Assistant"
                    },
                    {
                        "id": "msg_3",
                        "role": "user",
                        "createAt": int(datetime.now().timestamp() * 1000) + 2000,
                        "content": {
                            "type": "code",
                            "code": {
                                "lang": "javascript",
                                "value": "console.log('Imported code');"
                            }
                        },
                        "status": "complete",
                        "senderId": "user_new",
                        "senderName": "New User"
                    }
                ],
                "lastMsg": "Hello! I'm an imported assistant.",
                "lastMsgTime": int(datetime.now().timestamp() * 1000) + 1000,
                "unread": 0
            }
        ]
        
        # 导入聊天数据
        imported_ids = chat_service.import_chats_from_ui(ui_chats)
        
        # 验证
        assert len(imported_ids) == 1
        
        # 验证导入的会话
        imported_chat = chat_service._session.query(Conversation).filter_by(id=imported_ids[0]).first()
        assert imported_chat is not None
        assert imported_chat.name == "Imported Chat"
        
        # 验证会话成员
        members = list(imported_chat.members)
        assert len(members) == 2
        
        # 验证消息
        messages = list(imported_chat.messages)
        assert len(messages) == 3
        
        # 验证代码消息
        code_message = None
        for msg in messages:
            if "console.log" in msg.content:
                code_message = msg
                break
        
        assert code_message is not None, "代码消息应该被正确导入"
    
    def test_round_trip_conversion(self, chat_service, sample_data):
        """测试导出后再导入的往返转换"""
        # 导出
        ui_chats = chat_service.export_chats_for_ui()
        
        # 清除数据库
        chat_service._session.query(Attachment).delete()
        chat_service._session.query(Message).delete()
        chat_service._session.query(ConversationMember).delete()
        chat_service._session.query(Conversation).delete()
        chat_service._session.query(ChatUser).delete()
        chat_service._session.commit()
        
        # 导入
        imported_ids = chat_service.import_chats_from_ui(ui_chats)
        
        # 验证
        assert len(imported_ids) == 2
        
        # 再次导出
        reimported_chats = chat_service.export_chats_for_ui()
        
        # 验证基本结构保持一致
        assert len(reimported_chats) == len(ui_chats)
        
        # 验证会话名称
        original_names = [chat["name"] for chat in ui_chats]
        reimported_names = [chat["name"] for chat in reimported_chats]
        assert set(original_names) == set(reimported_names)
        
        # 验证消息数量
        original_msg_count = sum(len(chat["messages"]) for chat in ui_chats)
        reimported_msg_count = sum(len(chat["messages"]) for chat in reimported_chats)
        assert original_msg_count == reimported_msg_count 