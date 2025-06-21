import { create } from 'zustand';
import { Chat, Message } from '../types/chat';
import { IPCAPI } from '@/services/ipc/api';
import { demoChats, enableDemoData } from './demoData';

interface ChatState {
    chats: Chat[];
    activeChatId: number | null;
    addChat: (chat: Chat) => void;
    updateChat: (chat: Partial<Chat> & { id: number }) => void;
    setActiveChat: (chatId: number) => void;
    addMessage: (chatId: number, message: Message) => void;
    updateMessageStatus: (messageId: number, status: Message['status']) => void;
    sendMessage: (chatId: number, content: string, attachments: any[], options?: { ext?: any; replyTo?: number; atList?: string[] }) => Promise<void>;
    updateChatsGUI: (params: { chat: Omit<Chat, 'messages'> & { messages?: Message[] }, message: Message }) => void;
    initialize: () => void;
}

export const useChatStore = create<ChatState>((set, get) => ({
    chats: [],
    activeChatId: null,

    addChat: (chat) => set((state) => ({
        chats: [...state.chats, chat],
        activeChatId: state.activeChatId ?? chat.id
    })),

    updateChat: (chat) => set((state) => ({
        chats: state.chats.map(c => c.id === chat.id ? { ...c, ...chat } : c)
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
        const { chats } = get();
        const chatIndex = chats.findIndex(c => c.id === chat.id);
    
        if (chatIndex !== -1) {
            // 更新已有的chat
            const newChats = [...chats];
            const oldChat = newChats[chatIndex];
            const newMessages = oldChat.messages ? [...oldChat.messages, message] : [message];
            newChats[chatIndex] = { ...oldChat, ...chat, messages: newMessages };
            set({ chats: newChats });
        } else {
            // 添加新的chat
            const newChat = { ...chat, messages: [message] };
            set({ chats: [...chats, newChat] });
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