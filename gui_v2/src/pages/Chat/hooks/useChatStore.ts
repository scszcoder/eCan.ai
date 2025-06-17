import { create } from 'zustand';
import { Chat, Message } from '../types/chat';
import { IPCAPI } from '@/services/ipc/api';

interface ChatState {
    chats: Chat[];
    activeChatId: number | null;
    addChat: (chat: Chat) => void;
    updateChat: (chat: Partial<Chat> & { id: number }) => void;
    setActiveChat: (chatId: number) => void;
    addMessage: (chatId: number, message: Message) => void;
    updateMessageStatus: (messageId: number, status: Message['status']) => void;
    sendMessage: (chatId: number, content: string, attachments: any[]) => Promise<void>;
    updateChatsGUI: (params: { chat: Omit<Chat, 'messages'> & { messages?: Message[] }, message: Message }) => void;
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
                    lastMessageTime: new Date().toLocaleTimeString(),
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

    sendMessage: async (chatId, content, attachments) => {
        const tempId = Date.now();
        const newMessage: Message = {
            id: tempId,
            sessionId: chatId,
            content,
            attachments,
            sender: 'You',
            txTimestamp: new Date().toISOString(),
            rxTimestamp: '',
            readTimestamp: '',
            status: 'sending'
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
                lastMessageTime: new Date().toLocaleTimeString(),
                unreadCount: state.activeChatId === chat.id ? 0 : (existingChat.unreadCount + 1),
                messages: existingChat.messages
            });
            state.addMessage(chat.id, message);
        } else {
            state.addChat({
                ...chat,
                messages: [message],
                lastMessage: message.content,
                lastMessageTime: new Date().toLocaleTimeString(),
                unreadCount: 0
            });
        }
    },

    initialize: () => {
        // Initialize with default chats and messages
        const initialChats: Chat[] = [
            {
                id: 1,
                name: 'John Doe',
                type: 'user',
                status: 'online',
                lastMessage: 'Can you help me with the delivery schedule?',
                lastMessageTime: '10:30 AM',
                unreadCount: 2,
                messages: [
                    {
                        id: 1,
                        sessionId: 1,
                        content: 'Hello! How can I help you today?',
                        attachments: [],
                        sender: 'Support Bot',
                        txTimestamp: '10:00 AM',
                        rxTimestamp: '10:01 AM',
                        readTimestamp: '10:01 AM',
                        status: 'read',
                    },
                    {
                        id: 2,
                        sessionId: 1,
                        content: 'I need help with scheduling a delivery.',
                        attachments: [],
                        sender: 'You',
                        txTimestamp: '10:05 AM',
                        rxTimestamp: '10:06 AM',
                        readTimestamp: '10:06 AM',
                        status: 'read',
                    },
                    {
                        id: 3,
                        sessionId: 1,
                        content: 'Can you help me with the delivery schedule?',
                        attachments: [],
                        sender: 'John Doe',
                        txTimestamp: '10:30 AM',
                        rxTimestamp: '10:31 AM',
                        readTimestamp: '',
                        status: 'delivered',
                    }
                ]
            },
            {
                id: 2,
                name: 'Support Bot',
                type: 'bot',
                status: 'online',
                lastMessage: 'How can I assist you today?',
                lastMessageTime: '09:15 AM',
                unreadCount: 0,
                messages: [
                    {
                        id: 4,
                        sessionId: 2,
                        content: 'How can I assist you today?',
                        attachments: [],
                        sender: 'Support Bot',
                        txTimestamp: '09:15 AM',
                        rxTimestamp: '09:16 AM',
                        readTimestamp: '09:16 AM',
                        status: 'read',
                    }
                ]
            },
            {
                id: 3,
                name: 'Team Alpha',
                type: 'group',
                status: 'busy',
                lastMessage: 'Meeting at 2 PM',
                lastMessageTime: 'Yesterday',
                unreadCount: 5,
                messages: [
                    {
                        id: 5,
                        sessionId: 3,
                        content: 'Meeting at 2 PM',
                        attachments: [],
                        sender: 'Team Lead',
                        txTimestamp: 'Yesterday',
                        rxTimestamp: 'Yesterday',
                        readTimestamp: '',
                        status: 'delivered',
                    }
                ]
            }
        ];
        set({ chats: initialChats, activeChatId: 1 });
    }
})); 