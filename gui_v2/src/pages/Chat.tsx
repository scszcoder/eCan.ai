import React, { useState, useRef, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Input, Avatar, Card, Badge, Tooltip } from 'antd';
import { 
    MessageOutlined, 
    SendOutlined, 
    UserOutlined, 
    RobotOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    MoreOutlined,
    SmileOutlined,
    PaperClipOutlined,
    AudioOutlined,
    TeamOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';
import {ipc_api} from '../services/ipc_api';

const { Text, Title } = Typography;
const { TextArea } = Input;

const ChatItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .ant-progress-text {
        color: var(--text-primary);
    }
`;

const MessageItem = styled.div<{ isUser: boolean }>`
    display: flex;
    flex-direction: ${props => props.isUser ? 'row-reverse' : 'row'};
    margin-bottom: 16px;
    gap: 8px;
`;

const MessageContent = styled.div<{ isUser: boolean }>`
    max-width: 70%;
    padding: 12px;
    border-radius: 12px;
    background-color: ${props => props.isUser ? 'var(--primary-color)' : 'var(--bg-tertiary)'};
    color: ${props => props.isUser ? '#fff' : 'var(--text-primary)'};
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
`;

const MessageToolbar = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-top: 1px solid var(--border-color);
    border-radius: 0 0 8px 8px;
`;

interface Chat {
    id: number;
    name: string;
    type: 'user' | 'bot' | 'group';
    status: 'online' | 'offline' | 'busy';
    lastMessage: string;
    lastMessageTime: string;
    unreadCount: number;
}

interface Message {
    id: number;
    content: string;
    sender: string;
    timestamp: string;
    status: 'sending' | 'sent' | 'delivered' | 'read';
}

const initialChats: Chat[] = [
    {
        id: 1,
        name: 'John Doe',
        type: 'user',
        status: 'online',
        lastMessage: 'Can you help me with the delivery schedule?',
        lastMessageTime: '10:30 AM',
        unreadCount: 2,
    },
    {
        id: 2,
        name: 'Support Bot',
        type: 'bot',
        status: 'online',
        lastMessage: 'How can I assist you today?',
        lastMessageTime: '09:15 AM',
        unreadCount: 0,
    },
    {
        id: 3,
        name: 'Team Alpha',
        type: 'group',
        status: 'busy',
        lastMessage: 'Meeting at 2 PM',
        lastMessageTime: 'Yesterday',
        unreadCount: 5,
    },
];

const initialMessages: Message[] = [
    {
        id: 1,
        content: 'Hello! How can I help you today?',
        sender: 'Support Bot',
        timestamp: '10:00 AM',
        status: 'read',
    },
    {
        id: 2,
        content: 'I need help with scheduling a delivery.',
        sender: 'You',
        timestamp: '10:05 AM',
        status: 'read',
    },
    {
        id: 3,
        content: 'Sure! I can help you with that. What are the details?',
        sender: 'Support Bot',
        timestamp: '10:06 AM',
        status: 'read',
    },
];

const Chat: React.FC = () => {
    const { t } = useTranslation();
    const {
        selectedItem: selectedChat,
        items: chats,
        selectItem,
        updateItem,
    } = useDetailView<Chat>(initialChats);

    const [messages, setMessages] = useState<Message[]>(initialMessages);
    const [newMessage, setNewMessage] = useState('');
    const [filters, setFilters] = useState<Record<string, any>>({});
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const handleSendMessage = () => {
        if (!newMessage.trim() || !selectedChat) return;

        const newMsg: Message = {
            id: messages.length + 1,
            content: newMessage,
            sender: 'You',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            status: 'sending',
        };

        setMessages(prev => [...prev, newMsg]);
        setNewMessage('');

        // Simulate message status updates
        setTimeout(() => {
            setMessages(prev => 
                prev.map(msg => 
                    msg.id === newMsg.id ? { ...msg, status: 'sent' } : msg
                )
            );
        }, 1000);

        setTimeout(() => {
            setMessages(prev => 
                prev.map(msg => 
                    msg.id === newMsg.id ? { ...msg, status: 'delivered' } : msg
                )
            );
        }, 2000);

        // Simulate bot response
        setTimeout(() => {
            const botResponse: Message = {
                id: messages.length + 2,
                content: 'I understand. Let me help you with that.',
                sender: selectedChat.name,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                status: 'read',
            };
            setMessages(prev => [...prev, botResponse]);
        }, 3000);
    };

    const handleSearch = (value: string) => {
        // Implement search logic
    };

    const handleFilterChange = (newFilters: Record<string, any>) => {
        setFilters(prev => ({ ...prev, ...newFilters }));
    };

    const handleReset = () => {
        setFilters({});
    };

    const renderListContent = () => (
        <>
            <Title level={2}>{t('pages.chat.title')}</Title>
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'type',
                        label: t('pages.chat.type'),
                        options: [
                            { label: t('pages.chat.user'), value: 'user' },
                            { label: t('pages.chat.bot'), value: 'bot' },
                            { label: t('pages.chat.group'), value: 'group' },
                        ],
                    },
                    {
                        key: 'status',
                        label: t('pages.chat.status'),
                        options: [
                            { label: t('pages.chat.online'), value: 'online' },
                            { label: t('pages.chat.offline'), value: 'offline' },
                            { label: t('pages.chat.busy'), value: 'busy' },
                        ],
                    },
                ]}
                placeholder={t('pages.chat.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
                addText={t('pages.chat.addChat')}
                editText={t('pages.chat.editChat')}
                deleteText={t('pages.chat.deleteChat')}
                refreshText={t('pages.chat.refreshChat')}
                exportText={t('pages.chat.exportChat')}
                importText={t('pages.chat.importChat')}
                settingsText={t('pages.chat.chatSettings')}
            />
            <List
                dataSource={chats}
                renderItem={chat => (
                    <ChatItem onClick={() => selectItem(chat)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <Badge status={
                                    chat.status === 'online' ? 'success' :
                                    chat.status === 'busy' ? 'warning' : 'default'
                                } />
                                <Avatar icon={
                                    chat.type === 'user' ? <UserOutlined /> :
                                    chat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />
                                } />
                                <Text strong>{chat.name}</Text>
                                {chat.unreadCount > 0 && (
                                    <Badge count={chat.unreadCount} />
                                )}
                            </Space>
                            <Space>
                                <Text type="secondary">{chat.lastMessage}</Text>
                                <Text type="secondary">{chat.lastMessageTime}</Text>
                            </Space>
                        </Space>
                    </ChatItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedChat) {
            return <Text type="secondary">{t('pages.chat.selectChat')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%', height: '100%' }}>
                <Card
                    title={
                        <Space>
                            <Badge status={
                                selectedChat.status === 'online' ? 'success' :
                                selectedChat.status === 'busy' ? 'warning' : 'default'
                            } />
                            <Avatar icon={
                                selectedChat.type === 'user' ? <UserOutlined /> :
                                selectedChat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />
                            } />
                            <Text strong>{selectedChat.name}</Text>
                            <Tag color={
                                selectedChat.type === 'user' ? 'blue' :
                                selectedChat.type === 'bot' ? 'green' : 'purple'
                            }>
                                {t(`pages.chat.${selectedChat.type}`)}
                            </Tag>
                        </Space>
                    }
                    extra={
                        <Button icon={<MoreOutlined />} />
                    }
                >
                    <div style={{ height: 'calc(100vh - 300px)', overflowY: 'auto' }}>
                        {messages.map(message => (
                            <MessageItem key={message.id} isUser={message.sender === 'You'}>
                                <Avatar icon={
                                    message.sender === 'You' ? <UserOutlined /> :
                                    message.sender === 'Support Bot' ? <RobotOutlined /> : <TeamOutlined />
                                } />
                                <Space direction="vertical" style={{ maxWidth: '70%' }}>
                                    <MessageContent isUser={message.sender === 'You'}>
                                        {message.content}
                                    </MessageContent>
                                    <Space size={4}>
                                        <Text type="secondary" style={{ fontSize: '12px' }}>
                                            {message.timestamp}
                                        </Text>
                                        {message.sender === 'You' && (
                                            <Tooltip title={t(`pages.chat.${message.status}`)}>
                                                {message.status === 'sending' ? <ClockCircleOutlined /> :
                                                 message.status === 'sent' ? <CheckCircleOutlined /> :
                                                 message.status === 'delivered' ? <CheckCircleOutlined style={{ color: '#1890ff' }} /> :
                                                 <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                                            </Tooltip>
                                        )}
                                    </Space>
                                </Space>
                            </MessageItem>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>
                    <MessageToolbar>
                        <Button icon={<SmileOutlined />} />
                        <Button icon={<PaperClipOutlined />} />
                        <Button icon={<AudioOutlined />} />
                        <TextArea
                            value={newMessage}
                            onChange={e => setNewMessage(e.target.value)}
                            placeholder={t('pages.chat.typeMessage')}
                            autoSize={{ minRows: 1, maxRows: 4 }}
                            onPressEnter={e => {
                                if (!e.shiftKey) {
                                    e.preventDefault();
                                    handleSendMessage();
                                }
                            }}
                        />
                        <Button
                            type="primary"
                            icon={<SendOutlined />}
                            onClick={handleSendMessage}
                            disabled={!newMessage.trim()}
                        >
                            {t('pages.chat.send')}
                        </Button>
                    </MessageToolbar>
                </Card>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Chat; 