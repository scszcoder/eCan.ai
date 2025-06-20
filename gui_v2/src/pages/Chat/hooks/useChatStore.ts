import { create } from 'zustand';
import { ChatSession, Message } from '../types/chat';
import { IPCAPI } from '@/services/ipc/api';
import { demoChats, enableDemoData } from './demoData';

interface ChatState {
    chats: ChatSession[];
    activeChatId: number | null;
    addChat: (chat: ChatSession) => void;
    updateChat: (chat: Partial<ChatSession> & { id: number }) => void;
    setActiveChat: (chatId: number) => void;
    addMessage: (chatId: number, message: Message) => void;
    updateMessageStatus: (messageId: number, status: Message['status']) => void;
    sendMessage: (chatId: number, content: string, attachments: any[], options?: { ext?: any; replyTo?: number; atList?: string[] }) => Promise<void>;
    updateChatsGUI: (params: { chat: Omit<ChatSession, 'messages'> & { messages?: Message[] }, message: Message }) => void;
    initialize: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
    chats: [],
    activeChatId: null,

    addChat: (chat) => set((state) => ({
        chats: [chat, ...state.chats],
        activeChatId: state.activeChatId ?? chat.id
    })),

    updateChat: (updates) => set((state) => ({
        chats: state.chats.map(chat =>
            chat.id === updates.id ? { ...chat, ...updates } : chat
        )
    })),

    setActiveChat: (chatId) => set((state) => ({
        activeChatId: chatId,
        chats: state.chats.map(chat =>
            chat.id === chatId ? { ...chat, unreadCount: 0 } : chat
        )
    })),

    addMessage: (chatId, message) => set((state) => {
        const chat = state.chats.find(c => c.id === chatId);
        if (!chat) return state;

        return {
            chats: state.chats.map(chat => {
                if (chat.id !== chatId) return chat;
                const messageExists = chat.messages?.some(m => m.id === message.id);
                if (messageExists) return chat;

                return {
                    ...chat,
                    messages: [...(chat.messages || []), message],
                    lastMessage: message.content,
                    lastMessageTime: new Date().toISOString(),
                    unreadCount: state.activeChatId === chatId ? 0 : (chat.unreadCount + 1)
                };
            })
        };
    }),

    updateMessageStatus: (messageId, status) => set((state) => ({
        chats: state.chats.map(chat => ({
            ...chat,
            messages: chat.messages?.map(msg =>
                msg.id === messageId ? { ...msg, status } : msg
            )
        }))
    })),

    sendMessage: async (chatId, content, attachments, options = {}) => {
        const tempId = Date.now();
        const state = get();
        const chat = state.chats.find(c => c.id === chatId);
        // 推断 receiver
        let receiver = '';
        if (chat) {
            if (chat.type === 'user') {
                receiver = chat.name;
            } else if (chat.type === 'group') {
                receiver = String(chat.id);
            } else if (chat.type === 'bot') {
                receiver = chat.agentId || '';
            }
        }
        // 推断 type
        let msgType: Message['type'] = 'text';
        if (attachments && attachments.length > 0) {
            const firstType = attachments[0].type;
            if (firstType.startsWith('image')) msgType = 'image';
            else if (firstType.startsWith('audio')) msgType = 'file'; // 可细分
            else msgType = 'file';
        }
        // 组装消息
        const newMessage: Message = {
            id: tempId,
            sessionId: chatId,
            content,
            attachments,
            sender: 'You',
            receiver,
            type: msgType,
            txTimestamp: new Date().toISOString(),
            rxTimestamp: '',
            readTimestamp: '',
            status: 'sending',
            ext: options.ext || {},
            replyTo: options.replyTo,
            atList: options.atList || [],
        };
        // Add message to UI immediately
        get().addMessage(chatId, newMessage);
        try {
            const response = await IPCAPI.getInstance().sendChat(newMessage);
            if (response?.success) {
                get().updateMessageStatus(tempId, 'sent');
            } else {
                get().updateMessageStatus(tempId, 'failed');
            }
        } catch (error) {
            console.error('Failed to send message:', error);
            get().updateMessageStatus(tempId, 'failed');
        }
    },

    updateChatsGUI: ({ chat, message }) => {
        const state = useChatStore.getState();
        const existingChat = state.chats.find(c => c.id === chat.id);

        if (existingChat) {
            state.updateChat({
                ...existingChat,
                lastMessage: message.content,
                lastMessageTime: new Date().toISOString(),
                unreadCount: state.activeChatId === chat.id ? 0 : (existingChat.unreadCount + 1),
                messages: existingChat.messages
            });
            state.addMessage(chat.id, message);
        } else {
            state.addChat({
                ...chat,
                messages: [message],
                lastMessage: message.content,
                lastMessageTime: new Date().toISOString(),
                unreadCount: 0
            });
        }
    },

    initialize: () => {
        if (enableDemoData) {
            set({ chats: demoChats, activeChatId: demoChats[0]?.id || null });
        } else {
            set({ chats: [], activeChatId: null });
        }
    }
})); 