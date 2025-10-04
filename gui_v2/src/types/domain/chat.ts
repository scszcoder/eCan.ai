/**
 * Chat Domain Types
 * 聊天相关的类型定义
 */

/**
 * 聊天类型
 */
export enum ChatType {
  USER_SYSTEM = 'user-system',
  USER_AGENT = 'user-agent',
  AGENT_AGENT = 'agent-agent',
  GROUP = 'group',
}

/**
 * 消息状态
 */
export enum MessageStatus {
  LOADING = 'loading',
  INCOMPLETE = 'incomplete',
  COMPLETE = 'complete',
  ERROR = 'error',
  SENDING = 'sending',
  SENT = 'sent',
}

/**
 * 成员状态
 */
export enum MemberStatus {
  ONLINE = 'online',
  OFFLINE = 'offline',
  BUSY = 'busy',
}

/**
 * 附件接口
 */
export interface Attachment {
  uid: string;
  name: string;
  status: string;
  url?: string;
  size?: number;
  type?: string;
  filePath?: string;
  thumbnailUrl?: string;
  isImage?: boolean;
  mimeType?: string;
}

/**
 * 消息接口
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'agent';
  content: string;
  createAt: number;
  status: MessageStatus | string;
  attachments?: Attachment[];
  
  // 扩展字段
  chatId?: string;
  senderId?: string;
  senderName?: string;
  time?: number;
  isRead?: boolean;
}

/**
 * 成员接口
 */
export interface Member {
  userId: string;
  role: string;
  name: string;
  avatar?: string;
  status?: MemberStatus | string;
  ext?: Record<string, any>;
  agentName?: string;
}

/**
 * 聊天接口
 */
export interface Chat {
  // 基础信息
  id: string;
  type: ChatType | string;
  name: string;
  avatar?: string;
  
  // 成员和消息
  members: Member[];
  messages: Message[];
  
  // 聊天状态
  lastMsg?: string;
  lastMsgTime?: number;
  unread: number;
  
  // 自定义字段
  pinned?: boolean;
  muted?: boolean;
  ext?: Record<string, any>;
  
  // 时间戳
  createdAt?: string;
  updatedAt?: string;
  created_at?: string; // 兼容后端字段
  updated_at?: string; // 兼容后端字段
}

/**
 * 创建聊天的输入类型
 */
export interface CreateChatInput {
  type: ChatType;
  name: string;
  members: Member[];
  avatar?: string;
}

/**
 * 更新聊天的输入类型
 */
export interface UpdateChatInput {
  name?: string;
  avatar?: string;
  pinned?: boolean;
  muted?: boolean;
  members?: Member[];
}

/**
 * 发送消息的输入类型
 */
export interface SendMessageInput {
  chatId: string;
  content: string;
  attachments?: Attachment[];
}

