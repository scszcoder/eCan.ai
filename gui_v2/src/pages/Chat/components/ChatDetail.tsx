import React, { useRef, useEffect } from 'react';
import { Badge, Avatar, Space, Typography, Button } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, MoreOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat, Message, Attachment } from '../types/chat';
import { useChatStore } from '../hooks/useChatStore';
import MessageInput from './MessageInput';
import MessageItem from './MessageItem';

const { Text, Title } = Typography;

const ChatHeader = styled.div`
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border-color);
    background: var(--bg-secondary);
    box-shadow: var(--shadow-sm);
`;

const ChatInfo = styled.div`
    display: flex;
    align-items: center;
    gap: 12px;
`;

const ChatName = styled(Text)`
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
`;

const StyledAvatar = styled(Avatar)`
    box-shadow: var(--shadow-sm);
`;

const ChatContainer = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--bg-primary);
`;

const MessageList = styled.div`
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 20px;
    background: var(--bg-primary);
    min-height: 0;
    display: flex;
    flex-direction: column;
    
    &::-webkit-scrollbar {
        width: 6px;
    }
    &::-webkit-scrollbar-track {
        background: var(--bg-secondary);
        border-radius: 3px;
    }
    &::-webkit-scrollbar-thumb {
        background: var(--bg-tertiary);
        border-radius: 3px;
    }
    &::-webkit-scrollbar-thumb:hover {
        background: var(--text-muted);
    }
`;

const EmptyState = styled.div`
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    font-size: 14px;
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
        return (
            <EmptyState>
                {t('pages.chat.selectChat')}
            </EmptyState>
        );
    }

    const handleSendMessage = (content: string, attachments: Attachment[]) => {
        if (!chatId) return;
        sendMessage(chatId, content, attachments);
    };

    return (
        <ChatContainer>
            <ChatHeader>
                <ChatInfo>
                    <Badge 
                        status={
                            chat.status === 'online' ? 'success' :
                            chat.status === 'busy' ? 'warning' : 'default'
                        } 
                        offset={[-2, 2]}
                    />
                    <StyledAvatar 
                        icon={
                            chat.type === 'user' ? <UserOutlined /> :
                            chat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />
                        }
                        style={{
                            backgroundColor: chat.type === 'bot' ? 'var(--primary-color)' : 'var(--bg-tertiary)',
                            color: chat.type === 'bot' ? '#ffffff' : 'var(--text-secondary)'
                        }}
                    />
                    <ChatName>{chat.name}</ChatName>
                </ChatInfo>
                <Button 
                    icon={<MoreOutlined />} 
                    type="text"
                    style={{ color: 'var(--text-secondary)' }}
                />
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