import React, { useRef, useEffect } from 'react';
import { Badge, Avatar, Space, Typography, Button } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, MoreOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat, Message, Attachment } from '../types/chat';
import { useChatStore } from '../hooks/useChatStore';
import MessageItem from './MessageItem';
import MessageInput from './MessageInput';

const { Text, Title } = Typography;

const ChatHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
`;

const MessageList = styled.div`
    flex: 1;
    overflow-y: auto;
    padding: 16px;
`;

const ChatContainer = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
`;

interface ChatDetailProps {
    chatId: number | null;
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId }) => {
    const { t } = useTranslation();
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const { chats, sendMessage } = useChatStore();
    
    const chat = chats.find(c => c.id === chatId);

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [chat?.messages]);

    if (!chat) {
        return <Text type="secondary">{t('pages.chat.selectChat')}</Text>;
    }

    const handleSendMessage = (content: string, attachments: Attachment[]) => {
        if (!chatId) return;
        sendMessage(chatId, content, attachments);
    };

    return (
        <ChatContainer>
            <ChatHeader>
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
                </Space>
                <Button icon={<MoreOutlined />} />
            </ChatHeader>
            <MessageList>
                {chat.messages?.map(message => (
                    <MessageItem key={message.id} message={message} />
                ))}
                <div ref={messagesEndRef} />
            </MessageList>
            <MessageInput onSend={handleSendMessage} />
        </ChatContainer>
    );
};

export default ChatDetail; 