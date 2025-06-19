import React, { useState } from 'react';
import { List, Badge, Avatar, Space, Typography, Tag, Button, Popconfirm, Modal } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined, MinusOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat } from '../types/chat';
import SearchFilter from '../../../components/Common/SearchFilter';
import ActionButtons from '../../../components/Common/ActionButtons';

const { Text } = Typography;

const ChatItem = styled.div<{ isActive: boolean }>`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: ${props => props.isActive ? 'var(--bg-tertiary)' : 'var(--bg-secondary)'};
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
    activeChatId: number | null;
    onChatSelect: (chatId: number) => void;
    onChatDelete: (chatId: number) => void;
    onChatPin: (chatId: number) => void;
    onChatMute: (chatId: number) => void;
    onFilterChange: (filters: Record<string, any>) => void;
    onSearch?: (value: string) => void;
    onReset?: () => void;
    onAdd?: () => void;
    onEdit?: () => void;
    onRefresh?: () => void;
    onExport?: () => void;
    onImport?: () => void;
    onSettings?: () => void;
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
    onSettings = () => {}
}) => {
    const { t } = useTranslation();
    const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
    const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
    const [hoveredDeleteButton, setHoveredDeleteButton] = useState<number | null>(null);

    const handleDeleteConfirm = (chatId: number) => {
        setSelectedChatId(chatId);
        setIsDeleteConfirmOpen(true);
    };

    const getAvatarIcon = (type: Chat['type']) => {
        switch (type) {
            case 'user':
                return <UserOutlined />;
            case 'bot':
                return <RobotOutlined />;
            case 'group':
                return <TeamOutlined />;
        }
    };

    const getStatusColor = (status: Chat['status']) => {
        switch (status) {
            case 'online':
                return 'success';
            case 'busy':
                return 'warning';
            default:
                return 'default';
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

    const handleDeleteButtonMouseEnter = (chatId: number) => {
        setHoveredDeleteButton(chatId);
    };

    const handleDeleteButtonMouseLeave = () => {
        setHoveredDeleteButton(null);
    };

    return (
        <ChatListContainer>
            <SearchFilter
                onSearch={onSearch}
                placeholder={t('pages.chat.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={onAdd}
                onEdit={onEdit}
                onDelete={() => {}}
                onRefresh={onRefresh}
                onExport={onExport}
                onImport={onImport}
                onSettings={onSettings}
                addText={t('pages.chat.addChat')}
                editText={t('pages.chat.editChat')}
                deleteText={t('pages.chat.deleteChat')}
                refreshText={t('pages.chat.refreshChat')}
                exportText={t('pages.chat.exportChat')}
                importText={t('pages.chat.importChat')}
                settingsText={t('pages.chat.chatSettings')}
                visibleButtons={['add', 'refresh']}
            />
            <ChatListArea>
                <List
                    dataSource={chats}
                    renderItem={chat => (
                        <ChatItem
                            key={chat.id}
                            isActive={chat.id === activeChatId}
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
                                    <Badge status={getStatusColor(chat.status)} />
                                    <Avatar icon={getAvatarIcon(chat.type)} size="small" />
                                    <Text strong className="chat-name">{chat.name}</Text>
                                    {chat.unreadCount > 0 && (
                                        <Badge count={chat.unreadCount} />
                                    )}
                                </div>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <Text type="secondary" className="chat-message">
                                        {chat.lastMessage || 'No messages yet'}
                                    </Text>
                                    <Text type="secondary" className="chat-time">
                                        {(() => {
                                            const date = new Date(chat.lastMessageTime);
                                            if (isNaN(date.getTime())) {
                                                return '--:--';
                                            }
                                            return date.toLocaleTimeString([], {
                                                hour: '2-digit',
                                                minute: '2-digit'
                                            });
                                        })()}
                                    </Text>
                                </div>
                            </div>
                        </ChatItem>
                    )}
                />
            </ChatListArea>
            <Modal
                title={t('common.confirm')}
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
                            {chats.find(chat => chat.id === selectedChatId)?.name}
                        </strong>
                    </div>
                </div>
            </Modal>
        </ChatListContainer>
    );
};

export default ChatList; 