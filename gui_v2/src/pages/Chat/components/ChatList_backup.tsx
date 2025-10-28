import React, { useState } from 'react';
import { List, Badge, Avatar, Space, Typography, Tag, Button, Popconfirm, Modal } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, MinusOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat } from '../types/chat';
import SearchFilter from '../../../components/Common/SearchFilter';
import ActionButtons from '../../../components/Common/ActionButtons';
import AgentAnimation from './AgentAnimation';

const { Text } = Typography;

const ChatItem = styled.div<{ $isActive: boolean }>`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: ${props => props.$isActive ? 'var(--bg-tertiary)' : 'var(--bg-secondary)'};
    border-radius: 8px;
    margin: 4px 0;
    min-height: 60px;
    display: flex;
    align-items: center;
    position: relative;

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

    .chat-content {
        flex: 1;
        min-width: 0;
        overflow: hidden;
    }

    .chat-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 4px;
    }

    .chat-name {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .chat-message {
        color: var(--text-secondary);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        margin-right: 8px;
    }

    .chat-time {
        color: var(--text-secondary);
        font-size: 12px;
        white-space: nowrap;
        flex-shrink: 0;
    }

    .delete-button {
        opacity: 0;
        transition: all 0.2s ease;
        background-color: transparent !important;
        border: none !important;
        border-radius: 3px;
        color: #ff6b6b !important;
        width: 20px !important;
        height: 20px !important;
        min-width: 20px !important;
        padding: 0 !important;
        margin: 0 !important;
        display: flex;
        align-items: center;
        justify-content: center;
        line-height: 1;
        box-shadow: none !important;
        
        &:hover {
            background-color: rgba(255, 107, 107, 0.15) !important;
            color: #ff4757 !important;
            transform: scale(1.1);
            border: none !important;
        }

        &:focus {
            border: none !important;
            box-shadow: none !important;
        }

        .anticon {
            font-size: 12px;
            line-height: 1;
            margin: 0 !important;
        }
    }

    .delete-button-wrapper {
        position: absolute;
        top: 6px;
        right: 6px;
        z-index: 1;
        width: 18px;
        height: 18px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .delete-button.show {
        opacity: 1;
    }
`;

const ChatListContainer = styled.div`
    display: flex;
    flex-direction: column;
    height: 100%;
`;

const ChatListArea = styled.div`
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
`;

interface ChatListProps {
    chats: Chat[];
    activeChatId: string | null;
    onChatSelect: (chatId: string) => void;
    onChatDelete: (chatId: string) => void;
    onChatPin: (chatId: string) => void;
    onChatMute: (chatId: string) => void;
    onFilterChange: (filters: Record<string, any>) => void;
    onSearch?: (value: string) => void;
    onReset?: () => void;
    onAdd?: () => void;
    onEdit?: () => void;
    onRefresh?: () => void;
    onExport?: () => void;
    onImport?: () => void;
    onSettings?: () => void;
    currentAgentId?: string;
}

const ChatList: React.FC<ChatListProps> = ({
    chats,
    activeChatId,
    onChatSelect,
    onChatDelete,
    onChatPin,
    onChatMute,
    onFilterChange,
    onSearch = () => {},
    onReset = () => {},
    onAdd = () => {},
    onEdit = () => {},
    onRefresh = () => {},
    onExport = () => {},
    onImport = () => {},
    onSettings = () => {},
    currentAgentId
}) => {
    const { t } = useTranslation();
    const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
    const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
    const [hoveredDeleteButton, setHoveredDeleteButton] = useState<string | null>(null);

    // Ensure chats is always an array to prevent crashes
    const safeChats = Array.isArray(chats) ? chats.filter(chat => chat && chat.id) : [];

    const handleDeleteConfirm = (chatId: string) => {
        setSelectedChatId(chatId);
        setIsDeleteConfirmOpen(true);
    };

    const getAvatarIcon = (type: Chat['type']) => {
        switch (type) {
            case 'user-agent':
                return <RobotOutlined />;
            case 'group':
                return <TeamOutlined />;
            default:
                return <UserOutlined />;
        }
    };

    const handleConfirmDelete = () => {
        if (selectedChatId !== null) {
            onChatDelete(selectedChatId);
        }
        setIsDeleteConfirmOpen(false);
    };

    const handleCancelDelete = () => {
        setIsDeleteConfirmOpen(false);
    };

    const handleDeleteButtonMouseEnter = (chatId: string) => {
        setHoveredDeleteButton(chatId);
    };

    const handleDeleteButtonMouseLeave = () => {
        setHoveredDeleteButton(null);
    };

    // FormatTimeDisplay
    const formatTime = (timestamp?: number): string => {
        if (!timestamp) return '--:--';
        
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) return '--:--';
        
        const now = new Date();
        
        // 同一天DisplayTime，不同天DisplayDate
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } else {
            // 一周内Display星期几，否则DisplayDate
            const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));
            if (diffDays < 7) {
                const weekdays = [
                    t('pages.chat.weekday0'), // 周日
                    t('pages.chat.weekday1'), // 周一
                    t('pages.chat.weekday2'), // 周二
                    t('pages.chat.weekday3'), // 周三
                    t('pages.chat.weekday4'), // 周四
                    t('pages.chat.weekday5'), // 周五
                    t('pages.chat.weekday6'), // 周六
                ];
                return weekdays[date.getDay()];
            } else {
                return date.toLocaleDateString([], { month: 'numeric', day: 'numeric' });
            }
        }
    };

    return (
        <ChatListContainer>
            <SearchFilter
                onSearch={onSearch}
                placeholder={t('pages.chat.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={onAdd}
                onDelete={() => {}}
                onSettings={onSettings}
                addText={t('pages.chat.addChat')}
                deleteText={t('pages.chat.deleteChat')}
                settingsText={t('pages.chat.chatSettings')}
            />
            <ChatListArea>
                <List
                    rowKey={(chat) => (chat as any).id}
                    dataSource={safeChats}
                    renderItem={chat => {
                        return (
                            <ChatItem
                                key={chat.id}
                                $isActive={chat.id === activeChatId}
                                onClick={() => onChatSelect(chat.id)}
                            >
                                <div 
                                    className="delete-button-wrapper"
                                    onClick={(e) => e.stopPropagation()}
                                    onMouseDown={(e) => e.stopPropagation()}
                                >
                                    <Button
                                        type="text"
                                        size="small"
                                        icon={<MinusOutlined />}
                                        className={`delete-button ${hoveredDeleteButton === chat.id ? 'show' : ''}`}
                                        onClick={() => handleDeleteConfirm(chat.id)}
                                        style={{ 
                                            fontSize: '11px', 
                                            lineHeight: '1',
                                            padding: '0',
                                            margin: '0',
                                            width: '18px',
                                            height: '18px',
                                            minWidth: '18px',
                                            border: 'none',
                                            boxShadow: 'none'
                                        }}
                                        onMouseEnter={() => handleDeleteButtonMouseEnter(chat.id)}
                                        onMouseLeave={handleDeleteButtonMouseLeave}
                                    />
                                </div>
                                <div className="chat-content">
                                    <div className="chat-header">
                                        <Avatar icon={getAvatarIcon(chat.type)} size="small" />
                                        <Text strong className="chat-name">{chat.name}</Text>
                                        {chat.unread > 0 && (
                                            <Badge count={chat.unread} />
                                        )}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                        <Text type="secondary" className="chat-message">
                                            {chat.lastMsg || t('pages.chat.noMessages')}
                                        </Text>
                                        <Text type="secondary" className="chat-time">
                                            {formatTime(chat.lastMsgTime)}
                                        </Text>
                                    </div>
                                </div>
                            </ChatItem>
                        );
                    }}
                />
            </ChatListArea>
            <Modal
                title={t('pages.chat.deleteConfirmTitle')}
                open={isDeleteConfirmOpen}
                onOk={handleConfirmDelete}
                onCancel={handleCancelDelete}
                okText={t('common.confirm')}
                cancelText={t('common.cancel')}
                okButtonProps={{ danger: true }}
            >
                <div style={{ padding: '16px 0' }}>
                    <p style={{ marginBottom: '12px', color: 'var(--text-secondary)' }}>
                        {t('pages.chat.deleteConfirmDescription')}
                    </p>
                    <div style={{ 
                        background: 'var(--bg-secondary)', 
                        padding: '12px', 
                        borderRadius: '6px',
                        border: '1px solid var(--border-color)',
                        marginTop: '8px'
                    }}>
                        <strong style={{ color: 'var(--text-primary)' }}>
                            {selectedChatId && safeChats.length > 0 ? (safeChats.find(chat => chat.id === selectedChatId)?.name || '') : ''}
                        </strong>
                    </div>
                </div>
            </Modal>
        </ChatListContainer>
    );
};

export default React.memo(ChatList); 