/**
 * Chat Page特有TypeDefinition
 * BaseType（Chat、Message、Member 等）请从 @/types/domain/chat Import
 */

// 从 domain 层ImportBaseType
export type { Chat, Message, Member, Attachment } from '@/types/domain/chat';
export { ChatType, MessageStatus, MemberStatus } from '@/types/domain/chat';

/**
 * FormFieldInterface
 */
export interface FormField {
    id: string;
    type: 'text' | 'number' | 'select' | 'checkbox' | 'checkboxes' | 'radio' | 'textarea' | 'date' | 'password' | 'switch' | 'slider';
    label: string;
    placeholder?: string;
    required?: boolean;
    options?: { label: string; value: string | number }[];
    defaultValue?: any;
    validator?: string; // Frontend无法直接传递Function，Can使用预Definition的Validate器Name
    selectedValue?: any; // 新增，AllowFormRender时优先使用
    // 滑动Component专用Property
    min?: number; // MinimumValue
    max?: number; // MaximumValue
    step?: number; // 步长
    unit?: string; // 单位（如：px、%、°C等）
    custom?: boolean; // 新增，SupportCustom select
}

/**
 * 卡片OperationButtonInterface
 */
export interface CardAction {
    text: string;
    type: 'primary' | 'secondary' | 'tertiary' | 'warning' | 'danger';
    action: string;
}

/**
 * Represents a message content.
 * Support多种ContentType，丰富聊天体验
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
 * Semi UI Chat Component的 Metadata Interface
 */
export interface Metadata {
    name: string;
    avatar: string;
    color?: string; // 头像背景颜色，Support amber、blue、cyan、green 等
}

/**
 * Semi UI Chat Component的 RoleConfig Type
 * 使用索引签名使其与 Semi UI 的 RoleConfig TypeCompatible
 */
export interface RoleConfig {
    [key: string]: Metadata; // Add索引签名，使其与 Semi UI Compatible
    user: Metadata;
    assistant: Metadata;
    system: Metadata;
    agent: Metadata; // Add agent Role，设为必需
}

export type RoleKey = string;

/**
 * Optimize的RoleConfiguration，更好地体现AI交互特点
 * 每个Role的avatar都经过精心Select，以表现其在AI交互中的独特作用
 */
export const defaultRoleConfig: RoleConfig = {
    user: {
      name: 'User',
      avatar: '/src/assets/icons3.png',
      color: 'blue'
    },
    assistant: {
      name: 'AI助手',
      avatar: '/src/assets/icons6.png', // AI助手图标 - 表现智能AI的科技感和专业性
      color: 'green'
    },
    system: {
      name: 'System',
      avatar: '/src/assets/icons5.png', // System图标 - 表现System管理和控制功能，StableReliable
      color: 'grey'
    },
    agent: {
      name: '客服代理',
      avatar: '/src/assets/icons4.png', // 客服代理图标 - 表现专业Service和Support，友好亲切
      color: 'purple'
    }
};

/**
 * 文件InformationInterface
 * Used for getFileInfo API 返回的Data
 */
export interface FileInfo {
    fileName: string;        // 文件名
    filePath: string;        // 文件Path
    fileSize: number;        // 文件Size（字节）
    fileExt: string;         // 文件Extended名
    mimeType: string;        // MIME Type
    isImage: boolean;        // 是否为图片文件
    isText: boolean;         // 是否为文本文件
    lastModified: number;    // 最后修改Time（毫秒Time戳）
    created: number;         // CreateTime（毫秒Time戳）
}

/**
 * 文件ContentInterface
 * Used for getFileContent API 返回的Data
 */
export interface FileContent {
    dataUrl: string;         // 完整的 data URL (data:mimeType;base64,base64Data)
    mimeType: string;        // MIME Type
    fileName: string;        // 文件名
    fileSize: number;        // 文件Size（字节）
}