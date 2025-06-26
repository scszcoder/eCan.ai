-- IM/群聊后端数据库结构（2024新版）

-- 会话表
CREATE TABLE IF NOT EXISTS chats (
    id VARCHAR(64) PRIMARY KEY,
    type VARCHAR(32) NOT NULL,
    name VARCHAR(100) NOT NULL,
    avatar VARCHAR(255),
    lastMsg TEXT,
    lastMsgTime INTEGER,
    unread INTEGER DEFAULT 0,
    pinned BOOLEAN DEFAULT 0,
    muted BOOLEAN DEFAULT 0,
    ext JSON
);

-- 成员表
CREATE TABLE IF NOT EXISTS members (
    chat_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    name VARCHAR(100) NOT NULL,
    avatar VARCHAR(255),
    status VARCHAR(16),
    ext JSON,
    agentName VARCHAR(100),
    PRIMARY KEY (chat_id, user_id),
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

-- 消息表
CREATE TABLE IF NOT EXISTS messages (
    id VARCHAR(64) PRIMARY KEY,
    chat_id VARCHAR(64) NOT NULL,
    role VARCHAR(32) NOT NULL,
    createAt INTEGER NOT NULL,
    content JSON NOT NULL,
    status VARCHAR(16) NOT NULL,
    senderId VARCHAR(64),
    senderName VARCHAR(100),
    time INTEGER,
    ext JSON,
    is_read BOOLEAN DEFAULT 0,
    FOREIGN KEY (chat_id) REFERENCES chats(id)
);

-- 附件表
CREATE TABLE IF NOT EXISTS attachments (
    uid VARCHAR(64) PRIMARY KEY,
    message_id VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL,
    url VARCHAR(512),
    size INTEGER,
    type VARCHAR(64),
    ext JSON,
    FOREIGN KEY (message_id) REFERENCES messages(id)
); 