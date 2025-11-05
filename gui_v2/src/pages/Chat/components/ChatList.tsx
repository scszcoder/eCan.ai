import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { List, Badge, Avatar, Typography, Button, Modal, Tooltip } from 'antd';
import { RobotOutlined, TeamOutlined, MinusOutlined, FilterOutlined } from '@ant-design/icons';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { Chat, Member } from '../types/chat';
import SearchFilter from '../../../components/Common/SearchFilter';
import AgentAnimation from './AgentAnimation';
import { useAgentStore } from '../../../stores/agentStore';
import { GroupIconColored } from './GroupIcon';

const { Text } = Typography;

// Group Avatar Component - shows multiple member avatars in grid layout (up to 9)
const GroupAvatar = styled.div<{ $memberCount: number }>`
    position: relative;
    width: 40px;
    height: 40px;
    flex-shrink: 0;
    display: grid;
    gap: 1px;
    background: var(--bg-secondary);
    border-radius: 6px;
    overflow: hidden;
    
    /* 1 member: full size */
    grid-template-columns: ${props => props.$memberCount === 1 ? '1fr' : 
                                     props.$memberCount <= 4 ? 'repeat(2, 1fr)' : 
                                     'repeat(3, 1fr)'};
    grid-template-rows: ${props => props.$memberCount === 1 ? '1fr' : 
                                  props.$memberCount <= 4 ? 'repeat(2, 1fr)' : 
                                  'repeat(3, 1fr)'};
    
    .avatar-item {
        width: 100%;
        height: 100%;
        border: none;
        border-radius: 0;
        
        .ant-avatar {
            width: 100%;
            height: 100%;
            border-radius: 0;
        }
        
        img {
            object-fit: cover;
        }
    }
    
    /* Hide extra avatars beyond 9 */
    .avatar-item:nth-of-type(n+10) {
        display: none;
    }
`;

// Member count badge
const MemberCountBadge = styled.div`
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    background: var(--bg-tertiary);
    border-radius: 10px;
    font-size: 11px;
    color: var(--text-secondary);
    
    .anticon {
        font-size: 10px;
    }
`;

// HelperFunction：Format lastMsg Display
const formatLastMsg = (lastMsg: any): string => {
    if (!lastMsg) return '';
    
    // If是字符串，尝试Parse
    if (typeof lastMsg === 'string') {
        try {
            const parsed = JSON.parse(lastMsg);
            return parsed.text || parsed.content || lastMsg;
        } catch {
            return lastMsg;
        }
    }
    
    // If是对象，提取 text 或 content
    if (typeof lastMsg === 'object') {
        return lastMsg.text || lastMsg.content || JSON.stringify(lastMsg);
    }
    
    return String(lastMsg);
};

const ChatItem = styled.div<{ $isActive: boolean }>`
    padding: 12px;
    padding-left: ${props => props.$isActive ? '16px' : '12px'};
    border-bottom: 1px solid var(--border-color);
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    background: ${props => props.$isActive 
        ? 'linear-gradient(90deg, rgba(59, 130, 246, 0.15) 0%, rgba(51, 65, 85, 0.6) 100%)' 
        : 'var(--bg-secondary)'};
    border-radius: 8px;
    margin: 2px 0;
    min-height: 60px;
    display: flex;
    align-items: center;
    position: relative;
    border-left: ${props => props.$isActive ? '3px solid rgba(59, 130, 246, 0.8)' : '3px solid transparent'};
    box-shadow: ${props => props.$isActive ? '0 2px 12px rgba(59, 130, 246, 0.2)' : 'none'};

    &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 0;
        bottom: 0;
        width: 3px;
        background: ${props => props.$isActive 
            ? 'linear-gradient(180deg, rgba(59, 130, 246, 0.9) 0%, rgba(96, 165, 250, 0.7) 100%)' 
            : 'transparent'};
        border-radius: 8px 0 0 8px;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    &:hover {
        background: ${props => props.$isActive 
            ? 'linear-gradient(90deg, rgba(59, 130, 246, 0.2) 0%, rgba(51, 65, 85, 0.7) 100%)' 
            : 'var(--bg-tertiary)'};
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
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
        font-weight: ${props => props.$isActive ? '600' : '500'};
        color: ${props => props.$isActive ? 'rgba(248, 250, 252, 0.98)' : 'var(--text-primary)'};
    }

    .chat-message {
        color: ${props => props.$isActive ? 'rgba(203, 213, 225, 0.9)' : 'var(--text-secondary)'};
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        flex: 1;
        margin-right: 8px;
    }

    .chat-time {
        color: ${props => props.$isActive ? 'rgba(148, 163, 184, 0.9)' : 'var(--text-secondary)'};
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

const StyledFilterButton = styled(Button)`
    height: 36px !important;
    width: 36px !important;
    border-radius: 8px !important;
    background: rgba(51, 65, 85, 0.5) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;

    &:hover {
        background: rgba(51, 65, 85, 0.7) !important;
        border-color: rgba(59, 130, 246, 0.3) !important;
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15) !important;
    }

    &:active {
        opacity: 0.8 !important;
    }

    &.ant-btn-primary {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.9) 0%, rgba(99, 102, 241, 0.9) 100%) !important;
        border-color: rgba(59, 130, 246, 0.5) !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;

        &:hover {
            background: linear-gradient(135deg, rgba(59, 130, 246, 1) 0%, rgba(99, 102, 241, 1) 100%) !important;
            border-color: rgba(59, 130, 246, 0.7) !important;
            box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4) !important;
        }
    }

    .anticon {
        color: rgba(59, 130, 246, 0.9) !important;
        font-size: 16px !important;
        transition: all 0.3s ease !important;
    }

    &:hover .anticon {
        color: rgba(96, 165, 250, 1) !important;
    }

    &.ant-btn-primary .anticon {
        color: white !important;
    }
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
    onFilterClick?: () => void;
    filterAgentId?: string | null;
}

const ChatList: React.FC<ChatListProps> = ({
    chats,
    activeChatId,
    onChatSelect,
    onChatDelete,
    onChatPin: _onChatPin,
    onChatMute: _onChatMute,
    onFilterChange: _onFilterChange,
    onSearch = () => {},
    onReset: _onReset,
    onAdd: _onAdd,
    onEdit: _onEdit,
    onRefresh: _onRefresh,
    onExport: _onExport,
    onImport: _onImport,
    onSettings: _onSettings,
    currentAgentId,
    onFilterClick,
    filterAgentId,
}) => {
    const { t } = useTranslation();
    const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
    const [selectedChatId, setSelectedChatId] = useState<string | null>(null);
    const [hoveredDeleteButton, setHoveredDeleteButton] = useState<string | null>(null);
    
    // ScrollPositionSave
    const chatListAreaRef = useRef<HTMLDivElement>(null);
    const savedScrollPosition = useRef<number>(0);
    
    // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
    useEffectOnActive(
        () => {
            const container = chatListAreaRef.current;
            if (container && savedScrollPosition.current > 0) {
                requestAnimationFrame(() => {
                    container.scrollTop = savedScrollPosition.current;
                });
            }
            
            return () => {
                const container = chatListAreaRef.current;
                if (container) {
                    savedScrollPosition.current = container.scrollTop;
                }
            };
        },
        []
    );
    
    // Get agents from store
    const agents = useAgentStore((state) => state.agents);
    
    // Ref to store chat item DOM elements for scrolling
    const chatItemRefs = useRef<Map<string, HTMLDivElement>>(new Map());
    
    // Auto-scroll to active chat item when activeChatId changes
    useEffect(() => {
        if (!activeChatId) return;
        
        // Small delay to ensure DOM is rendered
        const timer = setTimeout(() => {
            const chatElement = chatItemRefs.current.get(activeChatId);
            if (chatElement) {
                chatElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest', // Scroll only if needed
                    inline: 'nearest'
                });
            }
        }, 100);
        
        return () => clearTimeout(timer);
    }, [activeChatId]);
    
    // Get current agent's avatar data
    const currentAgentAvatar = useMemo(() => {
        if (!currentAgentId || !agents) return undefined;
        // Agent ID is in card.id
        const agent = agents.find(a => a.card?.id === currentAgentId);
        return agent?.avatar;
    }, [currentAgentId, agents, activeChatId]);

    // Ensure chats is always an array to prevent crashes
    const safeChats = useMemo(() => (
        Array.isArray(chats) ? chats.filter(chat => chat && chat.id) : []
    ), [chats]);

    const getActivityTimestamp = useCallback((chat: Chat): number => {
        const candidates: (number | string | undefined)[] = [
            chat.lastMsgTime,
            chat.updatedAt,
            chat.updated_at,
            chat.createdAt,
            chat.created_at,
        ];

        for (const candidate of candidates) {
            if (typeof candidate === 'number' && !Number.isNaN(candidate)) {
                return candidate;
            }
            if (typeof candidate === 'string' && candidate) {
                const parsed = Date.parse(candidate);
                if (!Number.isNaN(parsed)) {
                    return parsed;
                }
            }
        }
        return 0;
    }, []);

    const sortedChats = useMemo(() => {
        return [...safeChats].sort((a, b) => {
            const aPinned = a.pinned ? 1 : 0;
            const bPinned = b.pinned ? 1 : 0;
            if (aPinned !== bPinned) {
                return bPinned - aPinned; // pinned chats first
            }

            const aTime = getActivityTimestamp(a);
            const bTime = getActivityTimestamp(b);
            if (aTime !== bTime) {
                return bTime - aTime; // latest activity first
            }

            return (b.unread ?? 0) - (a.unread ?? 0);
        });
    }, [safeChats, getActivityTimestamp]);

    const handleDeleteConfirm = (chatId: string) => {
        setSelectedChatId(chatId);
        setIsDeleteConfirmOpen(true);
    };
    
    // Get My Twin Agent ID
    const getMyTwinAgent = useAgentStore((state) => state.getMyTwinAgent);
    const myTwinAgent = getMyTwinAgent();
    const myTwinAgentId = myTwinAgent?.card?.id;
    
    // Get member names combined, with priority agent first
    const getMemberNames = (members: Member[], chatName?: string, priorityAgentId?: string): string => {
        if (!members || members.length === 0) return chatName || '';
        
        // Filter out My Twin Agent from members
        const filteredMembers = members.filter(m => m.userId !== myTwinAgentId);
        
        if (filteredMembers.length === 0) {
            // If only My Twin Agent, show chat name
            return chatName || '';
        }
        
        // Sort members: priority agent first, then others
        const sortedMembers = [...filteredMembers].sort((a, b) => {
            if (priorityAgentId) {
                if (a.userId === priorityAgentId) return -1;
                if (b.userId === priorityAgentId) return 1;
            }
            return 0;
        });
        
        const memberNames = sortedMembers.map(m => m.agentName || m.name).filter(Boolean).join(', ');
        // If no member names, fallback to chat name
        return memberNames || chatName || '';
    };
    
    // Get short member names for display (truncated)
    const getShortMemberNames = (members: Member[], chatName?: string, priorityAgentId?: string, maxLength: number = 30): string => {
        const fullNames = getMemberNames(members, chatName, priorityAgentId);
        if (!fullNames) return chatName || '';
        if (fullNames.length <= maxLength) return fullNames;
        return fullNames.substring(0, maxLength) + '...';
    };
    
    // Get agent avatar by ID
    const getAgentAvatar = (agentId: string) => {
        if (!agents) return undefined;
        const agent = agents.find(a => a.card?.id === agentId);
        if (!agent?.avatar) return undefined;
        
        // If avatar is object with imageUrl, return the imageUrl
        if (typeof agent.avatar === 'object' && 'imageUrl' in agent.avatar) {
            return (agent.avatar as { imageUrl: string }).imageUrl;
        }
        
        // If avatar is string, return it directly
        if (typeof agent.avatar === 'string') {
            return agent.avatar;
        }
        
        return undefined;
    };
    
    // Render chat avatar based on members count
    const renderGroupAvatar = (members: Member[], _chatType?: Chat['type']) => {
        if (!members || members.length === 0) {
            return <GroupIconColored size={40} />;
        }
        
        // Filter out My Twin Agent from members
        const filteredMembers = members.filter(m => m.userId !== myTwinAgentId);
        
        if (filteredMembers.length === 0) {
            // If only My Twin Agent, show default group icon
            return <GroupIconColored size={40} />;
        }
        
        // Case 1: Only 1 other member (2 people total including My Twin)
        // Show the other member's avatar
        if (filteredMembers.length === 1) {
            const member = filteredMembers[0];
            // Try to get latest avatar from agent store, fallback to member.avatar
            const avatarSrc = getAgentAvatar(member.userId) || member.avatar;
            return (
                <Avatar 
                    src={avatarSrc} 
                    icon={<RobotOutlined />} 
                    size={40}
                />
            );
        }
        
        // Case 2: More than 1 other member (3+ people total)
        // Show composite avatar with up to 9 members
        const displayMembers = filteredMembers.slice(0, 9);
        
        return (
            <GroupAvatar $memberCount={displayMembers.length}>
                {displayMembers.map((member) => {
                    // Try to get latest avatar from agent store, fallback to member.avatar
                    const avatarSrc = getAgentAvatar(member.userId) || member.avatar;
                    return (
                        <div key={member.userId} className="avatar-item">
                            <Avatar
                                src={avatarSrc}
                                icon={<RobotOutlined />}
                                shape="square"
                                style={{ width: '100%', height: '100%' }}
                            />
                        </div>
                    );
                })}
            </GroupAvatar>
        );
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
            {currentAgentId ? (
                <div style={{ 
                    display: 'flex', 
                    flexDirection: 'column',
                    alignItems: 'center',
                    padding: '4px 12px 0',
                    paddingBottom: '8px',
                    marginBottom: '8px',
                    flexShrink: 0,
                    height: 'auto',
                    maxHeight: '180px',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
                }}>
                    <AgentAnimation 
                        key={currentAgentId} 
                        agentId={currentAgentId} 
                        agentAvatar={currentAgentAvatar}
                    />
                    <div style={{
                        marginTop: 4,
                        fontSize: 11,
                        color: 'rgba(255,255,255,0.65)'
                    }}>
                        ID: <span style={{ fontFamily: 'monospace' }}>{currentAgentId}</span>
                    </div>
                </div>
            ) : null}
            <div style={{ 
                display: 'flex', 
                gap: 4, 
                marginBottom: 8, 
                paddingBottom: 8,
                alignItems: 'center',
                borderBottom: '1px solid rgba(255, 255, 255, 0.08)'
            }}>
                <div style={{ flex: 1 }}>
                    <SearchFilter
                        onSearch={onSearch}
                        placeholder={t('pages.chat.searchMessages')}
                    />
                </div>
                {onFilterClick && (
                    <Tooltip title={t('pages.chat.filterByAgent')}>
                        <StyledFilterButton
                            icon={<FilterOutlined />}
                            onClick={onFilterClick}
                            type="text"
                        />
                    </Tooltip>
                )}
            </div>
            <ChatListArea ref={chatListAreaRef}>
                <List
                    rowKey={(chat) => (chat as any).id}
                    dataSource={sortedChats}
                    renderItem={chat => {
                        return (
                            <ChatItem
                                key={chat.id}
                                ref={(el) => {
                                    if (el) {
                                        chatItemRefs.current.set(chat.id, el);
                                    } else {
                                        chatItemRefs.current.delete(chat.id);
                                    }
                                }}
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
                                        {renderGroupAvatar(chat.members, chat.type)}
                                        <div style={{ flex: 1, minWidth: 0, marginLeft: 8 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                                                <Tooltip title={getMemberNames(chat.members, chat.name, filterAgentId || undefined)}>
                                                    <Text strong className="chat-name">
                                                        {getShortMemberNames(chat.members, chat.name, filterAgentId || undefined, 25)}
                                                    </Text>
                                                </Tooltip>
                                                {chat.members && chat.members.length > 1 && (
                                                    <MemberCountBadge>
                                                        <TeamOutlined />
                                                        <span>{chat.members.length}</span>
                                                    </MemberCountBadge>
                                                )}
                                                {chat.unread > 0 && (
                                                    <Badge count={chat.unread} />
                                                )}
                                            </div>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                                <Text type="secondary" className="chat-message">
                                                    {formatLastMsg(chat.lastMsg) || t('pages.chat.noMessages')}
                                                </Text>
                                                <Text type="secondary" className="chat-time">
                                                    {formatTime(chat.lastMsgTime)}
                                                </Text>
                                            </div>
                                        </div>
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
                            {selectedChatId && sortedChats.length > 0 ? (sortedChats.find(chat => chat.id === selectedChatId)?.name || '') : ''}
                        </strong>
                    </div>
                </div>
            </Modal>
        </ChatListContainer>
    );
};

export default React.memo(ChatList);
