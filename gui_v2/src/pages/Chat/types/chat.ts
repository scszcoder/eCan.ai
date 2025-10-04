/**
 * Chat 页面特有类型定义
 * 基础类型（Chat、Message、Member 等）请从 @/types/domain/chat 导入
 */

// 从 domain 层导入基础类型
export type { Chat, Message, Member, Attachment } from '@/types/domain/chat';
export { ChatType, MessageStatus, MemberStatus } from '@/types/domain/chat';

/**
 * 表单字段接口
 */
export interface FormField {
    id: string;
    type: 'text' | 'number' | 'select' | 'checkbox' | 'checkboxes' | 'radio' | 'textarea' | 'date' | 'password' | 'switch' | 'slider';
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
      avatar: '/src/assets/icons3.png',
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