import React, { useState, useEffect, useRef, useCallback, useMemo, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ChatList from './components/ChatList';
const ChatDetail = lazy(() => import('./components/ChatDetail'));
import { Chat, Message, Attachment } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
const ChatNotification = lazy(() => import('./components/ChatNotification'));
import AgentFilterModal from './components/AgentFilterModal';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useAppDataStore } from '@/stores/appDataStore';
import { useAgentStore } from '@/stores/agentStore';
import { useChatNotifications, NOTIF_PAGE_SIZE } from './hooks/useChatNotifications';
import { useMessages } from './hooks/useMessages';
import { notificationManager } from './managers/NotificationManager';
import { getDisplayMsg } from './utils/displayMsg';
import { iTagManager } from './managers/ITagManager';
import { chatStateManager } from './managers/ChatStateManager';

// 工具函数：尝试将字符串解析为对象
function parseMaybeJson(str: any): any {
    if (typeof str === 'string') {
        try {
            const obj = JSON.parse(str);
            if (typeof obj === 'object' && obj !== null) return obj;
        } catch {}
    }
    return str;
}

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentIdFromUrl = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    const agents = useAgentStore(state => state.agents);
    const getMyTwinAgent = useAgentStore(state => state.getMyTwinAgent);
    
    // 直接从 store 获取 myTwinAgent，确保始终是最新的
    const myTwinAgent = getMyTwinAgent();
    const myTwinAgentId = myTwinAgent?.card?.id;
    
    const initialized = useAppDataStore(state => state.initialized);
    
    // Compute effective agentId: URL > ChatStateManager > myTwinAgentId
    const effectiveAgentId = useMemo(() => {
        if (agentIdFromUrl) {
            // Save to ChatStateManager for next time
            if (username) {
                chatStateManager.saveAgentId(username, agentIdFromUrl);
            }
            return agentIdFromUrl;
        }
        
        // Try to restore from ChatStateManager
        if (username) {
            const savedAgentId = chatStateManager.getAgentId(username);
            if (savedAgentId) {
                return savedAgentId;
            }
        }
        
        // Default to myTwinAgentId
        if (myTwinAgentId && username) {
            chatStateManager.saveAgentId(username, myTwinAgentId);
            return myTwinAgentId;
        }
        
        return null;
    }, [agentIdFromUrl, myTwinAgentId, username]);
    
    // Use effectiveAgentId instead of agentIdFromUrl
    const agentId = effectiveAgentId;
    
    // Initialize lastFetchedAgentId on mount to prevent unnecessary fetch
    const isFirstMount = useRef(true);
    useEffect(() => {
        if (isFirstMount.current && agentId) {
            // On first mount, initialize lastFetchedAgentId to current agentId
            // This prevents the agentId change detection from triggering on mount
            lastFetchedAgentId.current = agentId;
            isFirstMount.current = false;
        }
    }, [agentId]);

    const [chats, setChats] = useState<Chat[]>([]);
    const [activeChatId, setActiveChatId] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hasFetched, setHasFetched] = useState(false);
    const [isInitialLoading, setIsInitialLoading] = useState(false);
    
    // 引用型状态，用于跟踪和控制
    const lastFetchedAgentId = useRef<string | undefined>();
    const prevInitialized = useRef(initialized);
    const fetchOnceRef = useRef(false);
    const lastSelectedChatIdRef = useRef<string | null>(null);
    const isFetchingRef = useRef(false);
    const isCreatingChatRef = useRef(false);
    const effectsCompletedRef = useRef(false);
    const allChatsCache = useRef<Chat[]>([]); // Cache all chats (when no search)
    const cachedUserId = useRef<string | undefined>(); // Track which userId the cache is for
    const hasAutoSelectedRef = useRef(false); // Track if we've auto-selected for current filter
    const lastAutoSelectAgentId = useRef<string | undefined>(); // Track agentId when last auto-selected
    const handleChatSelectRef = useRef<((chatId: string) => Promise<void>) | null>(null); // Ref to handleChatSelect
    
    // 每次渲染都更新 ref，确保它始终指向最新的 handleChatSelect
    handleChatSelectRef.current = null; // Will be set later after handleChatSelect is defined

    // 使用全局通知管理器和消息管理器
    const { hasNew, markAsRead } = useChatNotifications(activeChatId || '');
    const { allMessages, unreadCounts, markAsRead: markMessageAsRead, updateMessages, addMessageToChat, updateMessage } = useMessages();

    // 新增独立的 loading 状态
    const [isInitialLoadingNotifications, setIsInitialLoadingNotifications] = useState(false);
    
    // 过滤器和搜索状态
    const [searchText, setSearchText] = useState('');
    const searchTextRef = useRef(''); // 保存最新的搜索文本
    const [showFilterModal, setShowFilterModal] = useState(false);

    // 组件挂载时初始化并确保 agents 已加载
    useEffect(() => {
        const initializeComponent = async () => {
            const agentStore = useAgentStore.getState();
            if (agentStore.agents.length === 0 && username) {
                await agentStore.fetchAgents(username);
            }
            
            // 注意：滚动状态由 KeepAlive 自动管理，不需要手动清理
            
            // agents 加载完成后，设置标志（移除 setTimeout，直接设置）
            effectsCompletedRef.current = true;
        };
        
        initializeComponent();
        
        return () => {
            effectsCompletedRef.current = false;
            isFetchingRef.current = false;
            isCreatingChatRef.current = false;
        };
    }, [username]);
    
    // 统一的数据获取 effect - 合并 myTwinAgentId、initialized 和 agentId 的监听
    useEffect(() => {
        // 检查是否需要获取数据
        const shouldFetch = (
            myTwinAgentId && // 必须有 myTwinAgentId
            !isFetchingRef.current && // 不在获取中
            (
                !fetchOnceRef.current || // 首次获取
                (initialized && !hasFetched) || // initialized 变化
                agentId !== lastFetchedAgentId.current // agentId 变化
            )
        );
        
        if (shouldFetch) {
            // 更新标志
            if (!fetchOnceRef.current) {
                fetchOnceRef.current = true;
            }
            if (initialized && !hasFetched) {
                setHasFetched(true);
            }
            if (agentId !== lastFetchedAgentId.current) {
                lastFetchedAgentId.current = agentId || undefined;
            }
            
            // 直接调用 fetchChats（移除 setTimeout）
            fetchChats();
        }
        
        // 更新 prevInitialized
        prevInitialized.current = initialized;
    }, [myTwinAgentId, initialized, hasFetched, agentId]);

    // 追踪上一次的消息和未读数，避免不必要的更新
    const prevMessagesRef = useRef<Map<string, Message[]>>(new Map());
    const prevUnreadRef = useRef<Map<string, number>>(new Map());

    // 同步消息管理器中的消息到聊天列表（优化版本：只在真正变化时更新）
    useEffect(() => {
        // 检查是否有真正的变化
        let hasChanges = false;
        
        for (const chat of chats) {
            const currentMessages = allMessages.get(chat.id) || [];
            const prevMessages = prevMessagesRef.current.get(chat.id) || [];
            const currentUnread = unreadCounts.get(chat.id) || 0;
            const prevUnread = prevUnreadRef.current.get(chat.id) || 0;
            
            // 比较消息数量和未读数
            if (currentMessages.length !== prevMessages.length || currentUnread !== prevUnread) {
                hasChanges = true;
                break;
            }
            
            // 如果数量相同，检查最后一条消息是否变化
            if (currentMessages.length > 0 && prevMessages.length > 0) {
                const lastCurrent = currentMessages[currentMessages.length - 1];
                const lastPrev = prevMessages[prevMessages.length - 1];
                if (lastCurrent.id !== lastPrev.id || lastCurrent.status !== lastPrev.status) {
                    hasChanges = true;
                    break;
                }
            }
        }
        
        // 只在有变化时才更新
        if (!hasChanges) {
            return;
        }
        
        // 更新引用
        prevMessagesRef.current = new Map(allMessages);
        prevUnreadRef.current = new Map(unreadCounts);
        
        // 更新 chats
        setChats(prevChats => {
            return prevChats.map(chat => {
                const messages = allMessages.get(chat.id) || [];
                const unreadCount = unreadCounts.get(chat.id) || 0;

                // 乐观刷新：取已发送成功或发送中的消息
                const validMessages = messages.filter(m => m.status === 'complete' || m.status === 'sending');
                let lastMsg = chat.lastMsg;
                let lastMsgTime = chat.lastMsgTime;
                if (validMessages.length > 0) {
                    const lastMessage = validMessages[validMessages.length - 1];
                    lastMsg = getDisplayMsg(lastMessage.content, t);
                    lastMsgTime = lastMessage.createAt;
                } else if (lastMsg && typeof lastMsg === 'object' && lastMsg !== null) {
                    lastMsg = getDisplayMsg(lastMsg, t);
                }

                return {
                    ...chat,
                    messages,
                    unread: unreadCount,
                    lastMsg: getDisplayMsg(parseMaybeJson(lastMsg), t),
                    lastMsgTime,
                };
            });
        });
    }, [allMessages, unreadCounts, chats, t]);

    // 抽取获取聊天的函数，可以在多个地方调用
    const fetchChats = async () => {
        // 如果已经在获取中，跳过
        if (isFetchingRef.current) {
            return;
        }
        
        // 设置加载状态和锁
        setIsLoading(true);
        isFetchingRef.current = true;
        
        try {
            // Determine which userId to query:
            // 1. If agentId is provided (filter selected), use that agentId
            // 2. Otherwise use myTwinAgentId (default: show MyTwin's chats)
            const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
            const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
            const targetUserId = agentId || currentMyTwinAgentId;
            
            if (!targetUserId) {
                logger.error("[fetchChats] No userId available (agentId or myTwinAgentId)");
                return;
            }
            
            // 使用 ref 获取最新的搜索文本
            const currentSearchText = searchTextRef.current;
            
            // Only use cache if: no search text, cache exists, AND cache is for the same userId
            if ((!currentSearchText || currentSearchText.trim() === '') && 
                allChatsCache.current.length > 0 && 
                cachedUserId.current === targetUserId) {
                setChats(prevChats => {
                    // 如果缓存和当前数据相同，不更新（避免重新渲染）
                    if (prevChats === allChatsCache.current) {
                        return prevChats;
                    }
                    return allChatsCache.current;
                });
                return;
            }
            
            // If userId changed, clear cache
            if (cachedUserId.current !== targetUserId) {
                allChatsCache.current = [];
                cachedUserId.current = targetUserId;
            }
            
            // 根据是否有搜索文本选择不同的 API
            if (currentSearchText && currentSearchText.trim()) {
                // 使用搜索 API
                const response = await get_ipc_api().chatApi.searchChats(
                    targetUserId,
                    currentSearchText,
                    false
                );
                
                if (response.success && response.data) {
                    let chatData: Chat[] = Array.isArray((response.data as any).data)
                        ? (response.data as any).data
                        : Array.isArray(response.data)
                            ? response.data as Chat[]
                            : [];
                    
                    // 解析并格式化 lastMsg 字段
                    chatData = chatData.map(chat => {
                        let parsedMsg = chat.lastMsg;
                        
                        // 如果是字符串，先解析
                        if (typeof parsedMsg === 'string') {
                            try {
                                parsedMsg = JSON.parse(parsedMsg);
                            } catch (e) {
                                logger.warn(`[fetchChats] Failed to parse lastMsg for chat ${chat.id}`);
                            }
                        }
                        
                        // 使用 getDisplayMsg 格式化显示
                        return {
                            ...chat,
                            lastMsg: getDisplayMsg(parsedMsg, t),
                        };
                    });
                    
                    // 智能更新：保持现有聊天的引用，只更新变化的部分
                    setChats(prevChats => {
                        // 如果数据相同，不更新（避免闪烁）
                        if (prevChats.length === chatData.length && 
                            prevChats.every((chat, i) => chat.id === chatData[i]?.id)) {
                            return prevChats;
                        }
                        // 如果搜索结果为空且之前有数据，也保持引用（避免闪烁）
                        if (chatData.length === 0 && prevChats.length > 0) {
                            return prevChats;
                        }
                        return chatData;
                    });
                } else {
                    logger.error('[fetchChats] Failed to search chats:', response.error);
                    setChats([]);
                }
            } else {
                // 使用普通查询 API
                await getChatsAndSetState(targetUserId);
            }
        } catch (error) {
            logger.error("Error in fetchChats:", error);
        } finally {
            // 重置加载状态和锁
            setIsLoading(false);
            isFetchingRef.current = false;
        }
    };
    
    // 处理agentId变化的函数
    const handleAgentIdChange = async (targetAgentId: string) => {
        if (!targetAgentId) return;
        
        
        // 查找是否存在包含该agentId的聊天
        const chatWithAgent = chats.find(chat => 
            chat.members?.some(member => member.userId === targetAgentId)
        );
        
        if (chatWithAgent) {
            // 如果找到，设置为活动聊天并获取消息
            // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
            setActiveChatIdAndFetchMessages(chatWithAgent.id);
        } else {
            // 如果没找到，创建新的聊天
            await createChatWithAgent(targetAgentId);
        }
    };

    // 通用获取聊天数据的函数，使用新的 API，并在获取数据后处理agentId相关逻辑
    const getChatsAndSetState = async (userId?: string) => {
        if (!userId) {
            logger.error("[getChatsAndSetState] Missing userId");
            return;
        }
        
        try {
            // 使用新的 API 获取聊天数据
            const response = await get_ipc_api().chatApi.getChats(
                userId,
                false // deep 参数，按需可调整
            );
            if (response.success && response.data) {
                let chatData: Chat[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Chat[]
                        : [];
                if (!Array.isArray(chatData)) {
                    if (chatData && typeof chatData === 'object') {
                        chatData = Object.values(chatData) as Chat[];
                    } else {
                        chatData = [];
                    }
                }
                
                // 这里直接对 lastMsg 做 display 解析
                const processedChats = chatData.map(chat => ({
                    ...chat,
                    lastMsg: getDisplayMsg(chat.lastMsg, t),
                }));
                
                // 更新缓存
                allChatsCache.current = processedChats;
                
                setChats(processedChats);
                
                // 处理agentId相关逻辑
                if (agentId) {
                    // Get the latest myTwinAgentId
                    const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
                    const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
                    
                    // 1. 查找是否存在包含该agentId的聊天
                    const chatWithAgent = chatData.find(chat => 
                        chat.members?.some(member => member.userId === agentId)
                    );
                    
                    if (chatWithAgent) {
                        // 2A. 如果找到，设置为活动聊天
                        // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                        setActiveChatIdAndFetchMessages(chatWithAgent.id);
                    } else if (agentId === currentMyTwinAgentId) {
                        // 2B. 如果 agentId 是 MyTwinAgent，不要创建聊天（会被过滤掉）
                        // 而是选择第一个可用的聊天（但要排除 My Twin Agent 自己的聊天）
                        if (chatData.length > 0) {
                            // 应用过滤逻辑，找到第一个不是 "My Twin Agent" 的聊天
                            const firstValidChat = chatData.find(chat => {
                                // 过滤掉名为 "My Twin Agent" 的聊天
                                if (chat.name === 'My Twin Agent') {
                                    return false;
                                }
                                
                                // 过滤掉只有 My Twin Agent 的聊天
                                if (chat.members && chat.members.length > 0) {
                                    const nonMyTwinMembers = chat.members.filter(m => m.userId !== currentMyTwinAgentId);
                                    if (nonMyTwinMembers.length === 0) {
                                        return false;
                                    }
                                }
                                
                                // 过滤掉 agent_id 等于 myTwinAgentId 的聊天
                                if ((chat as any).agent_id === currentMyTwinAgentId) {
                                    return false;
                                }
                                
                                return true;
                            });
                            
                            if (firstValidChat) {
                                setActiveChatIdAndFetchMessages(firstValidChat.id);
                            } else {
                                logger.warn(`[getChatsAndSetState] No valid chat found after filtering`);
                            }
                        }
                    } else {
                        // 2C. 如果没找到，且不是 MyTwinAgent，创建新的聊天
                        // 检查是否已经在创建聊天中
                        if (!isCreatingChatRef.current) {
                            await createChatWithAgent(agentId);
                        }
                    }
                } else if (chatData.length > 0) {
                    // 如果没有agentId，但有聊天列表，选择第一个聊天
                    const selectedChatId = chatData[0].id;
                    // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                    setActiveChatIdAndFetchMessages(selectedChatId);
                }
            } else {
                logger.error('Failed to load chats:', response.error);
                setError(response.error?.message || 'Failed to load chats');
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error loading chats:', errorMessage);
            setError(`Error loading chats: ${errorMessage}`);
        }
    };
    
    // 创建和Agent的聊天的辅助函数
    const createChatWithAgent = async (targetAgentId: string) => {
        // Get the latest myTwinAgentId from store
        const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
        const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
        
        if (!currentMyTwinAgentId) {
            logger.error("[createChatWithAgent] Missing myTwinAgentId");
            return;
        }
        
        // 检查是否是和自己聊天（targetAgentId === currentMyTwinAgentId）
        const isSelfChat = targetAgentId === currentMyTwinAgentId;
        
        // 🚫 阻止创建只包含 My Twin Agent 的聊天（会被过滤掉）
        if (isSelfChat) {
            logger.warn("[createChatWithAgent] Preventing creation of self-chat with My Twin Agent (would be filtered)");
            return;
        }
        
        // 如果已经在创建聊天中，跳过
        if (isCreatingChatRef.current) {
            return;
        }
        
        // 设置创建聊天锁
        isCreatingChatRef.current = true;
        
        try {
            const my_twin_agent = useAgentStore.getState().getAgentById(currentMyTwinAgentId);
            const receiver_agent = useAgentStore.getState().getAgentById(targetAgentId);
            
            // 创建聊天数据（isSelfChat 已经在前面被阻止了，这里不会执行）
            const chatData = {
                members: [
                    {"userId": currentMyTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"},
                    {"userId": targetAgentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                ],
                name: receiver_agent?.card.name || `Chat with ${targetAgentId}`,
                type: 'user-agent',
                agent_id: targetAgentId,  // ✅ 添加 agent_id
            };
            
            const response = await get_ipc_api().chatApi.createChat(chatData);
            const resp: any = response;
            
            // Check if IPC call succeeded
            if (resp.success && resp.data) {
                // Check if backend operation succeeded (new chat created)
                if (resp.data.success && resp.data.data) {
                    // 提取新聊天数据
                    const newChat = { ...resp.data.data, name: resp.data.data.name || chatData.name } as Chat;
                    
                    // 更新聊天列表
                    setChats(prevChats => {
                        const exists = prevChats.some(c => c.id === newChat.id);
                        return exists
                            ? prevChats.map(c => c.id === newChat.id ? { ...c, ...newChat } : c)
                            : [...prevChats, newChat];
                    });
                    
                    // 设置为活动聊天并获取消息
                    setActiveChatIdAndFetchMessages(newChat.id);
                } else if (!resp.data.success && resp.data.data) {
                    // Chat already exists - backend returns existing chat data when duplicate detected
                    const existingChat = { ...resp.data.data, name: resp.data.data.name || chatData.name } as Chat;
                    
                    // Add to chat list if not already there, or update if it exists
                    setChats(prevChats => {
                        const exists = prevChats.some(c => c.id === existingChat.id);
                        return exists 
                            ? prevChats.map(c => c.id === existingChat.id ? existingChat : c)
                            : [...prevChats, existingChat];
                    });
                    
                    // Set as active chat and load messages
                    setActiveChatIdAndFetchMessages(existingChat.id);
                } else {
                    logger.error('[createChatWithAgent] Backend operation failed:', resp.data.error);
                }
            } else {
                logger.error('[createChatWithAgent] IPC call failed:', resp.error);
            }
        } catch (error) {
            logger.error('[createChatWithAgent] Error creating chat:', error);
        } finally {
            // 重置创建聊天锁
            isCreatingChatRef.current = false;
        }
    };

    // 页面初始化
    useEffect(() => {
        // 只要 initialized 变 true，重置 hasFetched
        if (initialized) setHasFetched(false);
    }, [initialized]);

    const handleFilterChange = useCallback(() => {
    }, []);

    // 新增：设置activeChatId并获取消息的函数，避免重复调用handleChatSelect
    const setActiveChatIdAndFetchMessages = useCallback((chatId: string) => {
        // 注意：选中的聊天ID由 KeepAlive 自动保持，不需要手动保存
        
        setActiveChatId(chatId);
        // 直接调用 handleChatSelect（移除 setTimeout，使用 ref 确保最新函数）
        if (handleChatSelectRef.current) {
            handleChatSelectRef.current(chatId);
        }
    }, [username, agentId, chats, myTwinAgentId]);

    // 设置活动聊天ID
    const setActiveChat = useCallback((chatId: string) => {
        // 如果是通过setActiveChatIdAndFetchMessages调用的，不需要再次设置activeChatId
        if (activeChatId !== chatId) {
            setActiveChatId(chatId);
        }
    }, [activeChatId]);

    // 标记消息为已读
    const markChatAsRead = useCallback((chatId: string) => {
        markMessageAsRead(chatId);
    }, [markMessageAsRead]);

    // 假设 PAGE_SIZE 已定义（如 20），否则加上 const PAGE_SIZE = 20;
    const PAGE_SIZE = 20;
    // 获取并处理聊天消息
    const fetchAndProcessChatMessages = async (chatId: string, setIsInitialLoading?: (loading: boolean) => void) => {
        try {
            const response = await get_ipc_api().chatApi.getChatMessages({
                chatId,
                limit: PAGE_SIZE,
                offset: 0,
                reverse: true  // 获取最新的消息（倒序）
            });
            console.log("[chat message] result>>>", response.data);
            
            if (response.success && response.data) {
                let messages: Message[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Message[]
                        : [];
                
                // 确保每个消息都有唯一的 ID
                messages = messages.map((message, index) => ({
                    ...message,
                    id: message.id || 'server_msg_' + Date.now() + '_' + index + '_' + Math.random().toString(36).substr(2, 9)
                }));
                
                // 使用消息管理器更新消息
                updateMessages(chatId, messages);
            } else {
                // 失败时清空消息并可选提示
                updateMessages(chatId, []);
                if (response.error) {
                    setError(typeof response.error === 'string' ? response.error : response.error.message || 'Failed to load messages');
                }
                logger.warn('Failed to load chat messages:', response.error);
            }
        } catch (err) {
            logger.error('Error fetching chat messages:', err);
            updateMessages(chatId, []);
            setError('Error fetching chat messages');
        } finally {
            if (typeof setIsInitialLoading === 'function') setIsInitialLoading(false);
        }
    };

    // 获取并处理聊天通知（仅首次加载，支持分页）
    const fetchAndProcessChatNotifications = async (chatId: string, setIsInitialLoading?: (loading: boolean) => void) => {
        try {
            if (typeof setIsInitialLoading === 'function') setIsInitialLoading(true);
            const notificationResponse = await get_ipc_api().chatApi.getChatNotifications({ 
                chatId, 
                limit: NOTIF_PAGE_SIZE, 
                offset: 0, 
                reverse: true });
            console.log("[chat notifications] result>>>", notificationResponse.data);
            
            if (notificationResponse.success && notificationResponse.data) {
                notificationManager.clear(chatId);
                const dataArray = (notificationResponse.data as any).data;
                if (Array.isArray(dataArray)) {
                    dataArray.reverse().forEach((item: any) => {
                        notificationManager.addNotification(chatId, item);
                    });
                }

            } else {
                logger.warn('Failed to load chat notifications:', notificationResponse.error);
            }
        } catch (err) {
            logger.error('Error fetching chat notifications:', err);
        } finally {
            if (typeof setIsInitialLoading === 'function') setIsInitialLoading(false);
        }
    };

    // 点击chat时的主处理函数
    const handleChatSelect = async (chatId: string) => {
        // 1. 标记为已读
        markChatAsRead(chatId);
        
        // 2. 设置活动聊天
        setActiveChat(chatId);
        
        // 3. 并行获取消息和通知（通知只拉第一页，后续分页交给 useChatNotifications）
        await Promise.all([
            fetchAndProcessChatMessages(chatId, setIsInitialLoading),
            fetchAndProcessChatNotifications(chatId, setIsInitialLoadingNotifications)
        ]);
    };
    
    // Update ref to point to the latest handleChatSelect
    handleChatSelectRef.current = handleChatSelect;

    const handleChatDelete = async (chatId: string) => {
        try {
            // 先本地更新 UI（乐观更新）
            const updatedChats = chats.filter(c => c.id !== chatId);
            setChats(updatedChats);

            // 如果删除的是当前聊天，则切换到第一个聊天
            if (activeChatId === chatId) {
                const nextChatId = updatedChats[0]?.id || null;
                if (nextChatId) {
                    setActiveChatId(nextChatId);
                    handleChatSelect(nextChatId);
                } else {
                    // 没有剩余的 chat，清除 activeChatId 和 URL 参数
                    setActiveChatId(null);
                    setSearchParams({});
                }
            }
            
            // 调用 API 删除聊天
            const response = await get_ipc_api().chatApi.deleteChat(chatId);
            
            if (!response.success) {
                // 删除失败，回滚 UI
                setChats(chats);
                logger.error('Failed to delete chat:', response.error);
                setError(`Failed to delete chat: ${response.error?.message || 'Unknown error'}`);
            }
        } catch (err) {
            // 删除失败，回滚 UI
            setChats(chats);
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error deleting chat:', errorMessage);
            setError(`Error deleting chat: ${errorMessage}`);
        }
    };

    const handleChatPin = (chatId: string) => {
        const newChats = chats.map(chat => 
            chat.id === chatId ? { ...chat, pinned: !chat.pinned } : chat
        );
        newChats.sort((a, b) => (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0));
        setChats(newChats);
    };

    const handleChatMute = (chatId: string) => {
        setChats(chats.map(chat => 
            chat.id === chatId ? { ...chat, muted: !chat.muted } : chat
        ));
    };

    // handleMessageSend 发送消息时加 log
    const handleMessageSend = useCallback(async (content: string, attachments: Attachment[]) => {
        console.log('[handleMessageSend] called, content:', content, 'attachments:', attachments);
        if (!activeChatId) {
            logger.error('No activeChatId!!!');
            return;
        }

        const chat = chats.find(c => c.id === activeChatId);
        if (!chat) return;

        if (!myTwinAgentId) return;
        const my_twin_agent = useAgentStore.getState().getAgentById(myTwinAgentId);
        const senderId = my_twin_agent?.card.id;
        const senderName = my_twin_agent?.card.name;
        if (!senderId || !senderName) return;

        // 只保留可序列化字段，优先使用 response 字段（如有）
        const safeAttachments = (attachments || []).map(att => {
            if (!att) return att;
            const attAny = att as any;
            if (attAny.response && typeof attAny.response === 'object') {
                // response 字段通常是后端返回的 attachment 信息
                const resp = attAny.response;
                return {
                    name: resp.name,
                    type: resp.type,
                    size: resp.size,
                    url: resp.url || resp.base64 || resp.data || '',
                    status: resp.status || 'complete',
                    uid: resp.uid || attAny.uid || ('' + Date.now())
                };
            }
            return {
                name: att.name,
                type: att.type,
                size: att.size,
                url: att.url,
                status: att.status,
                uid: att.uid
            };
        });

        const userMessage: Message = {
            id: `user_msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            chatId: activeChatId,
            role: "user",
            createAt: Date.now(),
            senderId,
            senderName,
            content: content, // 只做文本或结构化内容
            status: 'sending',
            attachments: safeAttachments // 标准附件数组
        };

        // 先乐观地更新 UI - 使用消息管理器
        addMessageToChat(activeChatId, userMessage);
        console.log('[handleMessageSend] after addMessageToChat, allMessages:', allMessages);

        try {
            // 使用新的 API 发送消息
            const messageData = {
                chatId: activeChatId,
                senderId, // 明确为 string
                role: "user",
                content: content,
                createAt: String(Date.now()),
                senderName,
                status: 'complete',
                i_tag: iTagManager.getLatest(activeChatId) || undefined,
                attachments: safeAttachments as any
            };
            
            const response = await get_ipc_api().chatApi.sendChat(messageData);
            if (!response.success) {
                logger.error('Failed to send message:', response.error);
                // 更新消息状态为错误
                updateMessage(activeChatId, userMessage.id, { status: 'error' as const });
                return;
            }
            
            // 更新消息状态为已发送，并使用服务器返回的消息 ID
            if (response.data && (response.data as any).id) {
                // 替换乐观更新的消息，使用服务器返回的 ID
                updateMessage(activeChatId, userMessage.id, { 
                    id: (response.data as any).id, 
                    status: 'complete' as const,
                    // 保留服务器返回的其他字段
                    ...(response.data as any)
                });
            } else {
                // 如果服务器没有返回消息 ID，则只更新状态
                updateMessage(activeChatId, userMessage.id, { status: 'complete' as const });
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error sending message:', errorMessage);
            
            // 更新消息状态为错误
            updateMessage(activeChatId, userMessage.id, { status: 'error' as const });
        }
    }, [activeChatId, chats, myTwinAgentId, addMessageToChat, allMessages, updateMessage]);
    
    const currentChat = (!activeChatId || !chats || chats.length === 0)
        ? null
        : chats.find((c) => c.id === activeChatId) || null;

    // Compute left panel header agentId: 显示当前过滤的 agent 的视频
    // 视频不跟随选中的 chat 改变，只跟随过滤器（agentId 参数）改变
    const headerAgentId = useMemo(() => {
        // 优先级：URL agentId（过滤器选择）> myTwinAgentId（默认）> fallback
        if (agentId) {
            logger.debug(`[headerAgentId] Using URL agentId (filter): ${agentId}`);
            return agentId;
        }
        
        if (myTwinAgentId) {
            logger.debug(`[headerAgentId] Using myTwinAgentId (default): ${myTwinAgentId}`);
            return myTwinAgentId;
        }
        
        // Fallback：随机选择一个系统 agent
        if (chats.length === 0) {
            const systemAgents = agents.filter(a => a.card?.id?.startsWith('system_'));
            if (systemAgents.length > 0) {
                const randomIndex = Math.floor(Math.random() * systemAgents.length);
                const fallbackId = systemAgents[randomIndex].card?.id;
                logger.debug(`[headerAgentId] Using random system agent: ${fallbackId}`);
                return fallbackId;
            }
        }
        
        // 最终 fallback
        const fallbackId = agents && agents.length > 0 ? agents[0].card?.id : undefined;
        logger.debug(`[headerAgentId] Using final fallback: ${fallbackId}`);
        return fallbackId;
    }, [agentId, myTwinAgentId, agents, chats.length]);
    
    // 搜索防抖定时器 ref
    const searchDebounceTimer = useRef<NodeJS.Timeout | null>(null);
    
    // 处理搜索
    const handleSearch = useCallback((text: string) => {
        setSearchText(text);
        searchTextRef.current = text;
        
        // 清除之前的定时器
        if (searchDebounceTimer.current) {
            clearTimeout(searchDebounceTimer.current);
            searchDebounceTimer.current = null;
        }
        
        // 如果清空搜索，立即执行（不延迟）
        if (!text || text.trim() === '') {
            if (effectsCompletedRef.current) {
                fetchChats();
            }
        } else {
            // 有搜索文本时，使用防抖定时器
            searchDebounceTimer.current = setTimeout(() => {
                if (effectsCompletedRef.current) {
                    fetchChats();
                }
                searchDebounceTimer.current = null;
            }, 300);
        }
    }, []);
    
    // 清理搜索防抖定时器
    useEffect(() => {
        return () => {
            if (searchDebounceTimer.current) {
                clearTimeout(searchDebounceTimer.current);
            }
        };
    }, []);
    
    // 处理过滤器选择
    const handleFilterSelect = useCallback((selectedAgentId: string | null) => {
        logger.info(`[Chat] Filter agent selected: ${selectedAgentId}`);
        setShowFilterModal(false);
        
        // 更新 URL 参数
        if (selectedAgentId) {
            setSearchParams({ agentId: selectedAgentId });
        } else {
            setSearchParams({});
        }
    }, [setSearchParams]);

    // Filter chats based on agentId parameter
    // Always filter out chats that only have My Twin Agent as the sole member
    const filteredChats = useMemo(() => {
        if (!myTwinAgentId) {
            return chats;
        }
        
        const filtered = chats.filter(chat => {
            // 首先检查聊天名称 - 任何名为 "My Twin Agent" 的聊天都要过滤掉
            if (chat.name === 'My Twin Agent') {
                return false;
            }
            
            // 检查 members（如果存在）
            if (chat.members && chat.members.length > 0) {
                // 过滤掉只有 My Twin Agent 的聊天
                const nonMyTwinMembers = chat.members.filter(m => m.userId !== myTwinAgentId);
                
                if (nonMyTwinMembers.length === 0) {
                    // Only My Twin Agent in this chat, filter it out
                    return false;
                }
                
                // 如果正在按 agentId 过滤，显示所有剩余的聊天（已经过滤掉了只有 My Twin Agent 的）
                if (agentId) {
                    return true;
                }
                
                // 默认视图：也过滤掉包含 My Twin Agent 的聊天
                const hasMemberWithMyTwinAgent = chat.members.some(member => member.userId === myTwinAgentId);
                
                if (hasMemberWithMyTwinAgent) {
                    return false;
                }
                
                return true;
            }
            
            // 如果没有 members 信息，通过 agent_id 判断
            if ((chat as any).agent_id === myTwinAgentId) {
                return false;
            }
            
            // 默认保留
            return true;
        });
        
        return filtered;
    }, [chats, myTwinAgentId, agentId]);
    
    // Auto-select or restore chat selection when agentId changes or when current chat is not in filtered list
    useEffect(() => {
        if (filteredChats.length === 0 || !username) {
            return;
        }
        
        // Normalize agentId (null and undefined are treated the same)
        const normalizedAgentId = agentId || undefined;
        
        // Check if current activeChatId is in filteredChats
        const isActiveChatInFiltered = activeChatId && filteredChats.some(chat => chat.id === activeChatId);
        
        // 注意：由于启用了 KeepAlive，activeChatId 会自动保持
        // 不需要从 ChatStateManager 恢复状态
        let restoredFromSavedState = false;
        try {
            // 旧的状态恢复逻辑已移除
            const savedChatId = null;
            const savedAgentId = null;
            
            logger.info(`[Auto-select] Restore check - current activeChatId: ${activeChatId}, saved: ${savedChatId}, currentAgentId: ${agentId}, savedAgentId: ${savedAgentId}, hasAutoSelected: ${hasAutoSelectedRef.current}`);
            
            // Only restore if the saved state matches current agentId (or both are null)
            const agentIdMatches = (savedAgentId === agentId) || (!savedAgentId && !agentId);
            const isSavedChatInFilteredList = savedChatId && filteredChats.some(chat => chat.id === savedChatId);
            const canRestore = savedChatId && agentIdMatches && isSavedChatInFilteredList;
            
            logger.info(`[Auto-select] Restore conditions - agentIdMatches: ${agentIdMatches}, isSavedChatInFilteredList: ${isSavedChatInFilteredList}, canRestore: ${canRestore}`);
            
            if (canRestore) {
                // Check if we need to restore (only restore once per mount or agentId change)
                const needsRestore = !hasAutoSelectedRef.current || normalizedAgentId !== lastAutoSelectAgentId.current;
                
                if (needsRestore) {
                    logger.info(`[Auto-select] Restoring saved chat: ${savedChatId} (current: ${activeChatId}, needsRestore: ${needsRestore})`);
                    
                    // Always restore the chat selection
                    // Use setActiveChatIdAndFetchMessages which will properly load messages
                    setActiveChatIdAndFetchMessages(savedChatId as string);
                } else {
                    logger.info(`[Auto-select] Saved chat ${savedChatId} already restored, skipping`);
                }
                
                // Mark as handled for current filter to prevent further auto-select this turn
                lastAutoSelectAgentId.current = normalizedAgentId;
                hasAutoSelectedRef.current = true;
                restoredFromSavedState = true;
                return;
            } else if (savedChatId && !isSavedChatInFilteredList) {
                // Saved chat exists but not in filtered list - force select first chat
                logger.info(`[Auto-select] Saved chat ${savedChatId} not in filtered list (agentIdMatches: ${agentIdMatches}), selecting first chat`);
                // Force select first chat even if activeChatId is same as savedChatId
                if (activeChatId === savedChatId || !isActiveChatInFiltered) {
                    const firstChatId = filteredChats[0].id;
                    logger.info(`[Auto-select] Forcing selection of first chat: ${firstChatId}`);
                    setTimeout(() => {
                        setActiveChatIdAndFetchMessages(firstChatId);
                    }, 0);
                    hasAutoSelectedRef.current = true;
                    return;
                }
            } else if (!savedChatId) {
                logger.info(`[Auto-select] No saved chat found in state manager`);
            }
        } catch (e) {
            logger.warn('[Auto-select] Failed to restore saved chat:', e);
        }
        
        // Scenario 1: agentId changed - always select first chat
        if (normalizedAgentId !== lastAutoSelectAgentId.current) {
            const firstChatId = filteredChats[0].id;
            logger.info(`[Auto-select] Agent filter changed from ${lastAutoSelectAgentId.current || 'none'} to ${normalizedAgentId || 'default'}, selecting first chat: ${firstChatId}`);
            // Use setTimeout to ensure this runs after filteredChats is fully updated
            setTimeout(() => {
                setActiveChatIdAndFetchMessages(firstChatId);
            }, 0);
            lastAutoSelectAgentId.current = normalizedAgentId;
            hasAutoSelectedRef.current = false; // Reset for new filter
            return;
        }
        
        // Scenario 2: Current chat is not in filtered list
        if (!isActiveChatInFiltered && !hasAutoSelectedRef.current && !restoredFromSavedState) {
            const firstChatId = filteredChats[0].id;
            logger.info(`[Auto-select] Current chat not in filtered list (activeChatId: ${activeChatId}), selecting first chat: ${firstChatId}`);
            setTimeout(() => {
                setActiveChatIdAndFetchMessages(firstChatId);
            }, 0);
            hasAutoSelectedRef.current = true;
        }
    }, [agentId, filteredChats, activeChatId, setActiveChatIdAndFetchMessages, username]);

    const renderListContent = () => {
        return (
            <ChatList
                chats={filteredChats}
                activeChatId={activeChatId}
                onChatSelect={setActiveChatIdAndFetchMessages}
                onChatDelete={handleChatDelete}
                onChatPin={handleChatPin}
                onChatMute={handleChatMute}
                onFilterChange={handleFilterChange}
                onSearch={handleSearch}
                onFilterClick={() => setShowFilterModal(true)}
                filterAgentId={agentId}
                currentAgentId={headerAgentId}
            />
        );
    };

    // 处理消息已读回调
    const handleMessagesRead = useCallback((chatId: string, count: number) => {
        setChats(prevChats => {
            return prevChats.map(chat => {
                if (chat.id === chatId) {
                    const newUnread = Math.max(0, (chat.unread || 0) - count);
                    return { ...chat, unread: newUnread };
                }
                return chat;
            });
        });
    }, []);
    
    // Calculate chat title with member names
    const getChatTitle = useCallback((chat: Chat | null) => {
        if (!chat) return t('pages.chat.chatDetails');
        
        // If chat has members, show member names with priority sorting
        if (chat.members && chat.members.length > 0) {
            // Filter out My Twin Agent from members
            const filteredMembers = chat.members.filter(m => m.userId !== myTwinAgentId);
            
            if (filteredMembers.length === 0) {
                // If only My Twin Agent, show chat name
                return chat.name;
            }
            
            // Sort members: priority agent (agentId) first, then others
            const sortedMembers = [...filteredMembers].sort((a, b) => {
                if (agentId) {
                    if (a.userId === agentId) return -1;
                    if (b.userId === agentId) return 1;
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
            
            return memberNames || chat.name;
        }
        
        return chat.name;
    }, [agentId, myTwinAgentId, t]);

    const renderDetailsContent = () => (
        <Suspense fallback={<div className="loading-container">{t('common.loading')}</div>}>
            <ChatDetail 
                chatId={activeChatId} 
                chats={chats}
                onSend={handleMessageSend}
                setIsInitialLoading={setIsInitialLoading}
                onMessagesRead={handleMessagesRead}
                filterAgentId={agentId}
            />
        </Suspense>
    );

    const renderRightPanel = () => {
        return (
            <Suspense fallback={<div className="loading-container">{t('common.loading')}</div>}>
                <ChatNotification 
                    chatId={activeChatId || ''} 
                    isInitialLoading={isInitialLoadingNotifications}
                />
            </Suspense>
        );
    };

    // 显示加载状态或错误信息
    if (isLoading && chats.length === 0) {
        return <div className="loading-container">{t('common.loading')}</div>;
    }

    // 优化：无论 chats 是否为空，都渲染 ChatLayout，只是 detailsContent 为空时显示提示
    return (
        <>
            <ChatLayout
                listTitle={t('pages.chat.title')}
                detailsTitle={getChatTitle(currentChat)}
                listContent={renderListContent()}
                detailsContent={currentChat ? renderDetailsContent() : <div className="empty-chat-placeholder">{t('pages.chat.selectAChat')}</div>}
                chatNotificationTitle={t('pages.chat.chatNotificationTitle')}
                chatNotificationContent={renderRightPanel()}
                hasNewAgentNotifications={hasNew}
                onRightPanelToggle={(collapsed) => {
                    if (!collapsed) {
                        markAsRead();
                    }
                }}
            />
            
            {/* Agent 过滤器模态框 */}
            <AgentFilterModal
                visible={showFilterModal}
                selectedAgentId={agentId}
                onSelect={handleFilterSelect}
                onCancel={() => setShowFilterModal(false)}
            />
        </>
    );
};

export default ChatPage;
