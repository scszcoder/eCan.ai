# 聊天系统数据库使用说明

本文档提供了聊天系统数据库模型的使用说明和示例代码。

## 目录
- [服务层使用](#服务层使用)
- [基本使用](#基本使用)
- [会话管理](#会话管理)
- [消息处理](#消息处理)
- [事务管理](#事务管理)
- [附件处理](#附件处理)
- [消息状态管理](#消息状态管理)
- [注意事项](#注意事项)
- [错误处理](#错误处理)

## 服务层使用

我们提供了一个 `ChatService` 类来简化数据库操作。这是推荐的使用方式：

```python
from .chat_service import ChatService

# 创建服务实例
chat_service = ChatService()

try:
    # 创建用户
    user = chat_service.create_user(
        username="john_doe",
        display_name="John Doe",
        avatar_url="https://example.com/avatar.jpg"
    )

    # 创建会话
    conversation = chat_service.create_conversation(
        name="Team Chat",
        is_group=True,
        description="Team discussion group"
    )

    # 添加用户到会话
    chat_service.add_user_to_conversation(
        conversation_id=conversation.id,
        user_id=user.id,
        role="admin"
    )

    # 发送消息
    message = chat_service.send_message(
        conversation_id=conversation.id,
        sender_id=user.id,
        content="Hello, team!"
    )

    # 获取会话消息
    messages = chat_service.get_conversation_messages(
        conversation_id=conversation.id,
        limit=50
    )

    # 标记消息为已读
    chat_service.mark_message_as_read(
        message_id=message.id,
        user_id=user.id
    )

except Exception as e:
    print(f"Error: {str(e)}")
finally:
    del chat_service  # 确保会话被关闭
```

### 服务层主要功能

1. 用户管理
   - 创建用户
   - 获取用户信息
   - 更新用户信息
   - 删除用户

2. 会话管理
   - 创建会话
   - 获取会话信息
   - 添加/移除会话成员
   - 获取用户的所有会话

3. 消息管理
   - 发送消息
   - 获取会话消息
   - 编辑消息
   - 删除消息
   - 获取未读消息

4. 附件管理
   - 添加附件
   - 获取消息附件

5. 状态管理
   - 更新消息状态
   - 标记消息已读
   - 管理会话状态

### 事务管理

服务层自动处理事务，所有修改操作都在事务中执行：

```python
# 事务会自动处理
chat_service.create_user(username="john", display_name="John Doe")

# 如果需要手动控制事务
with chat_service.transaction() as session:
    # 执行多个操作
    user = ChatUser.create(session, username="john", display_name="John Doe")
    conversation = Conversation.create(session, name="Chat with John")
```

## 基本使用

### 1.1 获取服务实例

```python
from agent.chats.chat_service import ChatService

# 获取单例实例
chat_service = ChatService()
```

### 1.2 用户管理

```python
# 创建用户
user = chat_service.create_user(
    username="john_doe",
    display_name="John Doe",
    avatar_url="https://example.com/avatar.jpg"
)

# 获取用户信息
user = chat_service.get_user(user_id=1)
user = chat_service.get_user_by_username("john_doe")

# 更新用户信息
updated_user = chat_service.update_user(
    user_id=1,
    display_name="John Updated",
    avatar_url="https://example.com/new_avatar.jpg"
)

# 删除用户
success = chat_service.delete_user(user_id=1)
```

### 1.3 会话管理

```python
# 创建会话
conversation = chat_service.create_conversation(
    name="Team Chat",
    is_group=True,
    description="Team discussion group"
)

# 获取会话信息
conversation = chat_service.get_conversation(conversation_id=1)

# 获取用户的所有会话
conversations = chat_service.get_user_conversations(user_id=1)

# 添加用户到会话
member = chat_service.add_user_to_conversation(
    conversation_id=1,
    user_id=1,
    role="admin"  # 可选角色：admin, moderator, member
)

# 从会话中移除用户
success = chat_service.remove_user_from_conversation(
    conversation_id=1,
    user_id=1
)
```

### 1.4 消息管理

```python
# 发送消息
message = chat_service.send_message(
    conversation_id=1,
    sender_id=1,
    content="Hello, team!",
    message_type=MessageType.TEXT,  # 可选类型：TEXT, IMAGE, FILE, SYSTEM
    parent_id=None  # 可选，用于回复消息
)

# 获取会话消息
messages = chat_service.get_conversation_messages(
    conversation_id=1,
    limit=50,  # 每页消息数
    offset=0   # 分页偏移量
)

# 编辑消息
updated_message = chat_service.edit_message(
    message_id=1,
    content="Updated message content"
)

# 删除消息
success = chat_service.delete_message(message_id=1)
```

### 1.5 附件管理

```python
# 添加附件
attachment = chat_service.add_attachment(
    message_id=1,
    file_name="document.pdf",
    file_size=1024,
    mime_type="application/pdf",
    file_path="/path/to/document.pdf"
)

# 获取消息的所有附件
attachments = chat_service.get_message_attachments(message_id=1)
```

### 1.6 消息状态管理

```python
# 更新消息状态
message = chat_service.update_message_status(
    message_id=1,
    status=MessageStatus.DELIVERED  # 可选状态：SENT, DELIVERED, READ
)

# 标记消息为已读
read_status = chat_service.mark_message_as_read(
    message_id=1,
    user_id=1
)

# 获取未读消息
unread_messages = chat_service.get_unread_messages(
    user_id=1,
    conversation_id=1
)
```

### 1.7 会话状态管理

```python
# 获取活跃会话
active_session = chat_service.get_active_session(conversation_id=1)

# 结束会话
success = chat_service.end_session(session_id=1)
```

## 2. 多线程使用

```python
import threading
from agent.chats.chat_service import ChatService

def worker(thread_id):
    # 获取单例实例
    chat_service = ChatService()
    
    try:
        # 创建用户
        user = chat_service.create_user(
            username=f"user_{thread_id}",
            display_name=f"User {thread_id}"
        )
        
        # 创建会话
        conversation = chat_service.create_conversation(
            name=f"Thread {thread_id} Chat",
            is_group=True
        )
        
        # 发送消息
        message = chat_service.send_message(
            conversation_id=conversation.id,
            sender_id=user.id,
            content=f"Message from thread {thread_id}"
        )
        
    except Exception as e:
        print(f"Thread {thread_id} error: {str(e)}")

# 创建多个线程
threads = []
for i in range(5):
    thread = threading.Thread(target=worker, args=(i,))
    threads.append(thread)
    thread.start()

# 等待所有线程完成
for thread in threads:
    thread.join()
```

## 3. 错误处理

所有方法都可能抛出以下异常：

- `ValueError`: 参数验证失败
- `RuntimeError`: 数据库操作失败
- `Exception`: 其他未预期的错误

建议使用 try-except 进行错误处理：

```python
try:
    user = chat_service.create_user(
        username="john_doe",
        display_name="John Doe"
    )
except ValueError as e:
    print(f"参数错误: {str(e)}")
except RuntimeError as e:
    print(f"数据库错误: {str(e)}")
except Exception as e:
    print(f"未预期的错误: {str(e)}")
```

## 4. 性能注意事项

1. 会话管理
   - 服务使用单例模式，确保资源高效利用
   - 数据库会话是线程安全的，可以安全地在多线程环境中使用

2. 并发处理
   - 所有方法都是线程安全的
   - 使用锁机制确保数据一致性
   - 支持高并发访问

3. 资源清理
   - 服务实例会自动管理资源
   - 不需要手动关闭数据库会话
   - 程序退出时会自动清理资源

## 5. 最佳实践

1. 错误处理
   - 始终使用 try-except 处理可能的异常
   - 记录关键操作的错误信息

2. 资源管理
   - 不要手动创建多个服务实例
   - 让服务自动管理数据库会话

3. 并发使用
   - 在多线程环境中安全使用
   - 注意处理并发异常

4. 性能优化
   - 合理使用分页
   - 避免频繁创建和删除会话
   - 及时清理不需要的资源

## 6. 单元测试

### 6.1 测试环境设置

1. 安装依赖
```bash
pip install pytest pytest-cov
```

2. 运行测试
```bash
pytest agent/chats/tests/test_chat_service.py -v --cov=agent.chats
```

### 6.2 测试套件结构

测试套件包含以下测试类：

1. `TestUserOperations`
   - 测试用户创建、获取、更新、删除
   - 验证用户属性正确性
   - 测试用户查询功能

2. `TestConversationOperations`
   - 测试会话创建和管理
   - 验证会话成员管理
   - 测试会话查询功能

3. `TestMessageOperations`
   - 测试消息发送和接收
   - 验证消息编辑和删除
   - 测试消息查询功能

4. `TestAttachmentOperations`
   - 测试附件上传和管理
   - 验证附件关联
   - 测试附件查询功能

5. `TestMessageStatusOperations`
   - 测试消息状态更新
   - 验证已读状态管理
   - 测试未读消息查询

6. `TestSessionOperations`
   - 测试会话状态管理
   - 验证会话生命周期
   - 测试会话查询功能

7. `TestConcurrency`
   - 测试并发用户创建
   - 验证并发消息发送
   - 测试线程安全性

8. `TestErrorHandling`
   - 测试无效输入处理
   - 验证错误恢复机制
   - 测试异常处理

### 6.3 测试特点

1. 使用 SQLite 内存数据库
   - 测试隔离性好
   - 执行速度快
   - 无需外部数据库

2. 完整的测试夹具（Fixtures）
   - 数据库会话管理
   - 测试数据准备
   - 资源清理

3. 并发测试
   - 多线程操作测试
   - 线程安全性验证
   - 资源竞争测试

4. 错误处理测试
   - 边界条件测试
   - 异常情况处理
   - 错误恢复验证

### 6.4 测试覆盖率

运行测试时会生成覆盖率报告，包括：
- 代码行覆盖率
- 分支覆盖率
- 函数覆盖率

### 6.5 添加新测试

1. 在 `test_chat_service.py` 中添加新的测试类或方法
2. 遵循现有的测试模式
3. 确保测试的独立性和可重复性
4. 添加适当的测试夹具

### 6.6 测试最佳实践

1. 测试独立性
   - 每个测试应该是独立的
   - 避免测试之间的依赖
   - 使用测试夹具管理状态

2. 测试数据
   - 使用有意义的测试数据
   - 覆盖边界条件
   - 包含错误情况

3. 测试命名
   - 使用描述性的测试名称
   - 清晰表达测试目的
   - 遵循命名约定

4. 测试维护
   - 定期更新测试
   - 保持测试代码质量
   - 及时修复失败的测试

## 注意事项

1. 所有数据库操作都应该在事务中进行
2. 使用完会话后要记得关闭
3. 消息有编辑时间限制（默认5分钟）
4. 会话有超时时间（默认15分钟）
5. 消息数量有限制（每个会话1000条，全局10000条）

## 错误处理

```python
try:
    with ChatUser.session_scope(session) as s:
        # 数据库操作
        pass
except Exception as e:
    # 处理错误
    print(f"Error: {str(e)}")
finally:
    session.close()
```

## 数据库配置

数据库配置可以通过环境变量 `DATABASE_URL` 来设置，默认使用 SQLite：

```python
# 默认配置
DATABASE_URL = 'sqlite:///chat_app.db'

# PostgreSQL 示例
DATABASE_URL = 'postgresql://user:password@localhost:5432/chat_db'

# MySQL 示例
DATABASE_URL = 'mysql://user:password@localhost:3306/chat_db'
```

## 初始化数据库

```python
from .chats_db import init_chats_db

# 初始化数据库（创建所有表）
init_chats_db()
``` 