import { Chat } from '../types/chat';

// 是否启用 demo 数据
export const enableDemoData = true;

const now = new Date();
const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);
const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

export const demoChats: Chat[] = [
    {
        id: 1,
        name: 'John Doe',
        type: 'user',
        status: 'online',
        lastMessage: 'Can you help me with the delivery schedule?',
        lastMessageTime: oneHourAgo.toISOString(),
        unreadCount: 2,
        messages: [
            {
                id: 1,
                chatId: 1,
                content: '你好！有什么可以帮助你的吗？',
                attachments: [],
                sender_id: '1',
                sender_name: 'AI助手',
                recipient_id: 'user',
                recipient_name: '我',
                txTimestamp: twoHoursAgo.toISOString(),
                rxTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                readTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                status: 'read',
                ext: {},
                atList: [],
            },
            {
                id: 2,
                chatId: 1,
                content: '我想了解一下最新的AI技术进展。',
                attachments: [],
                sender_id: 'user',
                sender_name: '我',
                recipient_id: '1',
                recipient_name: 'AI助手',
                txTimestamp: new Date(twoHoursAgo.getTime() + 5 * 60000).toISOString(),
                rxTimestamp: new Date(twoHoursAgo.getTime() + 6 * 60000).toISOString(),
                readTimestamp: new Date(twoHoursAgo.getTime() + 6 * 60000).toISOString(),
                status: 'read',
                ext: {},
                atList: [],
            },
            {
                id: 3,
                chatId: 1,
                content: 'Can you help me with the delivery schedule?',
                attachments: [],
                sender_id: 'John Doe',
                sender_name: 'John Doe',
                recipient_id: 'You',
                recipient_name: 'You',
                txTimestamp: oneHourAgo.toISOString(),
                rxTimestamp: new Date(oneHourAgo.getTime() + 60000).toISOString(),
                readTimestamp: '',
                status: 'delivered',
                ext: {},
                atList: [],
            }
        ]
    },
    {
        id: 2,
        name: 'Support Bot',
        type: 'bot',
        status: 'online',
        lastMessage: 'How can I assist you today?',
        lastMessageTime: twoHoursAgo.toISOString(),
        unreadCount: 0,
        messages: [
            {
                id: 4,
                chatId: 2,
                content: 'How can I assist you today?',
                attachments: [],
                sender_id: '2',
                sender_name: 'Support Bot',
                recipient_id: 'You',
                recipient_name: 'You',
                txTimestamp: twoHoursAgo.toISOString(),
                rxTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                readTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                status: 'read',
                ext: {},
                atList: [],
            }
        ]
    },
    {
        id: 3,
        name: 'Team Alpha',
        type: 'group',
        status: 'busy',
        lastMessage: 'Meeting at 2 PM',
        lastMessageTime: yesterday.toISOString(),
        unreadCount: 5,
        messages: [
            {
                id: 5,
                chatId: 3,
                content: 'Meeting at 2 PM',
                attachments: [],
                sender_id: 'Team Lead',
                sender_name: 'Team Lead',
                recipient_id: 'Team Alpha',
                recipient_name: 'Team Alpha',
                txTimestamp: yesterday.toISOString(),
                rxTimestamp: yesterday.toISOString(),
                readTimestamp: '',
                status: 'delivered',
                ext: {},
                atList: [],
            }
        ]
    }
]; 