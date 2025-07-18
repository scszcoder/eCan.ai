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
    url?: string;     // 附件访问链接 (支持 pyqtfile:// 协议)
    size?: number;    // 附件大小（字节）
    type?: string;    // 附件MIME类型
    // 新增字段，支持 pyqtfile:// 协议
    filePath?: string;      // 文件路径，用于 pyqtfile:// 协议
    thumbnailUrl?: string;  // 缩略图URL（图片专用）
    isImage?: boolean;      // 是否为图片
    mimeType?: string;      // MIME类型
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
    content: string | Content | Content[];  // 支持字符串、单个Content对象或Content数组
    status: MessageStatus;      // 使用枚举类型
    attachments?: Attachment[]; // 统一使用 attachments 字段，匹配后端数据结构

    // 以下字段为应用内部使用，不是Semi Chat组件必需的
    chatId?: string;
    senderId?: string;
    senderName?: string;
    time?: number;
    isRead?: boolean; // 新增，表示消息是否已读
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
 * 表单字段接口
 */
export interface FormField {
    id: string;
    type: 'text' | 'number' | 'select' | 'checkbox' | 'radio' | 'textarea' | 'date' | 'password' | 'switch' | 'slider';
    label: string;
    placeholder?: string;
    required?: boolean;
    options?: { label: string; value: string | number }[];
    defaultValue?: any;
    validator?: string; // 前端无法直接传递函数，可以使用预定义的验证器名称
    selectedValue?: any; // 新增，允许表单渲染时优先使用
    // 滑动组件专用属性
    min?: number; // 最小值
    max?: number; // 最大值
    step?: number; // 步长
    unit?: string; // 单位（如：px、%、°C等）
    custom?: boolean; // 新增，支持自定义 select
}

/**
 * 卡片操作按钮接口
 */
export interface CardAction {
    text: string;
    type: 'primary' | 'secondary' | 'tertiary' | 'warning' | 'danger';
    action: string;
}

/**
 * Represents a message content.
 * 支持多种内容类型，丰富聊天体验
 */
export interface Content {
    type: 'text' | 'image_url' | 'file_url' | 'code' | 'system' | 'custom' | 'form' | 'notification' | 'card' | 'markdown' | 'table';
    text?: string;
    code?: { lang: string; value: string };
    image_url?: { url: string };
    file_url?: { url: string; name: string; size: string; type: string };
    form?: {
        id: string;
        title: string;
        fields: FormField[];
        submit_text: string;
    };
    system?: {
        text: string;
        level: 'info' | 'warning' | 'error' | 'success';
    };
    notification?: {
        title: string;
        content: string;
        level: 'info' | 'warning' | 'error' | 'success';
    };
    card?: {
        title: string;
        content: string;
        actions: CardAction[];
    };
    markdown?: string;
    table?: {
        headers: string[];
        rows: (string | number | boolean)[][];
    };
    key?: string;
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

/**
 * 优化的角色配置，更好地体现AI交互特点
 * 每个角色的avatar都经过精心选择，以表现其在AI交互中的独特作用
 */
export const defaultRoleConfig: RoleConfig = {
    user: {
      name: '用户',
      avatar: '/src/assets/icons2_100.png',
      color: 'blue'
    },
    assistant: {
      name: 'AI助手',
      avatar: '/src/assets/icons6.png', // AI助手图标 - 表现智能AI的科技感和专业性
      color: 'green'
    },
    system: {
      name: '系统',
      avatar: '/src/assets/icons5.png', // 系统图标 - 表现系统管理和控制功能，稳定可靠
      color: 'grey'
    },
    agent: {
      name: '客服代理',
      avatar: '/src/assets/icons4.png', // 客服代理图标 - 表现专业服务和支持，友好亲切
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