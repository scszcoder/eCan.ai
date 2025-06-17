import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from agent.chats.chats_db import (
    Base, ChatUser, Conversation, Message, ChatSession,
    ConversationMember, Attachment, MessageRead,
    MessageType, MessageStatus, init_chats_db, get_engine, DBVersion
)
from agent.chats.chat_service import ChatService
import threading
import time
import os
import shutil
import tempfile
import uuid
from agent.chats.entity import Base
from sqlalchemy.exc import IntegrityError


def init_db(engine):
    """初始化数据库，确保所有模型都被正确注册"""
    # 确保所有模型都被导入和注册
    from agent.chats.chats_db import (
        ChatUser, Conversation, Message, ChatSession,
        ConversationMember, Attachment, MessageRead
    )
    
    # 创建所有表
    Base.metadata.drop_all(engine)  # 先删除所有表
    Base.metadata.create_all(engine)  # 然后重新创建所有表


def cleanup_db(engine):
    """清理数据库"""
    Base.metadata.drop_all(engine)


@pytest.fixture(scope="session")
def temp_dir():
    """创建临时目录用于测试文件"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # 测试完成后清理临时目录
    shutil.rmtree(temp_dir)


@pytest.fixture(scope="session")
def db_engine():
    """创建测试数据库引擎"""
    db_path = 'test_chat.db'
    engine = create_engine(f'sqlite:///{db_path}', connect_args={'check_same_thread': False})
    init_chats_db(db_path)  # 使用 init_chats_db 初始化数据库
    yield engine
    Base.metadata.drop_all(engine)
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def custom_db_path(temp_dir):
    """创建自定义数据库路径"""
    db_path = os.path.join(temp_dir, f'test_db_{uuid.uuid4().hex[:8]}.db')
    yield db_path
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="function")
def db_session(db_engine):
    """创建测试数据库会话"""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def chat_service(db_engine, db_session):
    """创建聊天服务实例"""
    service = ChatService(engine=db_engine)
    return service


@pytest.fixture(scope="function")
def custom_chat_service(custom_db_path):
    """创建使用自定义数据库路径的聊天服务实例"""
    service = ChatService.initialize(db_path=custom_db_path)
    return service


@pytest.fixture(scope="function")
def test_user(db_session):
    """创建测试用户，每次生成唯一用户名"""
    unique_username = f"test_user_{uuid.uuid4().hex[:8]}"
    user = ChatUser(
        username=unique_username,
        display_name="Test User",
        avatar_url="https://example.com/avatar.jpg"
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture(scope="function")
def test_conversation(db_session, test_user):
    """创建测试会话并自动将 test_user 加入会话"""
    conversation = Conversation(
        name="Test Conversation",
        is_group=False
    )
    db_session.add(conversation)
    db_session.commit()
    # 自动将 test_user 加入会话
    from agent.chats.chats_db import ConversationMember
    member = ConversationMember(
        conversation_id=conversation.id,
        user_id=test_user.id,
        role="member"
    )
    db_session.add(member)
    db_session.commit()
    return conversation


class TestUserOperations:
    """测试用户相关操作"""

    def test_create_user(self, chat_service, temp_dir):
        """测试创建用户"""
        user = chat_service.create_user(
            username="new_user",
            display_name="New User",
            avatar_url="https://example.com/avatar.jpg"
        )
        assert user is not None
        assert user.username == "new_user"
        assert user.display_name == "New User"
        assert user.avatar_url == "https://example.com/avatar.jpg"

    def test_get_user(self, chat_service, test_user):
        """测试获取用户"""
        user = chat_service.get_user(test_user.id)
        assert user is not None
        assert user.id == test_user.id
        assert user.username == test_user.username

    def test_get_user_by_username(self, chat_service, test_user):
        """测试通过用户名获取用户"""
        user = chat_service.get_user_by_username(test_user.username)
        assert user is not None
        assert user.id == test_user.id

    def test_update_user(self, chat_service, test_user):
        """测试更新用户信息"""
        updated_user = chat_service.update_user(
            test_user.id,
            display_name="Updated Name",
            avatar_url="https://example.com/updated_avatar.jpg"
        )
        assert updated_user is not None
        assert updated_user.display_name == "Updated Name"
        assert updated_user.avatar_url == "https://example.com/updated_avatar.jpg"

    def test_delete_user(self, chat_service, test_user):
        """测试删除用户"""
        success = chat_service.delete_user(test_user.id)
        assert success is True
        deleted_user = chat_service.get_user(test_user.id)
        assert deleted_user is None


class TestConversationOperations:
    """测试会话相关操作"""

    def test_create_conversation(self, chat_service):
        """测试创建会话"""
        conversation = chat_service.create_conversation(
            name="New Conversation",
            is_group=True,
            description="New group chat"
        )
        assert conversation is not None
        assert conversation.name == "New Conversation"
        assert conversation.is_group is True
        assert conversation.description == "New group chat"

    def test_get_conversation(self, chat_service, test_conversation):
        """测试获取会话"""
        conversation = chat_service.get_conversation(test_conversation.id)
        assert conversation is not None
        assert conversation.id == test_conversation.id

    def test_get_user_conversations(self, chat_service, test_user, test_conversation):
        """测试获取用户的所有会话"""
        conversations = chat_service.get_user_conversations(test_user.id)
        assert len(conversations) > 0
        assert any(c.id == test_conversation.id for c in conversations)

    def test_add_user_to_conversation(self, chat_service, test_conversation):
        """测试添加用户到会话"""
        new_user = chat_service.create_user(
            username="new_member",
            display_name="New Member"
        )
        member = chat_service.add_user_to_conversation(
            conversation_id=test_conversation.id,
            user_id=new_user.id,
            role="member"
        )
        assert member is not None
        assert member.conversation_id == test_conversation.id
        assert member.user_id == new_user.id
        assert member.role == "member"

    def test_remove_user_from_conversation(self, chat_service, test_conversation, test_user):
        """测试从会话中移除用户"""
        success = chat_service.remove_user_from_conversation(
            test_conversation.id,
            test_user.id
        )
        assert success is True
        conversations = chat_service.get_user_conversations(test_user.id)
        assert not any(c.id == test_conversation.id for c in conversations)


class TestMessageOperations:
    """测试消息相关操作"""

    def test_send_message(self, chat_service, test_conversation, test_user, db_session):
        """测试发送消息"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Test message",
            message_type=MessageType.TEXT
        )
        assert message is not None
        assert message.content == "Test message"
        assert message.sender_id == test_user.id
        assert message.conversation_id == test_conversation.id

    def test_get_conversation_messages(self, chat_service, test_conversation, test_user, db_session):
        """测试获取会话消息"""
        # 先发送一些消息
        for i in range(3):
            chat_service.send_message(
                conversation_id=test_conversation.id,
                sender_id=test_user.id,
                content=f"Message {i}",
                message_type=MessageType.TEXT
            )

        messages = chat_service.get_conversation_messages(test_conversation.id)
        assert len(messages) == 3
        assert all(m.conversation_id == test_conversation.id for m in messages)

    def test_edit_message(self, chat_service, test_conversation, test_user, db_session):
        """测试编辑消息"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Original message",
            message_type=MessageType.TEXT
        )

        edited_message = chat_service.edit_message(
            message_id=message.id,
            content="Edited message"
        )
        assert edited_message.content == "Edited message"
        assert edited_message.is_edited

    def test_delete_message(self, chat_service, test_conversation, test_user, db_session):
        """测试删除消息"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Message to delete",
            message_type=MessageType.TEXT
        )

        chat_service.delete_message(message.id)
        deleted_message = db_session.get(Message, message.id)
        assert deleted_message is None


class TestAttachmentOperations:
    """测试附件相关操作"""

    def test_add_attachment(self, chat_service, test_conversation, test_user, db_session):
        """测试添加附件"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Message with attachment",
            message_type=MessageType.TEXT
        )

        attachment = chat_service.add_attachment(
            message_id=message.id,
            file_name="test.txt",
            file_size=1024,
            mime_type="text/plain",
            file_path="/path/to/test.txt"
        )
        assert attachment.message_id == message.id
        assert attachment.file_name == "test.txt"

    def test_get_message_attachments(self, chat_service, test_conversation, test_user, db_session):
        """测试获取消息附件"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Message with attachments",
            message_type=MessageType.TEXT
        )

        # 添加多个附件
        for i in range(3):
            chat_service.add_attachment(
                message_id=message.id,
                file_name=f"test_{i}.txt",
                file_size=1024,
                mime_type="text/plain",
                file_path=f"/path/to/test_{i}.txt"
            )

        attachments = chat_service.get_message_attachments(message.id)
        assert len(attachments) == 3


class TestMessageStatusOperations:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.chat_service = ChatService(engine=self.engine)
        yield

    def test_update_message_status(self, chat_service, test_conversation, test_user, db_session):
        """测试更新消息状态"""
        message = chat_service.send_message(
            conversation_id=test_conversation.id,
            sender_id=test_user.id,
            content="Test message",
            message_type=MessageType.TEXT
        )

        updated_message = chat_service.update_message_status(
            message_id=message.id,
            status=MessageStatus.DELIVERED
        )
        assert updated_message.status == MessageStatus.DELIVERED

    def test_mark_message_as_read(self):
        conversation = self.chat_service.create_conversation("Test Chat")
        user = self.chat_service.create_user("test_user", "Test User")
        message = self.chat_service.send_message(conversation.id, user.id, "Test message")
        self.chat_service.mark_message_as_read(message.id, user.id)
        # 验证已读
        session = self.chat_service._get_session()
        read_status = session.query(MessageRead).filter_by(message_id=message.id, user_id=user.id).first()
        assert read_status is not None

    def test_get_unread_messages(self, chat_service, test_conversation, test_user, db_session):
        """测试获取未读消息"""
        # 发送多条消息
        for i in range(3):
            chat_service.send_message(
                conversation_id=test_conversation.id,
                sender_id=test_user.id,
                content=f"Message {i}",
                message_type=MessageType.TEXT
            )

        unread_messages = chat_service.get_unread_messages(
            conversation_id=test_conversation.id,
            user_id=test_user.id
        )
        assert len(unread_messages) == 3


class TestSessionOperations:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.username = f"session_user_{uuid.uuid4()}"
        self.chat_service = ChatService(engine=self.engine)
        self.user = self.chat_service.create_user(self.username, "Session User")
        self.conversation = self.chat_service.create_conversation("Session Test")
        yield

    def test_get_active_session(self):
        session = self.chat_service.get_active_session(self.conversation.id)
        assert session is not None

    def test_end_session(self):
        session = self.chat_service.get_active_session(self.conversation.id)
        self.chat_service.end_session(session.id)
        # 断言session已结束
        session2 = self.chat_service.get_active_session(self.conversation.id)
        assert session2 is not None
        assert session2.id != session.id


class TestConcurrency:
    """测试并发操作"""

    def test_concurrent_user_creation(self, db_engine):
        """测试并发创建用户"""
        def create_user(thread_id):
            # 为每个线程创建独立的会话
            Session = sessionmaker(bind=db_engine)
            session = Session()
            try:
                user = ChatUser(
                    username=f"user_{thread_id}",
                    display_name=f"User {thread_id}",
                    avatar_url=f"https://example.com/avatar_{thread_id}.jpg"
                )
                session.add(user)
                session.commit()
                return user
            except Exception as e:
                print(f"Thread {thread_id} failed: {str(e)}")
                session.rollback()
                return None
            finally:
                session.close()

        threads = []
        results = []
        for i in range(5):
            thread = threading.Thread(target=lambda: results.append(create_user(i)))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5)

        successful_users = [r for r in results if r is not None]
        assert len(successful_users) > 0, "No users were created successfully"

    def test_concurrent_message_sending(self, db_engine, test_conversation, test_user):
        """测试并发发送消息"""
        def send_message(thread_id):
            # 为每个线程创建独立的会话
            Session = sessionmaker(bind=db_engine)
            session = Session()
            try:
                message = Message(
                    conversation_id=test_conversation.id,
                    sender_id=test_user.id,
                    content=f"Message from thread {thread_id}",
                    message_type=MessageType.TEXT
                )
                session.add(message)
                session.commit()
                return message
            except Exception as e:
                print(f"Thread {thread_id} failed: {str(e)}")
                session.rollback()
                return None
            finally:
                session.close()

        threads = []
        results = []
        for i in range(5):
            thread = threading.Thread(target=lambda: results.append(send_message(i)))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5)

        successful_messages = [r for r in results if r is not None]
        assert len(successful_messages) > 0, "No messages were sent successfully"


class TestErrorHandling:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.chat_service = ChatService(engine=self.engine)
        yield

    def test_invalid_user_id(self):
        user = self.chat_service.get_user(99999)
        assert user is None

    def test_invalid_conversation_id(self):
        conv = self.chat_service.get_conversation(99999)
        assert conv is None

    def test_invalid_message_id(self):
        messages = self.chat_service.get_conversation_messages(99999)
        assert messages == []

    def test_duplicate_username(self):
        # Use a unique username to avoid conflicts with other tests
        unique_username = f"test_user_{uuid.uuid4().hex[:8]}"
        
        # Create first user
        user1 = self.chat_service.create_user(unique_username, "Test User")
        assert user1 is not None
        
        # Try to create second user with same username
        with pytest.raises(IntegrityError):
            self.chat_service.create_user(unique_username, "Another User")
            
        # Verify first user still exists
        user = self.chat_service.get_user_by_username(unique_username)
        assert user is not None
        assert user.id == user1.id

    def test_chat_operations(self):
        conversation = self.chat_service.create_conversation("Test Chat")
        user = self.chat_service.create_user("test_user2", "Test User2")
        message = self.chat_service.send_message(conversation.id, user.id, "Hello, this is a test message")
        assert message is not None
        history = self.chat_service.get_conversation_messages(conversation.id)
        assert len(history) == 1
        assert history[0].content == "Hello, this is a test message"

    def test_delete_message(self):
        conversation = self.chat_service.create_conversation("Test Chat")
        user = self.chat_service.create_user("test_user3", "Test User3")
        message = self.chat_service.send_message(conversation.id, user.id, "Test message to delete")
        result = self.chat_service.delete_message(message.id)
        assert result is True
        history = self.chat_service.get_conversation_messages(conversation.id)
        assert all(msg.id != message.id for msg in history)


class TestDatabaseConfiguration:
    """测试数据库配置相关功能"""

    def test_custom_db_path(self, custom_db_path):
        """测试使用自定义数据库路径"""
        # 创建使用自定义路径的服务实例
        service = ChatService.initialize(db_path=custom_db_path)
        
        # 验证数据库文件已创建
        assert os.path.exists(custom_db_path)
        
        # 测试基本功能
        user = service.create_user(
            username="test_user",
            display_name="Test User"
        )
        assert user is not None
        assert user.username == "test_user"

    def test_multiple_db_instances(self, temp_dir):
        """测试多个数据库实例"""
        # 创建两个不同的数据库路径
        db_path1 = os.path.join(temp_dir, 'db1.db')
        db_path2 = os.path.join(temp_dir, 'db2.db')
        
        # 创建两个服务实例
        service1 = ChatService.initialize(db_path=db_path1)
        service2 = ChatService.initialize(db_path=db_path2)
        
        # 在每个数据库中创建用户
        user1 = service1.create_user(username="user1", display_name="User 1")
        user2 = service2.create_user(username="user2", display_name="User 2")
        
        # 验证数据隔离
        assert service1.get_user_by_username("user1") is not None
        assert service1.get_user_by_username("user2") is None
        assert service2.get_user_by_username("user2") is not None
        assert service2.get_user_by_username("user1") is None

    def test_db_path_persistence(self, custom_db_path):
        """测试数据库路径持久化"""
        # 创建服务实例并添加数据
        service = ChatService.initialize(db_path=custom_db_path)
        user = service.create_user(username="persistent_user", display_name="Persistent User")
        
        # 创建新的服务实例，使用相同的数据库路径
        new_service = ChatService.initialize(db_path=custom_db_path)
        
        # 验证数据持久化
        retrieved_user = new_service.get_user_by_username("persistent_user")
        assert retrieved_user is not None
        assert retrieved_user.id == user.id 


class TestDBVersion:
    """测试数据库版本管理表"""

    def test_db_version_init(self, db_engine):
        """测试初始化时版本表存在且为1.0.0"""
        Session = sessionmaker(bind=db_engine)
        session = Session()
        version = session.query(DBVersion).order_by(DBVersion.upgraded_at.desc()).first()
        assert version is not None
        assert version.version == "1.0.0"
        session.close()

    def test_db_version_upgrade(self, db_engine):
        """测试升级数据库版本"""
        Session = sessionmaker(bind=db_engine)
        session = Session()
        # 升级到2.0.0
        DBVersion.upgrade_version(session, "2.0.0", description="升级到2.0.0")
        version = DBVersion.get_current_version(session)
        assert version.version == "2.0.0"
        assert version.description == "升级到2.0.0"
        session.close() 