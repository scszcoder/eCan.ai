import React from 'react';
import { List, Badge, Avatar, Space, Typography, Tag } from 'antd';
import { UserOutlined, RobotOutlined, TeamOutlined } from '@ant-design/icons';
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

    return (
        <>
            <SearchFilter
                onSearch={onSearch}
                onFilterChange={onFilterChange}
                onReset={onReset}
                placeholder={t('pages.chat.searchPlaceholder')}
            />
            <ActionButtons
                onAdd={onAdd}
                onEdit={onEdit}
                onDelete={onChatDelete}
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
            />
            <List
                dataSource={chats}
                renderItem={chat => (
                    <ChatItem
                        key={chat.id}
                        isActive={chat.id === activeChatId}
                        onClick={() => onChatSelect(chat.id)}
                    >
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Space>
                                <Badge status={getStatusColor(chat.status)} />
                                <Avatar icon={getAvatarIcon(chat.type)} />
                                <Text strong>{chat.name}</Text>
                                {chat.unreadCount > 0 && (
                                    <Badge count={chat.unreadCount} />
                                )}
                            </Space>
                            <Space>
                                <Text type="secondary" ellipsis={true} style={{ maxWidth: '200px' }}>
                                    {chat.lastMessage || 'No messages yet'}
                                </Text>
                                <Text type="secondary">
                                    {new Date(chat.lastMessageTime).toLocaleTimeString([], {
                                        hour: '2-digit',
                                        minute: '2-digit'
                                    })}
                                </Text>
                            </Space>
                        </Space>
                    </ChatItem>
                )}
            />
        </>
    );
};

export default ChatList; 