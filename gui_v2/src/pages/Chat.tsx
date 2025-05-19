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
    AudioOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';

const { Text, Title } = Typography;
const { TextArea } = Input;

const ChatItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid #f0f0f0;
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: background-color 0.3s;
    &:hover {
        background-color: #f5f5f5;
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
    border-radius: 8px;
    background-color: ${props => props.isUser ? '#1890ff' : '#f0f0f0'};
    color: ${props => props.isUser ? '#fff' : 'inherit'};
`;

const MessageToolbar = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-top: 1px solid #f0f0f0;
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
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'type',
                        label: 'Type',
                        options: [
                            { label: 'User', value: 'user' },
                            { label: 'Bot', value: 'bot' },
                            { label: 'Group', value: 'group' },
                        ],
                    },
                    {
                        key: 'status',
                        label: 'Status',
                        options: [
                            { label: 'Online', value: 'online' },
                            { label: 'Offline', value: 'offline' },
                            { label: 'Busy', value: 'busy' },
                        ],
                    },
                ]}
                placeholder="Search chats..."
            />
            <ActionButtons
                onAdd={() => {}}
                onEdit={() => {}}
                onDelete={() => {}}
                onRefresh={() => {}}
                onExport={() => {}}
                onImport={() => {}}
                onSettings={() => {}}
            />
            <List
                dataSource={chats}
                renderItem={chat => (
                    <ChatItem onClick={() => selectItem(chat)}>
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <StatusTag status={chat.status} />
                                {chat.type === 'bot' ? <RobotOutlined /> : <UserOutlined />}
                                <Text strong>{chat.name}</Text>
                                {chat.unreadCount > 0 && (
                                    <Badge count={chat.unreadCount} />
                                )}
                            </Space>
                            <Space direction="vertical" size={0}>
                                <Text type="secondary" ellipsis>
                                    {chat.lastMessage}
                                </Text>
                                <Text type="secondary" style={{ fontSize: '12px' }}>
                                    {chat.lastMessageTime}
                                </Text>
                            </Space>
                        </Space>
                    </ChatItem>
                )}
            />
        </>
    );

    const renderDetailsContent = () => {
        if (!selectedChat) {
            return <Text type="secondary">Select a chat to start messaging</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%', height: '100%' }}>
                <DetailCard
                    title="Chat Information"
                    items={[
                        {
                            label: 'Name',
                            value: selectedChat.name,
                            icon: selectedChat.type === 'bot' ? <RobotOutlined /> : <UserOutlined />,
                        },
                        {
                            label: 'Type',
                            value: selectedChat.type,
                            icon: <MessageOutlined />,
                        },
                        {
                            label: 'Status',
                            value: <StatusTag status={selectedChat.status} />,
                            icon: <CheckCircleOutlined />,
                        },
                    ]}
                />
                <Card
                    style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
                    bodyStyle={{ flex: 1, overflow: 'auto', padding: '16px' }}
                >
                    {messages.map(message => (
                        <MessageItem key={message.id} isUser={message.sender === 'You'}>
                            <Avatar icon={message.sender === 'You' ? <UserOutlined /> : <RobotOutlined />} />
                            <Space direction="vertical" size={0}>
                                <MessageContent isUser={message.sender === 'You'}>
                                    {message.content}
                                </MessageContent>
                                <Space size={4}>
                                    <Text type="secondary" style={{ fontSize: '12px' }}>
                                        {message.timestamp}
                                    </Text>
                                    {message.sender === 'You' && (
                                        <Tooltip title={
                                            message.status === 'sending' ? 'Sending...' :
                                            message.status === 'sent' ? 'Sent' :
                                            message.status === 'delivered' ? 'Delivered' : 'Read'
                                        }>
                                            {message.status === 'sending' ? <ClockCircleOutlined /> :
                                             message.status === 'sent' ? <CheckCircleOutlined /> :
                                             message.status === 'delivered' ? <CheckCircleOutlined /> :
                                             <CheckCircleOutlined style={{ color: '#1890ff' }} />}
                                        </Tooltip>
                                    )}
                                </Space>
                            </Space>
                        </MessageItem>
                    ))}
                    <div ref={messagesEndRef} />
                </Card>
                <MessageToolbar>
                    <Button icon={<SmileOutlined />} />
                    <Button icon={<PaperClipOutlined />} />
                    <Button icon={<AudioOutlined />} />
                    <TextArea
                        value={newMessage}
                        onChange={e => setNewMessage(e.target.value)}
                        placeholder="Type a message..."
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
                    />
                </MessageToolbar>
            </Space>
        );
    };

    return (
        <DetailLayout
            listTitle="Chats"
            detailsTitle="Chat Details"
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Chat; 