import React from 'react';
import { Avatar, Space, Typography, Tooltip } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { Message } from '../types/chat';
import { useTranslation } from 'react-i18next';
import AttachmentPreview from './AttachmentPreview';

const { Text } = Typography;

const MessageItemWrapper = styled.div<{ isUser: boolean }>`
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
    display: flex;
    flex-direction: column;
    gap: 8px;
`;

interface MessageItemProps {
    message: Message;
}

const MessageItem: React.FC<MessageItemProps> = ({ message }) => {
    const { t } = useTranslation();
    const isUser = message.sender === 'You';

    const getAvatarIcon = () => {
        switch (message.sender) {
            case 'You':
                return <UserOutlined />;
            case 'Support Bot':
                return <RobotOutlined />;
            default:
                return <TeamOutlined />;
        }
    };

    const getStatusIcon = () => {
        switch (message.status) {
            case 'sending':
                return <ClockCircleOutlined />;
            case 'sent':
                return <CheckCircleOutlined />;
            case 'delivered':
                return <CheckCircleOutlined style={{ color: '#1890ff' }} />;
            case 'read':
                return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
            default:
                return null;
        }
    };

    return (
        <MessageItemWrapper isUser={isUser}>
            <Avatar icon={getAvatarIcon()} />
            <Space direction="vertical" style={{ maxWidth: '70%' }}>
                <MessageContent isUser={isUser}>
                    <div>{message.content}</div>
                    {message.attachments && message.attachments.length > 0 && (
                        <AttachmentPreview attachments={message.attachments} />
                    )}
                </MessageContent>
                <Space size={4}>
                    <Text type="secondary" style={{ fontSize: '12px' }}>
                        {new Date(message.txTimestamp).toLocaleTimeString()}
                    </Text>
                    {isUser && (
                        <Tooltip title={t(`pages.chat.${message.status}`)}>
                            {getStatusIcon()}
                        </Tooltip>
                    )}
                </Space>
            </Space>
        </MessageItemWrapper>
    );
};

export default MessageItem; 