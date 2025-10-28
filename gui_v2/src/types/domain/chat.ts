/**
 * Chat Domain Types
 * Type definitions for chats
 */

/**
 * Chat type
 */
export enum ChatType {
  USER_SYSTEM = 'user-system',
  USER_AGENT = 'user-agent',
  AGENT_AGENT = 'agent-agent',
  GROUP = 'group',
}

/**
 * Message status
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
 * Member status
 */
export enum MemberStatus {
  ONLINE = 'online',
  OFFLINE = 'offline',
  BUSY = 'busy',
}

/**
 * Attachment interface
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
 * Message interface
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'agent';
  content: string;
  createAt: number;
  status: MessageStatus | string;
  attachments?: Attachment[];
  
  // Extended fields
  chatId?: string;
  senderId?: string;
  senderName?: string;
  time?: number;
  isRead?: boolean;
}

/**
 * Member interface
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
 * Chat interface
 */
export interface Chat {
  // Basic information
  id: string;
  type: ChatType | string;
  name: string;
  avatar?: string;
  
  // Members and messages
  members: Member[];
  messages: Message[];
  
  // Chat status
  lastMsg?: string;
  lastMsgTime?: number;
  unread: number;
  
  // Custom fields
  pinned?: boolean;
  muted?: boolean;
  ext?: Record<string, any>;
  
  // Timestamps
  createdAt?: string;
  updatedAt?: string;
  created_at?: string; // Compatible with backend fields
  updated_at?: string; // Compatible with backend fields
}

/**
 * Create chat input type
 */
export interface CreateChatInput {
  type: ChatType;
  name: string;
  members: Member[];
  avatar?: string;
}

/**
 * Update chat input type
 */
export interface UpdateChatInput {
  name?: string;
  avatar?: string;
  pinned?: boolean;
  muted?: boolean;
  members?: Member[];
}

/**
 * Send message input type
 */
export interface SendMessageInput {
  chatId: string;
  content: string;
  attachments?: Attachment[];
}

