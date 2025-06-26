# IM/群聊后端数据库与接口架构说明（2024新版）

本系统为高质量 IM/群聊后端，前后端 schema 严格对齐，采用现代 ORM 设计，接口极简、返回标准化。

## 数据库核心表结构

- **Chat**：会话表
  - id (string, 主键)
  - type (string)
  - name (string)
  - avatar (string)
  - lastMsg (string)
  - lastMsgTime (int)
  - unread (int)  # 未读数
  - pinned (bool)
  - muted (bool)
  - ext (JSON)

- **Member**：成员表
  - chat_id (string, 主键1)
  - user_id (string, 主键2)
  - role (string)
  - name (string)
  - avatar (string)
  - status (string)
  - ext (JSON)
  - agentName (string)

- **Message**：消息表
  - id (string, 主键)
  - chat_id (string, 外键)
  - role (string)
  - createAt (int)
  - content (JSON)
  - status (string)
  - senderId (string)
  - senderName (string)
  - time (int)
  - ext (JSON)
  - is_read (bool)  # 是否已读

- **Attachment**：附件表
  - uid (string, 主键)
  - message_id (string, 外键)
  - name (string)
  - status (string)
  - url (string)
  - size (int)
  - type (string)
  - ext (JSON)

## 主要接口说明

### 1. 创建会话
```python
resp = chat_service.create_chat(
    members=[{"user_id": "user-1", "role": "user"}, {"user_id": "assistant-1", "role": "assistant"}],
    name="AI助手对话"
)
# 返回: {"success": True, "id": chat_id, "data": {...}, "error": None}
```

### 2. 添加消息
```python
resp = chat_service.add_message(
    chat_id=chat_id,
    role="user",
    content={"type": "text", "text": "你好"},
    senderId="user-1",
    createAt=1710000000000
)
# 自动 chat.unread+1，消息 is_read=False
```

### 3. 查询用户会话
```python
resp = chat_service.query_chats_by_user(user_id="user-1")
# 返回: {"success": True, "data": [chat, ...], ...}
```

### 4. 查询会话消息
```python
resp = chat_service.query_messages_by_chat(chat_id=chat_id, limit=20, offset=0)
# 返回: {"success": True, "data": [msg, ...], ...}
```

### 5. 批量标记消息为已读
```python
resp = chat_service.mark_message_as_read(message_ids=["msg-1", "msg-2"], user_id="user-1")
# 自动 chat.unread-2，消息 is_read=True
```

### 6. 删除会话
```python
resp = chat_service.delete_chat(chat_id=chat_id)
```

## 设计要点
- 所有 id 为 string，content/ext 为 JSON
- 所有 ORM 支持递归 to_dict 序列化
- 接口参数极简，返回结构标准化
- 自动查重、错误处理、数据库初始化
- 支持自动导入/导出 UI 格式数据
- 已读未读机制：add_message 自动 unread+1，mark_message_as_read 自动 unread-1

## 示例返回结构
```json
{
  "success": true,
  "id": "chat-000001",
  "data": { ... },
  "error": null
}
```

---

如需更多接口示例或 schema 说明，请查阅源码或前端 schema 文档。 