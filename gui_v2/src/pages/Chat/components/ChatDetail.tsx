import React, { useRef, useEffect, useMemo, useState, useCallback } from 'react';
import { Chat as SemiChat } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { Chat } from '../types/chat';
import { defaultRoleConfig } from '../types/chat';
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
import { chatStateManager } from '../managers/ChatStateManager';

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
  // 按 createAt 升序（老消息在前，新消息在后）
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
    
    // 获取当前用户信息
    const username = useUserStore(state => state.username) || 'default_user';
    const getMyTwinAgent = useAgentStore(state => state.getMyTwinAgent);
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
    
    // 加载更多消息
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
            reverse: true  // 获取更早的消息（倒序）
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

    // Save scroll position to state manager
    const saveScrollPosition = useCallback(() => {
        if (!chatId || !username) return;
        
        const chatBox = chatBoxRef.current;
        if (!chatBox) return;
        
        const scrollTop = chatBox.scrollTop;
        const scrollHeight = chatBox.scrollHeight;
        
        // 🚫 Skip saving if scrollHeight is 0 (DOM is being destroyed or not ready)
        if (scrollHeight === 0) {
            return;
        }
        
        // Use username (real user ID) instead of currentUserId (agent ID) to match Chat page
        chatStateManager.saveScrollPosition(
            username,
            chatId,
            scrollTop,
            scrollHeight
        );
    }, [chatId, username]);
    
    // Handle scroll position detection
    const handleScroll = useCallback((e: Event) => {
        const target = e.target as HTMLElement;
        
        // Update scroll position tracking
        const nowAtBottom = isAtBottom();
        shouldAutoScrollRef.current = nowAtBottom;
        
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
    }, [isAtBottom, handleLoadMore, saveScrollPosition]);
    
    // 懒加载可见内容：仅在可见时渲染消息内容，减少首屏渲染压力
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

    // 初始化协议处理器
    useEffect(() => {
        protocolHandler.init();
    }, []);

    // 根据 chatId 获取对应的聊天数据
    const currentChat = useMemo(() => {
        if (!chatId || !chats.length) return null;
        return chats.find(chat => chat.id === chatId);
    }, [chatId, chats]);


    // 处理消息，确保content是字符串
    const messages = useMemo<any[]>(() => {
        // 如果有当前聊天，使用其消息
        if (currentChat && Array.isArray(currentChat.messages)) {
            return currentChat.messages;
        }
        // 否则返回空数组
        return [];
    }, [currentChat]);

    // 聚焦输入框的函数
    const focusInputArea = useCallback(() => {
        try {
            // 尝试多种选择器找到输入框
            let inputArea: HTMLTextAreaElement | null = null;
            
            // 尝试不同的选择器找到输入框
            inputArea = document.querySelector('.semi-chat-inputbox textarea') as HTMLTextAreaElement;
            if (!inputArea) {
                inputArea = document.querySelector('.semi-input-textarea') as HTMLTextAreaElement;
            }
            if (!inputArea) {
                inputArea = document.querySelector('textarea[placeholder]') as HTMLTextAreaElement;
            }
            
            if (inputArea) {
                inputArea.focus();
                
                // 尝试将光标移动到文本末尾
                if (typeof inputArea.selectionStart === 'number') {
                    try {
                        const length = inputArea.value.length;
                        inputArea.selectionStart = length;
                        inputArea.selectionEnd = length;
                    } catch (e) {
                        // 忽略错误
                    }
                }
            }
        } catch (error) {
            // 忽略错误
        }
    }, []);

    // 检测消息列表变化，如果有新消息，尝试聚焦输入框
    useEffect(() => {
        if (messages.length > lastMessageLengthRef.current) {
            // 消息列表增加了，可能是发送了新消息
            setTimeout(focusInputArea, 100);
        }
        lastMessageLengthRef.current = messages.length;
    }, [messages.length, focusInputArea]);

    // 自定义消息发送处理函数
    const handleMessageSend = useCallback((content: string, attachments: any[]) => {
        justSentMessageRef.current = true;
        // When user sends a message, they should auto-scroll to see their message and responses
        shouldAutoScrollRef.current = true;
        isAtBottomRef.current = true;
        
        // 构造新消息对象
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
        
        // 使用多次尝试确保聚焦成功
        const attempts = [100, 200, 300, 500, 1000];
        focusTimersRef.current = attempts.map(delay => 
            setTimeout(() => {
                if (justSentMessageRef.current) {
                    focusInputArea();
                }
            }, delay)
        );
        
        // 最后一次尝试后重置标志
        const resetTimer = setTimeout(() => {
            justSentMessageRef.current = false;
        }, Math.max(...attempts) + 100);
        focusTimersRef.current.push(resetTimer);
    }, [chatId, onSend, focusInputArea, scrollToBottom, clearAllTimers]);

    // 添加事件监听，防止输入框失去焦点
    // 优化：在 useEffect 内部定义处理函数，避免闭包陷阱
    useEffect(() => {
        const chatContainer = wrapperRef.current?.querySelector('.semi-chat-container');
        if (!chatContainer) return;
        
        // 在 useEffect 内部定义处理函数，避免闭包问题
        const preventFocusLoss = () => {
            if (justSentMessageRef.current) {
                // 直接访问 DOM 元素聚焦，避免依赖外部函数
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
    }, []); // 移除依赖，避免重复创建监听器

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

    // 为 Semi UI Chat 生成稳定的 key
    // Use a hash of chatTitle to avoid special characters in key
    const chatKey = useMemo(() => {
        // Create a simple hash from chatTitle to ensure key changes when title changes
        const titleHash = chatTitle.split('').reduce((acc, char) => {
            return ((acc << 5) - acc) + char.charCodeAt(0);
        }, 0);
        return `chat_${chatId}_${titleHash}`;
    }, [chatId, chatTitle]);

    // 处理表单提交
    const handleFormSubmit = useCallback(async (formId: string, values: any, chatId: string, messageId: string, processedForm: any) => {
        const response = await get_ipc_api().chatApi.chatFormSubmit(chatId, messageId, formId, processedForm)
        if (response.success) {
            Toast.success(t('pages.chat.formSubmitSuccess'));
        } else {
            Toast.error(t('pages.chat.formSubmitFail'));
        }
    }, [t]);

    // 处理卡片动作
    const handleCardAction = useCallback((action: string) => {
        if (onSend) {
            // 创建卡片动作消息
            const actionContent = JSON.stringify({
                type: 'card_action',
                action
            });
            onSend(actionContent, []);
        }
    }, [onSend]);

    // 删除消息处理函数
    const handleMessageDelete = useCallback(async (message?: any) => {
        const messageId = message?.id;
        const chatId: string = message?.chatId ?? '';
        if (!messageId || !chatId) return;
        if (onMessageDelete) {
            onMessageDelete(messageId);
            return;
        }
        // 默认行为：调用 ipc_api 删除消息
        const response = await get_ipc_api().chatApi.deleteMessage(chatId, messageId);
        if (response.success) {
            Toast.success(t('pages.chat.deleteMessageSuccess'));
            // 本地移除消息
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

    // 监听消息区滚动事件
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

    // 恢复滚动位置
    const restoreScrollPosition = useCallback(() => {
        if (!chatId || !username) return;
        
        // Use username (real user ID) instead of currentUserId (agent ID) to match Chat page
        const savedScrollState = chatStateManager.getScrollPosition(username, chatId);
        if (!savedScrollState) {
            return;
        }
        
        const chatBox = chatBoxRef.current;
        if (!chatBox) {
            return;
        }
        
        // 等待内容渲染完成后恢复滚动位置
        // 使用多次 requestAnimationFrame 确保 DOM 完全渲染
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    // 如果内容高度发生变化，按比例恢复滚动位置
                    const currentScrollHeight = chatBox.scrollHeight;
                    const savedScrollHeight = savedScrollState.scrollHeight;
                    
                    let targetScrollTop = savedScrollState.scrollTop;
                    
                    // 如果滚动高度变化了，按比例调整滚动位置
                    if (savedScrollHeight > 0 && currentScrollHeight !== savedScrollHeight) {
                        const scrollRatio = savedScrollState.scrollTop / savedScrollHeight;
                        targetScrollTop = scrollRatio * currentScrollHeight;
                    }
                    
                    chatBox.scrollTop = targetScrollTop;
                    scrollPositionRestoredRef.current = true;
                    
                    // 更新 auto-scroll 相关状态
                    shouldAutoScrollRef.current = false; // 禁用自动滚动，保持用户位置
                    isAtBottomRef.current = false; // 用户不在底部
                });
            });
        });
    }, [chatId, username]);
    
    // 初始化加载第一页
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
        
        // Load initial messages when chatId changes
        if (chatId) {
            const loadInitialMessages = async () => {
                try {
                    const res = await get_ipc_api().chatApi.getChatMessages({
                        chatId,
                        limit: PAGE_SIZE,
                        offset: 0,
                        reverse: true  // 获取最新的消息（倒序）
                    });
                    
                    let initialMsgs: any[] = [];
                    if (res.success && res.data && typeof res.data === 'object' && Array.isArray((res.data as any).data)) {
                        initialMsgs = (res.data as any).data;
                    }
                    
                    // 使用 mergeAndSortMessages 确保消息按时间升序排列（老消息在前，新消息在后）
                    setPageMessages(mergeAndSortMessages(initialMsgs));
                    setOffset(initialMsgs.length);
                    setHasMore(initialMsgs.length === PAGE_SIZE);
                    
                    // 标记未读消息为已读
                    if (initialMsgs.length > 0 && currentUserId) {
                        // 只提取未读消息的 ID
                        const unreadMessageIds = initialMsgs
                            .filter(msg => msg.isRead === false)
                            .map(msg => msg.id)
                            .filter(Boolean);
                        
                        if (unreadMessageIds.length > 0) {
                            get_ipc_api().chatApi.markMessageAsRead(unreadMessageIds, currentUserId)
                                .then((response: any) => {
                                    // 后端返回实际更新的消息数量
                                    if (response.success && response.data) {
                                        const actualUpdatedCount = response.data.updated_ids?.length || unreadMessageIds.length;
                                        
                                        // 通知父组件更新 unread 计数
                                        if (onMessagesRead) {
                                            onMessagesRead(chatId, actualUpdatedCount);
                                        }
                                    }
                                })
                                .catch(err => {
                                    console.error('Failed to mark messages as read:', err);
                                });
                        }
                    }
                    
                    // 尝试恢复滚动位置，如果没有保存的位置则滚动到底部
                    // 增加延迟确保消息和 DOM 完全渲染
                    setTimeout(() => {
                        // Use username (real user ID) to match Chat page
                        const savedScrollState = chatStateManager.getScrollPosition(username, chatId);
                        
                        if (savedScrollState && savedScrollState.scrollTop > 0) {
                            // 有保存的滚动位置，恢复它
                            restoreScrollPosition();
                        } else {
                            // 没有保存的位置，滚动到底部（新聊天或首次打开）
                            shouldAutoScrollRef.current = true;
                            isAtBottomRef.current = true;
                            scrollToBottom(false);
                        }
                    }, 300); // 增加延迟从 200ms 到 300ms
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
    }, [chatId, scrollToBottom, restoreScrollPosition, saveScrollPosition, username]);

    // Sync allMessages from useMessages hook to pageMessages for display
    useEffect(() => {
        if (!chatId) return;
        
        const globalMsgs = allMessages.get(chatId) || [];
        if (globalMsgs.length > 0) {
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
        }
    }, [allMessages, chatId, scrollToBottom, isAtBottom]);

    // Memoized message renderer to prevent unnecessary re-renders
    const MessageRenderer = React.memo<{ message: any }>(({ message }) => {
        const content = message?.content || '';
        // 只处理 content 字段，不再解析附件标记
        let parsedContent = content;
        if (typeof content === 'string' && (content.startsWith('{') || content.startsWith('['))) {
            try {
                parsedContent = JSON.parse(content);
            } catch (e) {
                // 解析失败，按普通文本处理
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

    // 自定义渲染配置
    const chatBoxRenderConfig = useMemo(() => ({
        renderChatBoxContent: (props: any) => {
            const { message } = props;
            return <MessageRenderer message={message} />;
        }
    }), []);

    // 上传组件的配置
    const uploadProps = getUploadProps();

    // 在组件挂载和更新时尝试聚焦输入框
    useEffect(() => {
        // 延迟聚焦，确保组件已经完全渲染
        const timer = setTimeout(focusInputArea, 200);
        return () => clearTimeout(timer);
    }, [chatId, focusInputArea]); // 当聊天ID变化时重新聚焦
    
    // 组件卸载时清理所有定时器
    useEffect(() => {
        return () => {
            clearAllTimers();
        };
    }, [clearAllTimers]);

    return (
        <ChatDetailWrapper ref={wrapperRef}>
            {loadingMore && <div style={{textAlign: 'center'}}>{t('common.loading')}</div>}
            {!hasMore && <div style={{textAlign: 'center'}}>{t('pages.chat.noMore') || ''}</div>}

            <SemiChat
                key={chatKey}
                chats={pageMessages}
                style={{ ...commonOuterStyle }}
                align="leftRight"
                mode="bubble"
                placeholder={t('pages.chat.typeMessage')}
                onMessageSend={handleMessageSend}
                onMessageDelete={handleMessageDelete}
                roleConfig={defaultRoleConfig}
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