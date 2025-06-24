import React, { useMemo } from 'react';
import { Button } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, MoreOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat as LocalChat, Message as LocalMessage, Attachment } from '../types/chat';
import { useAppDataStore } from '../../../stores/appDataStore';
import { Chat as SemiChat } from '@douyinfe/semi-ui';

const ChatDetailWrapper = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    /* 保证撑满父容器 */

    /* Semi UI 深色主题变量覆盖 */
    --semi-color-bg-0: #0f172a;
    --semi-color-bg-1: #1e293b;
    --semi-color-border: #334155;
    --semi-color-text-0: #f8fafc;
    --semi-color-text-1: #cbd5e1;
    --semi-color-text-2: #cbd5e1; /* placeholder增强 */
    --semi-color-primary: #4e40e5;
    --semi-color-primary-hover: #a5b4fc;
    --semi-color-icon-hover: #a5b4fc;
    --semi-color-fill-0: #334155;
    --semi-color-disabled-text: #64748b;
    --semi-color-link: #8b5cf6;

    /* 强制SemiChat宽度100% */
    .semi-chat, .semi-chat-inner {
        max-width: 100% !important;
        width: 100% !important;
        min-width: 0 !important;
    }
`;

const ChatHeader = styled.div`
    flex-shrink: 0;
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

const ChatName = styled.span`
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
`;

const StyledAvatar = styled.div`
    box-shadow: var(--shadow-sm);
`;

const EmptyState = styled.div`
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    font-size: 14px;
`;

const commonOuterStyle = {
    border: '1px solid var(--semi-color-border)',
    borderRadius: '16px',
    height: '100%',
    width: '100%',
}

interface ChatDetailProps {
    chatId: number | null;
    onSend: (content: string, attachments: Attachment[]) => void;
}

const roleConfig = {
    user: {
        name: '你',
        avatar: 'https://lf3-static.bytednsdoc.com/obj/eden-cn/ptlz_zlp/ljhwZthlaukjlkulzlp/docs-icon.png',
    },
    assistant: {
        name: 'AI',
        avatar: 'https://lf3-static.bytednsdoc.com/obj/eden-cn/ptlz_zlp/ljhwZthlaukjlkulzlp/other/logo.png',
    },
    system: {
        name: '系统',
        avatar: 'https://lf3-static.bytednsdoc.com/obj/eden-cn/ptlz_zlp/ljhwZthlaukjlkulzlp/other/logo.png',
    },
};

function mapLocalToSemiMessages(messages: LocalMessage[]): any[] {
    return (messages || []).map((msg) => {
        let role: 'user' | 'assistant' | 'system' = 'assistant';
        if (msg.sender_id === 'You' || msg.sender_id === 'user') role = 'user';
        else if (msg.sender_id === 'system') role = 'system';
        else role = 'assistant';
        return {
            role,
            id: String(msg.id),
            createAt: new Date(msg.txTimestamp).getTime(),
            content: msg.content,
            status: msg.status === 'sending' ? 'loading' : (msg.status === 'failed' ? 'error' : 'complete'),
            // 可扩展 attachment 映射
        };
    });
}

const uploadProps = {
    action: 'https://api.semi.design/upload',
};

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId, onSend }) => {
    const { t } = useTranslation();
    const { chats } = useAppDataStore();
    const chat = useMemo(() => (Array.isArray(chats) ? chats.find((c: LocalChat) => c.id === chatId) : undefined), [chats, chatId]);

    // 适配消息数据
    const semiMessages = useMemo(() => mapLocalToSemiMessages(chat?.messages || []), [chat]);

    // 发送消息适配
    const handleMessageSend = (content: string, attachment: any[]) => {
        // attachment 结构可扩展
        onSend(content, attachment || []);
    };

    if (!chat) {
        return (
            <EmptyState>
                {t('pages.chat.selectChat')}
            </EmptyState>
        );
    }

    return (
        <ChatDetailWrapper>
            <ChatHeader>
                <ChatInfo>
                    <StyledAvatar>
                        {chat.type === 'user' ? <UserOutlined /> : chat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />}
                    </StyledAvatar>
                    <ChatName>{chat.name}</ChatName>
                </ChatInfo>
                <Button 
                    icon={<MoreOutlined />} 
                    type="text"
                    style={{ color: 'var(--text-secondary)' }}
                />
            </ChatHeader>
            <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <SemiChat
                    chats={semiMessages}
                    roleConfig={roleConfig}
                    onMessageSend={handleMessageSend}
                    style={commonOuterStyle}
                    align="leftRight"
                    mode="userBubble"
                    placeholder={t('pages.chat.typeMessage')}
                    uploadProps={uploadProps}
                />
            </div>
        </ChatDetailWrapper>
    );
};

export default ChatDetail; 