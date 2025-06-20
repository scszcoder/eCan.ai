import { ChatSession } from '../types/chat';

// 是否启用 demo 数据
export const enableDemoData = true;

const now = new Date();
const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
const twoHoursAgo = new Date(now.getTime() - 2 * 60 * 60 * 1000);
const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

export const demoChats: ChatSession[] = [
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
                sessionId: 1,
                content: 'Hello! How can I help you today?',
                attachments: [],
                sender: 'Support Bot',
                receiver: 'John Doe',
                type: 'text',
                txTimestamp: twoHoursAgo.toISOString(),
                rxTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                readTimestamp: new Date(twoHoursAgo.getTime() + 60000).toISOString(),
                status: 'read',
                ext: {},
                atList: [],
            },
            {
                id: 2,
                sessionId: 1,
                content: 'I need help with scheduling a delivery.',
                attachments: [],
                sender: 'You',
                receiver: 'John Doe',
                type: 'text',
                txTimestamp: new Date(twoHoursAgo.getTime() + 5 * 60000).toISOString(),
                rxTimestamp: new Date(twoHoursAgo.getTime() + 6 * 60000).toISOString(),
                readTimestamp: new Date(twoHoursAgo.getTime() + 6 * 60000).toISOString(),
                status: 'read',
                ext: {},
                atList: [],
            },
            {
                id: 3,
                sessionId: 1,
                content: 'Can you help me with the delivery schedule?',
                attachments: [],
                sender: 'John Doe',
                receiver: 'You',
                type: 'text',
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
                sessionId: 2,
                content: 'How can I assist you today?',
                attachments: [],
                sender: 'Support Bot',
                receiver: 'You',
                type: 'text',
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
                sessionId: 3,
                content: 'Meeting at 2 PM',
                attachments: [],
                sender: 'Team Lead',
                receiver: 'Team Alpha',
                type: 'text',
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