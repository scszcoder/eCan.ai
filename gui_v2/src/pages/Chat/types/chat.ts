export interface Chat {
    id: number;
    name: string;
    avatar?: string;
    type: 'user' | 'bot' | 'group';
    status: 'online' | 'offline' | 'busy';
    agentId?: string;
    lastMessage: string;
    lastMessageTime: string;
    unreadCount: number;
    isGroup?: boolean;
    members?: string[];
    messages: Message[];
}

export interface Message {
    id: number;
    chat_id: number;
    content: string;
    attachments: Attachment[];
    sender_id: string;
    sender_name: string;
    recipient_id: string;
    recipient_name: string;
    txTimestamp: string;
    rxTimestamp: string;
    readTimestamp: string;
    status: 'sending' | 'sent' | 'delivered' | 'read' | 'failed';
    isEdited?: boolean;
    isRetracted?: boolean;
    ext?: Record<string, any>;
    replyTo?: number;
    atList?: string[];
}

export interface Attachment {
    id: string;
    name: string;
    type: string;
    size: number;
    url?: string;
    content?: string; // base64
    file?: File;
} 