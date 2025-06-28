/**
 * This file defines the core data structures for the chat feature,
 * based on SemiDesign's Chat component standards with added application-specific fields.
 */

/**
 * Represents a file attachment in a message.
 */
export interface Attachment {
    uid: string;      // 附件唯一标识符
    name: string;     // 附件名称
    status: string;   // 附件状态（'done', 'uploading', 'error' 等）
    url?: string;     // 附件访问链接
    size?: number;    // 附件大小（字节）
    type?: string;    // 附件MIME类型
}

/**
 * 消息状态枚举
 */
export type MessageStatus = 'loading' | 'incomplete' | 'complete' | 'error' | 'sending' | 'sent';

/**
 * Represents a single message within a chat.
 */
export interface Message {
    role: 'user' | 'assistant' | 'system' | 'agent';
    id: string;
    createAt: number;
    content: string | Content;  // 支持字符串或Content对象
    status: MessageStatus;      // 使用枚举类型
    attachments?: Attachment[]; // 统一使用 attachments 字段，匹配后端数据结构

    // 以下字段为应用内部使用，不是Semi Chat组件必需的
    chatId?: string;
    senderId?: string;
    senderName?: string;
    time?: number;
}

/**
 * Represents a chat conversation.
 */
export interface Chat {
    id: string; // Unique chat identifier
    type: 'user-system' | 'user-agent' | 'agent-agent' | 'group';
    name: string; // Display name of the chat
    avatar?: string; // URL for the chat's avatar

    members: Member[];

    messages: Message[];

    // Application-specific fields for managing chat list
    lastMsg?: string;
    lastMsgTime?: number;
    unread: number;

    // Custom fields for additional functionality
    pinned?: boolean;
    muted?: boolean;

    ext?: Record<string, any>; // For any extra data
}

/**
 * Represents a member in a chat.
 */
export interface Member {
    userId: string;
    role: string; // 与 roleConfig key 对应
    name: string;
    avatar?: string;
    status?: 'online' | 'offline' | 'busy';
    ext?: Record<string, any>;
    agentName?: string;
}

/**
 * Represents a message content.
 * 注意：此接口用于应用内部消息处理，不直接用于 Semi Chat 组件。
 * 使用 Semi Chat 组件时，应将此对象转换为 Message.content 字符串。
 */
export interface Content {
    type: 'text' | 'image' | 'file' | 'code' | 'system' | 'custom';
    text?: string;
    code?: { lang: string; value: string };
    imageUrl?: string;
    fileUrl?: string;
    fileName?: string;
    fileSize?: number;
    // 移除 attachments 字段，统一使用 Message.attachment
    [key: string]: any;
}

/**
 * Represents a role configuration item.
 */
export interface RoleConfigItem {
    name: string;
    avatar: string;
    status?: 'online' | 'offline' | 'busy';
    ext?: Record<string, any>;
}

/**
 * Semi UI Chat 组件的 Metadata 接口
 */
export interface Metadata {
    name: string;
    avatar: string;
    color?: string; // 头像背景颜色，支持 amber、blue、cyan、green 等
}

/**
 * Semi UI Chat 组件的 RoleConfig 类型
 * 使用索引签名使其与 Semi UI 的 RoleConfig 类型兼容
 */
export interface RoleConfig {
    [key: string]: Metadata; // 添加索引签名，使其与 Semi UI 兼容
    user: Metadata;
    assistant: Metadata;
    system: Metadata;
    agent: Metadata; // 添加 agent 角色，设为必需
}

export type RoleKey = string;

export const defaultRoleConfig: RoleConfig = {
    user: {
      name: '用户',
      avatar: '/src/assets/agent0_100.png',
      color: 'blue'
    },
    assistant: {
      name: 'AI助手',
      avatar: '/src/assets/icons1_100.png',
      color: 'green'
    },
    system: {
      name: '系统',
      avatar: '/src/assets/icons0_door_100.png',
      color: 'grey'
    },
    agent: {
      name: '客服代理',
      avatar: '/src/assets/icons2_100.png',
      color: 'purple'
    }
  };

/**
 * 文件信息接口
 * 用于 getFileInfo API 返回的数据
 */
export interface FileInfo {
    fileName: string;        // 文件名
    filePath: string;        // 文件路径
    fileSize: number;        // 文件大小（字节）
    fileExt: string;         // 文件扩展名
    mimeType: string;        // MIME 类型
    isImage: boolean;        // 是否为图片文件
    isText: boolean;         // 是否为文本文件
    lastModified: number;    // 最后修改时间（毫秒时间戳）
    created: number;         // 创建时间（毫秒时间戳）
}

/**
 * 文件内容接口
 * 用于 getFileContent API 返回的数据
 */
export interface FileContent {
    dataUrl: string;         // 完整的 data URL (data:mimeType;base64,base64Data)
    mimeType: string;        // MIME 类型
    fileName: string;        // 文件名
    fileSize: number;        // 文件大小（字节）
}