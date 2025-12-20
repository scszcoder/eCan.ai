import React, { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { useEffectOnActive } from 'keepalive-for-react';
import { Chat } from '../types/chat';
import { defaultRoleConfig, RoleConfig } from '../types/chat';
import { getUploadProps } from '../utils/attachmentHandler';
import ContentTypeRenderer from './ContentTypeRenderer';

import { protocolHandler } from '../utils/protocolHandler';
import { ChatDetailWrapper, commonOuterStyle } from '../styles/ChatDetail.styles';
import AttachmentList from './AttachmentList';
import { get_ipc_api } from '@/services/ipc_api';
import { Toast } from '@douyinfe/semi-ui';
import { removeMessageFromList } from '../utils/messageHandlers';
import { useMessages } from '../hooks/useMessages';
import { useUserStore } from '@/stores/userStore';
import { useAgentStore } from '@/stores/agentStore';
import { useChatStore } from '@/stores/domain/chatStore';
import { messageManager } from '../managers/MessageManager';

interface ChatDetailProps {
    chatId?: string | null;
    chats?: Chat[];
    onSend?: (content: string, attachments: any[]) => void;
    onMessageDelete?: (messageId: string) => void;
    setIsInitialLoading?: (loading: boolean) => void;
    onMessagesRead?: (chatId: string, count: number) => void;
    filterAgentId?: string | null;
}

function mergeAndSortMessages(...msgArrays: any[][]) {
  const map = new Map();
  msgArrays.flat().forEach(msg => {
    if (msg && msg.id) map.set(msg.id, msg);
  });
  // 按 createAt 升序（老Message在前，新Message在后）
  return Array.from(map.values()).sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId: rawChatId, chats = [], onSend, onMessageDelete, setIsInitialLoading, onMessagesRead, filterAgentId }) => {
    const chatId = rawChatId || '';
    const { t } = useTranslation();
    const wrapperRef = useRef<HTMLDivElement>(null);
    const lastMessageLengthRef = useRef<number>(0);
    const justSentMessageRef = useRef<boolean>(false);
    const { updateMessages } = useMessages(chatId);
    const [offset, setOffset] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const PAGE_SIZE = 20;
    const [pageMessages, setPageMessages] = useState<any[]>([]);
    const { allMessages } = useMessages(chatId);
    const [isInitialLoadingState, _setIsInitialLoading] = useState(false);
    const isInitialLoading = typeof setIsInitialLoading === 'function' ? undefined : isInitialLoadingState;
    const chatBoxRef = useRef<HTMLDivElement | null>(null);
    const prevMsgCountRef = useRef(pageMessages.length);
    
    // GetWhen前UserInformation
    const username = useUserStore(state => state.username) || 'default_user';
    const getMyTwinAgent = useAgentStore(state => state.getMyTwinAgent);
    const getAgentById = useAgentStore(state => state.getAgentById);
    const myTwinAgent = getMyTwinAgent();
    const currentUserId = myTwinAgent?.card?.id || `system_${username}`;
    const prevScrollHeightRef = useRef(0);
    const prevScrollTopRef = useRef(0);
    const isLoadingMoreRef = useRef(false);
    
    // Auto-scroll related refs
    const isAtBottomRef = useRef(true);
    const shouldAutoScrollRef = useRef(true);
    const scrollTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    
    // Scroll position restoration
    const scrollPositionRestoredRef = useRef(false);
    const saveScrollPositionTimeoutRef = useRef<NodeJS.Timeout | null>(null);
    const savedScrollPositionRef = useRef<number>(0); // SaveScrollPosition
    const unreadClearedRef = useRef(false);
    const clearingUnreadRef = useRef(false);
    
    // Timer management refs for cleanup
    const scrollTimersRef = useRef<NodeJS.Timeout[]>([]);
    const focusTimersRef = useRef<NodeJS.Timeout[]>([]);

    // Check if user is at the bottom of the chat
    const isAtBottom = useCallback(() => {
        const chatBox = chatBoxRef.current;
        if (!chatBox) return true;
        
        const threshold = 100; // Increased threshold for better detection
        const scrollBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight;
        const atBottom = scrollBottom <= threshold;
        
        // Update refs for tracking
        isAtBottomRef.current = atBottom;
        
        return atBottom;
    }, []);
    
    // Scroll to bottom of chat
    const scrollToBottom = useCallback((smooth: boolean = true) => {
        const chatBox = chatBoxRef.current;
        if (!chatBox) return;
        
        chatBox.scrollTo({
            top: chatBox.scrollHeight,
            behavior: smooth ? 'smooth' : 'auto'
        });
    }, []);
    
    // Clear all timers - cleanup function
    const clearAllTimers = useCallback(() => {
        scrollTimersRef.current.forEach(timer => clearTimeout(timer));
        focusTimersRef.current.forEach(timer => clearTimeout(timer));
        scrollTimersRef.current = [];
        focusTimersRef.current = [];
    }, []);
    
    // Load更多Message
    const handleLoadMore = useCallback(async () => {
        if (loadingMore || isInitialLoading || !hasMore || !chatId) {
            return;
        }
        // Record current scrollHeight and scrollTop
        const chatBox = chatBoxRef.current;
        if (chatBox) {
            prevScrollHeightRef.current = chatBox.scrollHeight;
            prevScrollTopRef.current = chatBox.scrollTop;
        }
        isLoadingMoreRef.current = true;
        setLoadingMore(true);
        const res = await get_ipc_api().chatApi.getChatMessages({
            chatId,
            limit: PAGE_SIZE,
            offset: pageMessages.length,
            reverse: true  // Get更早的Message（倒序）
        });
        let newMsgs: any[] = [];
        if (res.success && res.data && typeof res.data === 'object' && Array.isArray((res.data as any).data)) {
            newMsgs = (res.data as any).data;
        }
        setPageMessages(prev => mergeAndSortMessages(newMsgs, prev));
        setOffset(offset + newMsgs.length);
        setHasMore(newMsgs.length === PAGE_SIZE);
        setLoadingMore(false);
    }, [loadingMore, isInitialLoading, hasMore, chatId, pageMessages.length, offset]);

    // Note：ScrollPosition由 KeepAlive 自动保持，不Need手动Save
    // 这个Callback保留是为了Compatible性，但实际上不做任何事情
    const saveScrollPosition = useCallback(() => {
        // KeepAlive 会自动保持ScrollPosition
    }, []);
    
    // Handle scroll position detection
    const markChatAsRead = useCallback((targetChatId: string) => {
        try {
            // Update both chatStore and messageManager
            useChatStore.getState().markAsRead(targetChatId);
            messageManager.markAsRead(targetChatId);
        } catch (error) {
            console.error('Failed to update chat unread state:', error);
        }
    }, []);

    const clearUnread = useCallback((targetChatId: string) => {
        if (!targetChatId || unreadClearedRef.current || clearingUnreadRef.current) {
            return;
        }

        clearingUnreadRef.current = true;
        get_ipc_api().chatApi.cleanChatUnRead(targetChatId)
            .then(() => {
                markChatAsRead(targetChatId);
                unreadClearedRef.current = true;
            })
            .catch(err => {
                console.error('Failed to clean chat unread:', err);
            })
            .finally(() => {
                clearingUnreadRef.current = false;
            });
    }, [markChatAsRead]);

    const handleScroll = useCallback((e: Event) => {
        const target = e.target as HTMLElement;
        
        // Update scroll position tracking
        const nowAtBottom = isAtBottom();
        shouldAutoScrollRef.current = nowAtBottom;

        if (nowAtBottom) {
            clearUnread(chatId);
        }
        
        // Clear any pending scroll timeout
        if (scrollTimeoutRef.current) {
            clearTimeout(scrollTimeoutRef.current);
        }
        
        // Save scroll position (debounced)
        if (saveScrollPositionTimeoutRef.current) {
            clearTimeout(saveScrollPositionTimeoutRef.current);
        }
        saveScrollPositionTimeoutRef.current = setTimeout(() => {
            saveScrollPosition();
        }, 300);
        
        // Load more messages when scrolled to top
        if (target.scrollTop === 0) {
            handleLoadMore();
        }
    }, [isAtBottom, handleLoadMore, saveScrollPosition, clearUnread, chatId]);
    
    // 懒Load可见Content：仅在可见时RenderMessageContent，减少首屏Render压力
    const LazyVisible = React.memo<{ children: React.ReactNode }>(({ children }) => {
        const [visible, setVisible] = useState(false);
        const itemRef = useRef<HTMLDivElement | null>(null);
        useEffect(() => {
            const rootEl = chatBoxRef.current || undefined;
            const observer = new IntersectionObserver(
                (entries) => {
                    entries.forEach((entry) => {
                        if (entry.isIntersecting) {
                            setVisible(true);
                            if (itemRef.current) observer.unobserve(itemRef.current);
                        }
                    });
                },
                { root: rootEl, rootMargin: '100px 0px', threshold: 0.01 }
            );
            if (itemRef.current) observer.observe(itemRef.current);
            return () => observer.disconnect();
        }, []);
        return <div ref={itemRef}>{visible ? children : null}</div>;
    });

    // Initialize协议Process器
    useEffect(() => {
        protocolHandler.init();
    }, []);

    // 根据 chatId Get对应的聊天Data
    const currentChat = useMemo(() => {
        if (!chatId || !chats.length) return null;
        return chats.find(chat => chat.id === chatId);
    }, [chatId, chats]);


    // ProcessMessage，确保content是字符串
    const messages = useMemo<any[]>(() => {
        // If有When前聊天，使用其Message
        if (currentChat && Array.isArray(currentChat.messages)) {
            return currentChat.messages;
        }
        // 否则返回空数组
        return [];
    }, [currentChat]);

    // 聚焦Input框的Function
    const focusInputArea = useCallback(() => {
        try {
            // 尝试多种Select器找到Input框
            let inputArea: HTMLTextAreaElement | null = null;
            
            // 尝试不同的Select器找到Input框
            inputArea = document.querySelector('.semi-chat-inputbox textarea') as HTMLTextAreaElement;
            if (!inputArea) {
                inputArea = document.querySelector('.semi-input-textarea') as HTMLTextAreaElement;
            }
            if (!inputArea) {
                inputArea = document.querySelector('textarea[placeholder]') as HTMLTextAreaElement;
            }
            
            if (inputArea) {
                inputArea.focus();
                
                // 尝试将光标Move到文本末尾
                if (typeof inputArea.selectionStart === 'number') {
                    try {
                        const length = inputArea.value.length;
                        inputArea.selectionStart = length;
                        inputArea.selectionEnd = length;
                    } catch (e) {
                        // 忽略Error
                    }
                }
            }
        } catch (error) {
            // 忽略Error
        }
    }, []);

    // 检测MessageList变化，If有新Message，尝试聚焦Input框
    useEffect(() => {
        if (messages.length > lastMessageLengthRef.current) {
            // MessageList增加了，可能是Send了新Message
            setTimeout(focusInputArea, 100);
        }
        lastMessageLengthRef.current = messages.length;
    }, [messages.length, focusInputArea]);

    // CustomMessageSendProcessFunction
    const handleMessageSend = useCallback((content: string, attachments: any[]) => {
        justSentMessageRef.current = true;
        // When user sends a message, they should auto-scroll to see their message and responses
        shouldAutoScrollRef.current = true;
        isAtBottomRef.current = true;
        
        // 构造新Message对象
        const tempId = `user_msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const userMessage = {
            id: tempId,
            chatId,
            role: 'user',
            createAt: Date.now(),
            senderId: '', // 可根据实际补充
            senderName: '', // 可根据实际补充
            content,
            status: 'sending',
            attachments
        };
        setPageMessages(prev => mergeAndSortMessages(prev, [userMessage]));
        
        // Clear previous timers before creating new ones
        clearAllTimers();
        
        // Scroll to bottom after sending message - use multiple attempts with different timings
        const scrollAttempts = [50, 100, 200, 300];
        scrollTimersRef.current = scrollAttempts.map(delay => 
            setTimeout(() => {
                scrollToBottom(true);
            }, delay)
        );
        
        if (onSend) {
            onSend(content, attachments);
        }
        focusInputArea();
        
        // 使用多次尝试确保聚焦Success
        const attempts = [100, 200, 300, 500, 1000];
        focusTimersRef.current = attempts.map(delay => 
            setTimeout(() => {
                if (justSentMessageRef.current) {
                    focusInputArea();
                }
            }, delay)
        );
        
        // 最后一次尝试后Reset标志
        const resetTimer = setTimeout(() => {
            justSentMessageRef.current = false;
        }, Math.max(...attempts) + 100);
        focusTimersRef.current.push(resetTimer);
    }, [chatId, onSend, focusInputArea, scrollToBottom, clearAllTimers]);

    // AddEventListen，防止Input框失去焦点
    // Optimize：在 useEffect InternalDefinitionProcessFunction，避免闭包陷阱
    useEffect(() => {
        const chatContainer = wrapperRef.current?.querySelector('.semi-chat-container');
        if (!chatContainer) return;
        
        // 在 useEffect InternalDefinitionProcessFunction，避免闭包问题
        const preventFocusLoss = () => {
            if (justSentMessageRef.current) {
                // 直接访问 DOM 元素聚焦，避免DependencyExternalFunction
                const inputArea = wrapperRef.current?.querySelector('.semi-chat-input');
                if (inputArea instanceof HTMLElement) {
                    setTimeout(() => inputArea.focus(), 0);
                }
            }
        };
        
        chatContainer.addEventListener('click', preventFocusLoss, true);
        
        return () => {
            chatContainer.removeEventListener('click', preventFocusLoss, true);
        };
    }, []); // RemoveDependency，避免重复CreateListen器

    // Chat title - show member names with priority agent first, with length limit
    const chatTitle = useMemo(() => {
        if (!currentChat) {
            return t('pages.chat.defaultTitle');
        }
        
        // If chat has members, show member names with priority sorting
        if (currentChat.members && currentChat.members.length > 0) {
            // Filter out My Twin Agent (current user) from members
            const filteredMembers = currentChat.members.filter(m => m.userId !== currentUserId);
            
            if (filteredMembers.length === 0) {
                // If only My Twin Agent, show chat name
                return currentChat.name;
            }
            
            // Sort members: priority agent (filterAgentId) first, then others
            const sortedMembers = [...filteredMembers].sort((a, b) => {
                if (filterAgentId) {
                    if (a.userId === filterAgentId) return -1;
                    if (b.userId === filterAgentId) return 1;
                }
                return 0;
            });
            
            const memberNames = sortedMembers
                .map(m => m.agentName || m.name)
                .filter(Boolean)
                .join(', ');
            
            // Limit length to 50 characters for title display
            if (memberNames.length > 50) {
                return memberNames.substring(0, 50) + '...';
            }
            
            return memberNames || currentChat.name;
        }
        
        return currentChat.name;
    }, [currentChat, t, filterAgentId, currentUserId]);

    // 为 Semi UI Chat 生成Stable的 key
    // Use a hash of chatTitle to avoid special characters in key
    const chatKey = useMemo(() => {
        // Create a simple hash from chatTitle to ensure key changes when title changes
        const titleHash = chatTitle.split('').reduce((acc, char) => {
            return ((acc << 5) - acc) + char.charCodeAt(0);
        }, 0);
        return `chat_${chatId}_${titleHash}`;
    }, [chatId, chatTitle]);

    const { enhancedMessages, roleConfig } = useMemo(() => {
        const baseConfig: RoleConfig = {
            user: { ...defaultRoleConfig.user },
            assistant: { ...defaultRoleConfig.assistant },
            system: { ...defaultRoleConfig.system },
            agent: { ...defaultRoleConfig.agent }
        };

        if (myTwinAgent?.card) {
            const { name } = myTwinAgent.card;
            const avatarUrl = myTwinAgent.avatar?.imageUrl;
            baseConfig.user = {
                ...baseConfig.user,
                name: name || baseConfig.user.name,
                avatar: avatarUrl || baseConfig.user.avatar
            };
        }
        const members = currentChat?.members || [];

        const enhanced = pageMessages.map(message => {
            if (message?.role === 'agent' && message?.senderId) {
                const member = members.find(m => m.userId === message.senderId);
                const agentInfo = getAgentById?.(message.senderId);
                const roleKey = `agent_${message.senderId}`;
                baseConfig[roleKey] = {
                    ...baseConfig.agent,
                    name: member?.agentName || member?.name || agentInfo?.card?.name || message.senderName || baseConfig.agent.name,
                    avatar: member?.avatar || agentInfo?.avatar?.imageUrl || baseConfig.agent.avatar,
                };
                return {
                    ...message,
                    role: roleKey
                };
            }

            if (message?.role === 'user' && message?.senderId && message.senderId !== currentUserId) {
                const member = members.find(m => m.userId === message.senderId);
                const agentInfo = getAgentById?.(message.senderId);
                const roleKey = `user_${message.senderId}`;
                baseConfig[roleKey] = {
                    ...baseConfig.user,
                    name: member?.agentName || member?.name || agentInfo?.card?.name || message.senderName || baseConfig.user.name,
                    avatar: member?.avatar || agentInfo?.avatar?.imageUrl || baseConfig.user.avatar,
                };
                return {
                    ...message,
                    role: roleKey
                };
            }

            if (message?.role === 'system') {
                const member = members.find(m => m.userId === message.senderId);
                const agentInfo = message?.senderId ? getAgentById?.(message.senderId) : null;
                if (member || agentInfo) {
                    baseConfig.system = {
                        ...baseConfig.system,
                        name: member?.agentName || member?.name || agentInfo?.card?.name || baseConfig.system.name,
                        avatar: member?.avatar || agentInfo?.avatar?.imageUrl || baseConfig.system.avatar,
                    };
                }
            }

            return message;
        });

        return { enhancedMessages: enhanced, roleConfig: baseConfig };
    }, [currentChat, currentUserId, myTwinAgent, pageMessages, getAgentById]);

    // ProcessFormSubmit
    const handleFormSubmit = useCallback(async (formId: string, _values: any, chatId: string, messageId: string, processedForm: any) => {
        const response = await get_ipc_api().chatApi.chatFormSubmit(chatId, messageId, formId, processedForm)
        if (response.success) {
            Toast.success(t('pages.chat.formSubmitSuccess'));
        } else {
            Toast.error(t('pages.chat.formSubmitFail'));
        }
    }, [t]);

    // Process卡片Action
    const handleCardAction = useCallback((action: string) => {
        if (onSend) {
            // Create卡片ActionMessage
            const actionContent = JSON.stringify({
                type: 'card_action',
                action
            });
            onSend(actionContent, []);
        }
    }, [onSend]);

    // DeleteMessageProcessFunction
    const handleMessageDelete = useCallback(async (message?: any) => {
        const messageId = message?.id;
        const chatId: string = message?.chatId ?? '';
        if (!messageId || !chatId) return;
        if (onMessageDelete) {
            onMessageDelete(messageId);
            return;
        }
        // Default行为：调用 ipc_api DeleteMessage
        const response = await get_ipc_api().chatApi.deleteMessage(chatId, messageId);
        if (response.success) {
            Toast.success(t('pages.chat.deleteMessageSuccess'));
            // LocalRemoveMessage
            updateMessages(chatId, removeMessageFromList(messages, messageId));
        } else {
            Toast.error(t('pages.chat.deleteMessageFail'));
        }
    }, [onMessageDelete, t, updateMessages, messages]);


    // 平滑分页：pageMessages 增加时，调整 scrollTop 保持视图无感衔接
    useEffect(() => {
        if (isLoadingMoreRef.current) {
            const chatBox = chatBoxRef.current;
            if (chatBox) {
                const newScrollHeight = chatBox.scrollHeight;
                chatBox.scrollTop = newScrollHeight - prevScrollHeightRef.current + prevScrollTopRef.current;
            }
            isLoadingMoreRef.current = false;
        }
        prevMsgCountRef.current = pageMessages.length;
    }, [pageMessages]);

    // ListenMessage区ScrollEvent
    useEffect(() => {
        if (!wrapperRef.current) return;
        const chatBox = wrapperRef.current.querySelector('.semi-chat-container');
        if (chatBox) chatBoxRef.current = chatBox as HTMLDivElement;
        if (!chatBox) return;
        
        chatBox.addEventListener('scroll', handleScroll);
        return () => {
            chatBox.removeEventListener('scroll', handleScroll);
            if (scrollTimeoutRef.current) {
                clearTimeout(scrollTimeoutRef.current);
            }
        };
    }, [handleScroll]);

    // Note：ScrollPosition由 KeepAlive 自动保持，不Need手动Restore
    // 这个Function保留是为了Compatible性，但实际上不做任何事情
    const restoreScrollPosition = useCallback(() => {
        // KeepAlive 会自动保持ScrollPosition
        return;
    }, []);
    
    // InitializeLoad第一页
    useEffect(() => {
        setOffset(0);
        setHasMore(true);
        setPageMessages([]);
        // Reset scroll position restoration flag
        scrollPositionRestoredRef.current = false;
        
        // Don't reset auto-scroll state - we'll determine it based on saved state
        // shouldAutoScrollRef.current = true;
        // isAtBottomRef.current = true;
        
        if (setIsInitialLoading) setIsInitialLoading(true); else _setIsInitialLoading(true);
        
        unreadClearedRef.current = false;
        clearingUnreadRef.current = false;

        // Load initial messages when chatId changes
        if (chatId) {
            const loadInitialMessages = async () => {
                try {
                    const res = await get_ipc_api().chatApi.getChatMessages({
                        chatId,
                        limit: PAGE_SIZE,
                        offset: 0,
                        reverse: true  // Get最新的Message（倒序）
                    });
                    
                    let initialMsgs: any[] = [];
                    if (res.success && res.data && typeof res.data === 'object' && Array.isArray((res.data as any).data)) {
                        initialMsgs = (res.data as any).data;
                    }
                    
                    // 使用 mergeAndSortMessages 确保Message按Time升序排列（老Message在前，新Message在后）
                    setPageMessages(mergeAndSortMessages(initialMsgs));
                    setOffset(initialMsgs.length);
                    setHasMore(initialMsgs.length === PAGE_SIZE);
                    
                    // 标记未读Message为已读
                    if (initialMsgs.length > 0 && currentUserId) {
                        // 只提取未读Message的 ID
                        const unreadMessageIds = initialMsgs
                            .filter(msg => msg.isRead === false)
                            .map(msg => msg.id)
                            .filter(Boolean);
                        
                        if (unreadMessageIds.length > 0) {
                            try {
                                const response = await get_ipc_api().chatApi.markMessageAsRead(unreadMessageIds, currentUserId);
                                if (response.success && response.data) {
                                    const actualUpdatedCount = (response.data as any)?.updated_ids?.length || unreadMessageIds.length;
                                    if (onMessagesRead) {
                                        onMessagesRead(chatId, actualUpdatedCount);
                                    }
                                }
                            } catch (err) {
                                console.error('Failed to mark messages as read:', err);
                            }

                            clearUnread(chatId);
                        }
                    }
                    
                    // 尝试RestoreScrollPosition，If没有Save的Position则Scroll到Bottom
                    // 增加Delay确保Message和 DOM 完全Render
                    setTimeout(() => {
                        // Note：ScrollPosition由 KeepAlive 自动保持
                        // 这里只NeedProcess新Message的Scroll
                        if (false) {
                            // 旧的ScrollRestore逻辑已Remove
                            restoreScrollPosition();
                        } else {
                            // 没有Save的Position，Scroll到Bottom（新聊天或首次Open）
                            shouldAutoScrollRef.current = true;
                            isAtBottomRef.current = true;
                            scrollToBottom(false);
                        }
                    }, 300); // 增加Delay从 200ms 到 300ms
                } catch (error) {
                    console.error('Failed to load initial messages:', error);
                } finally {
                    if (setIsInitialLoading) setIsInitialLoading(false); else _setIsInitialLoading(false);
                }
            };
            
            loadInitialMessages();
        } else {
            if (setIsInitialLoading) setIsInitialLoading(false); else _setIsInitialLoading(false);
        }
        
        // Cleanup: save scroll position when component unmounts or chatId changes
        return () => {
            if (saveScrollPositionTimeoutRef.current) {
                clearTimeout(saveScrollPositionTimeoutRef.current);
            }
            saveScrollPosition();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chatId, scrollToBottom, restoreScrollPosition, saveScrollPosition, username, clearUnread, currentUserId, onMessagesRead]);

    // Sync allMessages from useMessages hook to pageMessages for display
    useEffect(() => {
        if (!chatId) return;
        
        const globalMsgs = allMessages.get(chatId) || [];
        if (globalMsgs.length > 0) {
            let shouldClearUnread = false;

            setPageMessages(prev => {
                // Remove local "sending" messages that match global messages
                const filteredPrev = prev.filter(
                    m => !(m.status === 'sending' && globalMsgs.some(gm => gm.content === m.content))
                );
                
                // Only merge messages that are newer than the latest in current pageMessages
                const latestTime = filteredPrev.length > 0 ? filteredPrev[filteredPrev.length - 1].createAt : 0;
                const newMsgs = globalMsgs.filter(m => m.createAt > latestTime);
                
                const merged = mergeAndSortMessages(filteredPrev, newMsgs);
                
                // Check if user is at bottom before new messages arrive
                const wasAtBottom = isAtBottomRef.current;
                
                // If new incoming messages arrive, check if we should clear unread
                if (newMsgs.length > 0) {
                    const hasIncoming = newMsgs.some(msg => msg.senderId && msg.senderId !== currentUserId);
                    if (hasIncoming) {
                        unreadClearedRef.current = false;
                        // Since user is viewing this chat (it's the active chat), 
                        // we should clear unread regardless of scroll position
                        shouldClearUnread = true;
                    }
                }

                // If there are new messages and user was at bottom, auto-scroll
                // BUT only if we haven't just restored scroll position (to preserve user's viewing position)
                if (newMsgs.length > 0 && wasAtBottom && !scrollPositionRestoredRef.current) {
                    // Use requestAnimationFrame for better performance and timing
                    requestAnimationFrame(() => {
                        scrollToBottom(false); // Use instant scroll first
                        
                        // Then follow up with smooth scroll attempts
                        const scrollDelays = [50, 150, 300];
                        scrollDelays.forEach(delay => {
                            setTimeout(() => {
                                const stillAtBottom = isAtBottom();
                                if (wasAtBottom || stillAtBottom) {
                                    scrollToBottom(true);
                                }
                            }, delay);
                        });
                    });
                } else if (scrollPositionRestoredRef.current && newMsgs.length > 0) {
                    // If we just restored scroll position, reset the flag after processing new messages
                    // This allows future new messages to trigger auto-scroll if user scrolls to bottom
                    setTimeout(() => {
                        scrollPositionRestoredRef.current = false;
                    }, 1000);
                }
                
                return merged;
            });

            if (shouldClearUnread) {
                clearUnread(chatId);
            }
        }
    }, [allMessages, chatId, scrollToBottom, isAtBottom, clearUnread, currentUserId]);

    // Memoized message renderer to prevent unnecessary re-renders
    const MessageRenderer = React.memo<{ message: any }>(({ message }) => {
        const content = message?.content || '';
        // 只Process content Field，不再Parse附件标记
        let parsedContent = content;
        if (typeof content === 'string' && (content.startsWith('{') || content.startsWith('['))) {
            try {
                parsedContent = JSON.parse(content);
            } catch (e) {
                // ParseFailed，按普通文本Process
            }
        }
        return (
            <LazyVisible>
                <div>
                    <ContentTypeRenderer 
                        content={parsedContent} 
                        chatId={message?.chatId}
                        messageId={message?.id}
                        onFormSubmit={(
                            formId: string, 
                            values: any, 
                            chatId?: string, 
                            messageId?: string, 
                            processedForm?: any) => handleFormSubmit(
                                formId, 
                                values, 
                                chatId || '', 
                                messageId || '', 
                                processedForm)}
                        onCardAction={handleCardAction}
                    />
                    <AttachmentList attachments={message.attachments} />
                </div>
            </LazyVisible>
        );
    }, (prevProps, nextProps) => {
        // Custom comparison to prevent re-render if message content hasn't changed
        const prevMsg = prevProps.message;
        const nextMsg = nextProps.message;
        return (
            prevMsg?.id === nextMsg?.id &&
            prevMsg?.content === nextMsg?.content &&
            prevMsg?.status === nextMsg?.status &&
            JSON.stringify(prevMsg?.attachments) === JSON.stringify(nextMsg?.attachments)
        );
    });

    // CustomRenderConfiguration
    const chatBoxRenderConfig = useMemo(() => ({
        renderChatBoxContent: (props: any) => {
            const { message } = props;
            return <MessageRenderer message={message} />;
        }
    }), []);

    // 上传Component的Configuration
    const uploadProps = getUploadProps();

    // 在ComponentMount和Update时尝试聚焦Input框
    useEffect(() => {
        // Delay聚焦，确保Component已经完全Render
        const timer = setTimeout(focusInputArea, 200);
        return () => clearTimeout(timer);
    }, [chatId, focusInputArea]); // When聊天ID变化时重新聚焦
    
    // ComponentUnmount时CleanupAll定时器
    useEffect(() => {
        return () => {
            clearAllTimers();
        };
    }, [clearAllTimers]);

    // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
    useEffectOnActive(
        () => {
            // ComponentActive时：RestoreScrollPosition
            const chatBox = chatBoxRef.current;
            if (chatBox && savedScrollPositionRef.current > 0) {
                // 使用 requestAnimationFrame 确保 DOM 已经Render
                requestAnimationFrame(() => {
                    chatBox.scrollTop = savedScrollPositionRef.current;
                    // console.log('[ChatDetail] Restored scroll position:', savedScrollPositionRef.current);
                });
            }
            
            // 返回CleanupFunction，在Component失活前SaveScrollPosition
            return () => {
                const chatBox = chatBoxRef.current;
                if (chatBox) {
                    savedScrollPositionRef.current = chatBox.scrollTop;
                    // console.log('[ChatDetail] Saved scroll position:', savedScrollPositionRef.current);
                }
            };
        },
        []
    );

    return (
        <ChatDetailWrapper ref={wrapperRef}>
            {loadingMore && <div style={{textAlign: 'center'}}>{t('common.loading')}</div>}
            {!hasMore && <div style={{textAlign: 'center'}}>{t('pages.chat.noMore') || ''}</div>}

            <SemiChat
                key={chatKey}
                chats={enhancedMessages}
                style={{ ...commonOuterStyle }}
                align="leftRight"
                mode="bubble"
                placeholder={t('pages.chat.typeMessage')}
                onMessageSend={handleMessageSend}
                onMessageDelete={handleMessageDelete}
                roleConfig={roleConfig}
                uploadProps={uploadProps}
                title={chatTitle}
                showAvatar={true}
                showTime={true}
                showStatus={true}
                maxLength={5000}
                chatBoxRenderConfig={chatBoxRenderConfig}
            />
        </ChatDetailWrapper>
    );
};

export default ChatDetail; 