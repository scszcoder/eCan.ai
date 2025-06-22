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
    margin-bottom: 20px;
    gap: 12px;
    align-items: flex-start;
`;

const MessageContent = styled.div<{ isUser: boolean }>`
    max-width: 70%;
    padding: 16px;
    border-radius: ${props => props.isUser ? '20px 20px 4px 20px' : '20px 20px 20px 4px'};
    background-color: ${props => props.isUser ? 'var(--primary-color)' : 'var(--bg-tertiary)'};
    color: ${props => props.isUser ? '#ffffff' : 'var(--text-primary)'};
    box-shadow: var(--shadow-sm);
    display: flex;
    flex-direction: column;
    gap: 8px;
    position: relative;
    
    &::before {
        content: '';
        position: absolute;
        top: 0;
        ${props => props.isUser ? 'right' : 'left'}: -8px;
        width: 0;
        height: 0;
        border: 8px solid transparent;
        border-top-color: ${props => props.isUser ? 'var(--primary-color)' : 'var(--bg-tertiary)'};
        border-top-width: 12px;
        border-bottom-width: 0;
    }
`;

const MessageText = styled.div`
    line-height: 1.5;
    font-size: 14px;
    word-wrap: break-word;
`;

const MessageTime = styled.div`
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 4px;
`;

const TimeText = styled(Text)`
    font-size: 11px !important;
    opacity: 0.7;
`;

const StatusIcon = styled.span`
    font-size: 12px;
    display: flex;
    align-items: center;
`;

const StyledAvatar = styled(Avatar)`
    flex-shrink: 0;
    box-shadow: var(--shadow-sm);
`;

interface MessageItemProps {
    message: Message;
}

const MessageItem: React.FC<MessageItemProps> = ({ message }) => {
    const { t } = useTranslation();
    const isUser = message.sender_id === 'You';

    const getAvatarIcon = () => {
        switch (message.sender_id) {
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
                return <ClockCircleOutlined style={{ color: 'var(--text-muted)' }} />;
            case 'sent':
                return <CheckCircleOutlined style={{ color: 'var(--text-muted)' }} />;
            case 'delivered':
                return <CheckCircleOutlined style={{ color: 'var(--primary-color)' }} />;
            case 'read':
                return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
            default:
                return null;
        }
    };

    return (
        <MessageItemWrapper isUser={isUser}>
            <StyledAvatar 
                icon={getAvatarIcon()} 
                style={{ 
                    backgroundColor: isUser ? 'var(--primary-color)' : 'var(--bg-secondary)',
                    color: isUser ? '#ffffff' : 'var(--text-secondary)'
                }}
            />
            <div style={{ maxWidth: '70%', display: 'flex', flexDirection: 'column' }}>
                <MessageContent isUser={isUser}>
                    <MessageText>{message.content}</MessageText>
                    {message.attachments && message.attachments.length > 0 && (
                        <AttachmentPreview attachments={message.attachments} />
                    )}
                </MessageContent>
                <MessageTime>
                    <TimeText type="secondary">
                        {new Date(message.txTimestamp).toLocaleTimeString([], { 
                            hour: '2-digit', 
                            minute: '2-digit' 
                        })}
                    </TimeText>
                    {isUser && (
                        <Tooltip title={t(`pages.chat.${message.status}`)}>
                            <StatusIcon>
                                {getStatusIcon()}
                            </StatusIcon>
                        </Tooltip>
                    )}
                </MessageTime>
            </div>
        </MessageItemWrapper>
    );
};

export default MessageItem; 