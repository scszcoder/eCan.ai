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
import { messageManager } from './managers/MessageManager';
import { getDisplayMsg } from './utils/displayMsg';
import { iTagManager } from './managers/ITagManager';
import { chatStateManager } from './managers/ChatStateManager';
import { eventBus } from '@/utils/eventBus';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentIdFromUrl = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    const agents = useAgentStore(state => state.agents);
    const getMyTwinAgent = useAgentStore(state => state.getMyTwinAgent);
    
    // 直接从 store Get myTwinAgent，确保始终是最新的
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
    
    // Reference型Status，Used for跟踪和控制
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
    
    // 每次Render都Update ref，确保它始终指向最新的 handleChatSelect
    handleChatSelectRef.current = null; // Will be set later after handleChatSelect is defined

    // 使用全局Notification管理器和Message管理器
    const { hasNew, markAsRead } = useChatNotifications(activeChatId || '');
    const { allMessages, unreadCounts, markAsRead: markMessageAsRead, updateMessages, addMessageToChat, updateMessage } = useMessages();

    // 新增独立的 loading Status
    const [isInitialLoadingNotifications, setIsInitialLoadingNotifications] = useState(false);
    
    // Filter器和SearchStatus
    const [searchText, setSearchText] = useState('');
    const searchTextRef = useRef(''); // Save最新的Search文本
    const [showFilterModal, setShowFilterModal] = useState(false);

    // ComponentMount时Initialize并确保 agents 已Load
    useEffect(() => {
        const initializeComponent = async () => {
            const agentStore = useAgentStore.getState();
            if (agentStore.agents.length === 0 && username) {
                await agentStore.fetchAgents(username);
            }
            
            // Note：ScrollStatus由 KeepAlive 自动管理，不Need手动Cleanup
            
            // agents LoadCompleted后，Settings标志（Remove setTimeout，直接Settings）
            effectsCompletedRef.current = true;
        };
        
        initializeComponent();
        
        return () => {
            effectsCompletedRef.current = false;
            isFetchingRef.current = false;
            isCreatingChatRef.current = false;
        };
    }, [username]);
    
    // CRITICAL FIX: Listen to agentIdFromUrl changes to handle KeepAlive scenario
    // When user navigates from agents page back to chat, component doesn't remount (KeepAlive),
    // but URL params change, so we need to detect this and trigger fetch
    const prevAgentIdFromUrlRef = useRef<string | null>(null);
    useEffect(() => {
        const currentAgentIdFromUrl = searchParams.get('agentId');
        const prevAgentIdFromUrl = prevAgentIdFromUrlRef.current;
        
        // If agentId from URL changed from null/undefined to a value, and lastFetchedAgentId was reset
        if (currentAgentIdFromUrl !== prevAgentIdFromUrl && currentAgentIdFromUrl && !prevAgentIdFromUrl) {
            // If lastFetchedAgentId was reset (undefined), force agentId change detection
            if (lastFetchedAgentId.current === undefined && myTwinAgentId && !isFetchingRef.current) {
                // Reset fetchOnceRef to allow the main useEffect to trigger fetch
                fetchOnceRef.current = false;
                // The main useEffect will detect agentId !== lastFetchedAgentId and trigger fetch
            }
        }
        
        prevAgentIdFromUrlRef.current = currentAgentIdFromUrl;
    }, [searchParams, myTwinAgentId]);

    // 统一的DataGet effect - 合并 myTwinAgentId、initialized 和 agentId 的Listen
    useEffect(() => {
        // Check是否NeedGetData
        const shouldFetch = (
            myTwinAgentId && // Must有 myTwinAgentId
            !isFetchingRef.current && // 不在Get中
            (
                !fetchOnceRef.current || // 首次Get
                (initialized && !hasFetched) || // initialized 变化
                agentId !== lastFetchedAgentId.current // agentId 变化（包括从有值变为undefined，或从undefined变为有值）
            )
        );
        
        if (shouldFetch) {
            // Update标志
            if (!fetchOnceRef.current) {
                fetchOnceRef.current = true;
            }
            if (initialized && !hasFetched) {
                setHasFetched(true);
            }
            if (agentId !== lastFetchedAgentId.current) {
                lastFetchedAgentId.current = agentId || undefined;
            }
            
            // 直接调用 fetchChats（Remove setTimeout）
            fetchChats();
        }
        
        // Update prevInitialized
        prevInitialized.current = initialized;
    }, [myTwinAgentId, initialized, hasFetched, agentId]);

    // CRITICAL FIX: Update MessageManager with active chat
    // This prevents MessageManager from incrementing unread count for active chat
    useEffect(() => {
        messageManager.setActiveChat(activeChatId);
    }, [activeChatId]);

    // CRITICAL FIX: Listen to new messages and clear unread for active chat (fallback)
    // Even though MessageManager won't increment for active chat, we still clear it as a safety measure
    useEffect(() => {
        const handleNewMessage = (params: any) => {
            const { chatId, message } = params;
            const realChatId = chatId || message?.chatId;
            
            if (!realChatId || !activeChatId) {
                return;
            }
            
               // Only process if this message is for the currently active chat
               if (realChatId === activeChatId) {
                   // Check if this is an incoming message (not from current user/myTwinAgent)
                   const senderId = message?.senderId;
                   if (senderId && senderId !== myTwinAgentId) {
                       // Clear unread count for this chat (safety measure, MessageManager should already skip increment)
                       markMessageAsRead(activeChatId);
                   }
               }
        };
        
        eventBus.on('chat:newMessage', handleNewMessage);
        
        return () => {
            eventBus.off('chat:newMessage', handleNewMessage);
        };
    }, [activeChatId, myTwinAgentId, markMessageAsRead]);

    // SyncMessage管理器中的Message到聊天List
    // Update chats when messages or unread counts change
    useEffect(() => {
        setChats(prevChats => {
            return prevChats.map(chat => {
                const messages = allMessages.get(chat.id) || [];
                const unreadCount = unreadCounts.get(chat.id) || 0;

                // Get the last message from messages (includes both sent and received)
                // Messages are sorted by time (oldest to newest)
                let lastMsg = chat.lastMsg;
                let lastMsgTime = chat.lastMsgTime;
                
                if (messages.length > 0) {
                    // Get the last message regardless of status
                    const lastMessage = messages[messages.length - 1];
                    // Only use completed/success/sending messages for display (skip failed messages)
                    if (lastMessage.status !== 'failed' && lastMessage.status !== 'error') {
                        lastMsg = getDisplayMsg(lastMessage.content, t);
                        lastMsgTime = lastMessage.createAt;
                    }
                } else if (lastMsg) {
                    // Fallback: if no messages in memory but chat has lastMsg from DB, format it
                    // Parse if it's a JSON string, then format
                    let parsedMsg = lastMsg;
                    if (typeof lastMsg === 'string') {
                        try {
                            parsedMsg = JSON.parse(lastMsg);
                        } catch {
                            // If parsing fails, it's already a string, use it directly
                            parsedMsg = lastMsg;
                        }
                    }
                    lastMsg = getDisplayMsg(parsedMsg, t);
                }

                return {
                    ...chat,
                    messages,
                    unread: unreadCount,
                    lastMsg: lastMsg || '', // Already processed by getDisplayMsg, ensure it's not null
                    lastMsgTime,
                };
            });
        });
    }, [allMessages, unreadCounts, t]);

    // 抽取Get聊天的Function，Can在多个地方调用
    const fetchChats = async () => {
        // If已经在Get中，跳过
        if (isFetchingRef.current) {
            return;
        }
        
        // SettingsLoadStatus和锁
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
            
            // 使用 ref Get最新的Search文本
            const currentSearchText = searchTextRef.current;
            
            // Only use cache if: no search text, cache exists, AND cache is for the same userId
            if ((!currentSearchText || currentSearchText.trim() === '') && 
                allChatsCache.current.length > 0 && 
                cachedUserId.current === targetUserId) {
                setChats(prevChats => {
                    // IfCache和When前Data相同，不Update（避免重新Render）
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
            
            // 根据是否有Search文本Select不同的 API
            if (currentSearchText && currentSearchText.trim()) {
                // 使用Search API
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
                    
                    // Parse并Format lastMsg Field
                    chatData = chatData.map(chat => {
                        let parsedMsg = chat.lastMsg;
                        
                        // If是字符串，先Parse
                        if (typeof parsedMsg === 'string') {
                            try {
                                parsedMsg = JSON.parse(parsedMsg);
                            } catch (e) {
                                logger.warn(`[fetchChats] Failed to parse lastMsg for chat ${chat.id}`);
                            }
                        }
                        
                        // 使用 getDisplayMsg FormatDisplay
                        return {
                            ...chat,
                            lastMsg: getDisplayMsg(parsedMsg, t),
                        };
                    });
                    
                    // 智能Update：保持现有聊天的Reference，只Update变化的部分
                    setChats(prevChats => {
                        // IfData相同，不Update（避免闪烁）
                        if (prevChats.length === chatData.length && 
                            prevChats.every((chat, i) => chat.id === chatData[i]?.id)) {
                            return prevChats;
                        }
                        // IfSearchResult为空且之前有Data，也保持Reference（避免闪烁）
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
                // 使用普通Query API
                await getChatsAndSetState(targetUserId);
            }
        } catch (error) {
            logger.error("Error in fetchChats:", error);
        } finally {
            // ResetLoadStatus和锁
            setIsLoading(false);
            isFetchingRef.current = false;
        }
    };
    
    // GeneralGet聊天Data的Function，使用新的 API，并在GetData后ProcessagentId相关逻辑
    const getChatsAndSetState = async (userId?: string) => {
        if (!userId) {
            logger.error("[getChatsAndSetState] Missing userId");
            return;
        }
        
        try {
            // 使用新的 API Get聊天Data
            const response = await get_ipc_api().chatApi.getChats(
                userId,
                true // deep Parameter，包含 members 数据
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
                
                // 这里直接对 lastMsg 做 display Parse
                const processedChats = chatData.map(chat => ({
                    ...chat,
                    lastMsg: getDisplayMsg(chat.lastMsg, t),
                }));
                
                // UpdateCache
                allChatsCache.current = processedChats;
                
                setChats(processedChats);
                
                // ProcessagentId相关逻辑
                if (agentId) {
                    // Get the latest myTwinAgentId
                    const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
                    const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
                    
                    // 1. 查找是否存在Include该agentId的聊天
                    const chatWithAgent = chatData.find(chat => 
                        chat.members?.some(member => member.userId === agentId)
                    );
                    
                    if (chatWithAgent) {
                        // 2A. If找到，Settings为活动聊天
                        // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                        setActiveChatIdAndFetchMessages(chatWithAgent.id);
                    } else if (agentId === currentMyTwinAgentId) {
                        // 2B. If agentId 是 MyTwinAgent，不要Create聊天（会被Filter掉）
                        // 而是Select第一个Available的聊天（但要Exclude My Twin Agent 自己的聊天）
                        if (chatData.length > 0) {
                            // 应用Filter逻辑，找到第一个not "My Twin Agent" 的聊天
                            const firstValidChat = chatData.find(chat => {
                                // Filter掉名为 "My Twin Agent" 的聊天
                                if (chat.name === 'My Twin Agent') {
                                    return false;
                                }
                                
                                // Filter掉只有 My Twin Agent 的聊天
                                if (chat.members && chat.members.length > 0) {
                                    const nonMyTwinMembers = chat.members.filter(m => m.userId !== currentMyTwinAgentId);
                                    if (nonMyTwinMembers.length === 0) {
                                        return false;
                                    }
                                }
                                
                                // Filter掉 agent_id 等于 myTwinAgentId 的聊天
                                if ((chat as any).agent_id === currentMyTwinAgentId) {
                                    return false;
                                }
                                
                                return true;
                            });
                            
                            if (firstValidChat) {
                                setActiveChatIdAndFetchMessages(firstValidChat.id);
                            } else {
                                logger.warn(`[fetchChats] No valid chat found after filtering`);
                            }
                        }
                    } else {
                        // 2C. If没找到，且not MyTwinAgent，Create新的聊天
                        // Check是否已经在Create聊天中
                        if (!isCreatingChatRef.current) {
                            await createChatWithAgent(agentId);
                        }
                    }
                } else if (chatData.length > 0) {
                    // If没有agentId，但有聊天List，Select第一个聊天
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
    
    // Create和Agent的聊天的HelperFunction
    const createChatWithAgent = async (targetAgentId: string) => {
        // Get the latest myTwinAgentId from store
        const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
        const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
        
        if (!currentMyTwinAgentId) {
            logger.error("[createChatWithAgent] Missing myTwinAgentId");
            return;
        }
        
        // Check是否是和自己聊天（targetAgentId === currentMyTwinAgentId）
        const isSelfChat = targetAgentId === currentMyTwinAgentId;
        
        // 🚫 阻止Create只Include My Twin Agent 的聊天（会被Filter掉）
        if (isSelfChat) {
            logger.warn("[createChatWithAgent] Preventing creation of self-chat with My Twin Agent (would be filtered)");
            return;
        }
        
        // If已经在Create聊天中，跳过
        if (isCreatingChatRef.current) {
            return;
        }
        
        // SettingsCreate聊天锁
        isCreatingChatRef.current = true;
        
        try {
            const my_twin_agent = useAgentStore.getState().getAgentById(currentMyTwinAgentId);
            const receiver_agent = useAgentStore.getState().getAgentById(targetAgentId);
            
            // Create聊天Data（isSelfChat 已经在前面被阻止了，这里不会Execute）
            const chatData = {
                members: [
                    {"userId": currentMyTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"},
                    {"userId": targetAgentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                ],
                name: receiver_agent?.card.name || `Chat with ${targetAgentId}`,
                type: 'user-agent',
                agent_id: targetAgentId,  // ✅ Add agent_id
            };
            
            const response = await get_ipc_api().chatApi.createChat(chatData);
            const resp: any = response;
            
            // Check if IPC call succeeded
            if (resp.success && resp.data) {
                // Check if backend operation succeeded (new chat created)
                if (resp.data.success && resp.data.data) {
                    // 提取新聊天Data
                    const newChat = { ...resp.data.data, name: resp.data.data.name || chatData.name } as Chat;
                    
                    // Update聊天List
                    setChats(prevChats => {
                        const exists = prevChats.some(c => c.id === newChat.id);
                        return exists
                            ? prevChats.map(c => c.id === newChat.id ? { ...c, ...newChat } : c)
                            : [...prevChats, newChat];
                    });
                    
                    // Settings为活动聊天并GetMessage
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
            // ResetCreate聊天锁
            isCreatingChatRef.current = false;
        }
    };

    // PageInitialize
    useEffect(() => {
        // 只要 initialized 变 true，Reset hasFetched
        if (initialized) setHasFetched(false);
    }, [initialized]);

    const handleFilterChange = useCallback(() => {
    }, []);

    // 新增：SettingsactiveChatId并GetMessage的Function，避免重复调用handleChatSelect
    const setActiveChatIdAndFetchMessages = useCallback((chatId: string) => {
        // Note：选中的聊天ID由 KeepAlive 自动保持，不Need手动Save
        
        setActiveChatId(chatId);
        // 直接调用 handleChatSelect（Remove setTimeout，使用 ref 确保最新Function）
        if (handleChatSelectRef.current) {
            handleChatSelectRef.current(chatId);
        }
    }, [username, agentId, chats, myTwinAgentId]);

    // Settings活动聊天ID
    const setActiveChat = useCallback((chatId: string) => {
        // If是通过setActiveChatIdAndFetchMessages调用的，不Need再次SettingsactiveChatId
        if (activeChatId !== chatId) {
            setActiveChatId(chatId);
        }
    }, [activeChatId]);

    // 标记Message为已读
    const markChatAsRead = useCallback((chatId: string) => {
        markMessageAsRead(chatId);
    }, [markMessageAsRead]);

    // 假设 PAGE_SIZE 已Definition（如 20），否则加上 const PAGE_SIZE = 20;
    const PAGE_SIZE = 20;
    // Get并Process聊天Message
    const fetchAndProcessChatMessages = async (chatId: string, setIsInitialLoading?: (loading: boolean) => void) => {
        try {
            const response = await get_ipc_api().chatApi.getChatMessages({
                chatId,
                limit: PAGE_SIZE,
                offset: 0,
                reverse: true  // Get最新的Message（倒序）
            });
            console.log("[chat message] result>>>", response.data);
            
            if (response.success && response.data) {
                let messages: Message[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Message[]
                        : [];
                
                // 确保每个Message都有唯一的 ID
                messages = messages.map((message, index) => ({
                    ...message,
                    id: message.id || 'server_msg_' + Date.now() + '_' + index + '_' + Math.random().toString(36).substr(2, 9)
                }));
                
                // 使用Message管理器UpdateMessage
                updateMessages(chatId, messages);
            } else {
                // Failed时清空Message并OptionalPrompt
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

    // Get并Process聊天Notification（仅首次Load，Support分页）
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

    // Clickchat时的主ProcessFunction
    const handleChatSelect = async (chatId: string) => {
        // 1. 标记为已读
        markChatAsRead(chatId);
        
        // 2. Settings活动聊天
        setActiveChat(chatId);
        
        // 3. 并行GetMessage和Notification（Notification只拉第一页，后续分页交给 useChatNotifications）
        await Promise.all([
            fetchAndProcessChatMessages(chatId, setIsInitialLoading),
            fetchAndProcessChatNotifications(chatId, setIsInitialLoadingNotifications)
        ]);
    };
    
    // Update ref to point to the latest handleChatSelect
    handleChatSelectRef.current = handleChatSelect;

    const handleChatDelete = async (chatId: string) => {
        try {
            // Find the chat to be deleted
            const deletedChat = chats.find(c => c.id === chatId);
            logger.info(`[handleChatDelete] Deleting chat ${chatId}, deletedChat found: ${!!deletedChat}`);
            
            // 调用 API Delete聊天（先删除，避免竞态条件）
            const response = await get_ipc_api().chatApi.deleteChat(chatId);
            
            if (!response.success) {
                logger.error('Failed to delete chat:', response.error);
                setError(`Failed to delete chat: ${response.error?.message || 'Unknown error'}`);
                return;
            }
            
            // 删除成功后再Update UI
            const updatedChats = chats.filter(c => c.id !== chatId);
            setChats(updatedChats);

            // IfDelete的是When前聊天，则Toggle到第一个聊天
            if (activeChatId === chatId) {
                const nextChatId = updatedChats[0]?.id || null;
                if (nextChatId) {
                    setActiveChatId(nextChatId);
                    handleChatSelect(nextChatId);
                } else {
                    // 没有剩余的 chat，清除 activeChatId 和 URL Parameter
                    setActiveChatId(null);
                    setSearchParams({});
                    
                    // CRITICAL FIX: Reset lastFetchedAgentId and clear ChatStateManager
                    // This ensures agentId will be read from URL next time user navigates back
                    if (deletedChat && agentId) {
                        const isChatWithCurrentAgent = deletedChat.members?.some(
                            member => member.userId === agentId
                        );
                        if (isChatWithCurrentAgent) {
                            // Clear ChatStateManager to force agentId to be read from URL next time
                            if (username) {
                                chatStateManager.saveAgentId(username, null);
                            }
                            // Use setTimeout to allow navigation to complete
                            setTimeout(() => {
                                lastFetchedAgentId.current = undefined;
                                // Also reset fetchOnceRef to allow fetch when returning
                                fetchOnceRef.current = false;
                            }, 500); // 500ms should be enough for navigation
                        }
                    }
                }
            }
        } catch (err) {
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

    // handleMessageSend SendMessage时加 log
    const handleMessageSend = useCallback(async (content: string, attachments: Attachment[]) => {
        console.log('[handleMessageSend] called, content:', content, 'attachments:', attachments);
        if (!activeChatId) {
            logger.error('No activeChatId!!!');
            return;
        }

        // Check if chat exists in current chats list
        let chat = chats.find(c => c.id === activeChatId);
        
        // If chat not found (e.g., was deleted), we need to create a new one
        if (!chat) {
            logger.warn(`Chat ${activeChatId} not found in chats list, backend will create new chat`);
        }

        if (!myTwinAgentId) return;
        const my_twin_agent = useAgentStore.getState().getAgentById(myTwinAgentId);
        const senderId = my_twin_agent?.card.id;
        const senderName = my_twin_agent?.card.name;
        if (!senderId || !senderName) return;

        // 只保留可SerializeField，优先使用 response Field（如有）
        const safeAttachments = (attachments || []).map(att => {
            if (!att) return att;
            const attAny = att as any;
            if (attAny.response && typeof attAny.response === 'object') {
                // response Field通常是Backend返回的 attachment Information
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
            content: content, // 只做文本或结构化Content
            status: 'sending',
            attachments: safeAttachments // Standard附件数组
        };

        // 先乐观地Update UI - 使用Message管理器
        addMessageToChat(activeChatId, userMessage);
        console.log('[handleMessageSend] after addMessageToChat, allMessages:', allMessages);

        try {
            // Get receiver info from current chat members
            let receiverId: string | undefined;
            let receiverName: string | undefined;
            
            if (chat && chat.members) {
                // Normal case: Get receiver from chat members
                const receiver = chat.members.find(m => m.userId !== senderId);
                if (receiver) {
                    receiverId = receiver.userId;
                    receiverName = receiver.name || receiver.agentName;
                }
            } else if (!chat && agentId) {
                // Chat was deleted: Use agentId from URL as receiver
                receiverId = agentId;
                const receiverAgent = useAgentStore.getState().getAgentById(agentId);
                receiverName = receiverAgent?.card?.name || 'Agent';
            }
            
            // 使用新的 API SendMessage
            const messageData = {
                chatId: activeChatId,
                senderId, // 明确为 string
                role: "user",
                content: content,
                createAt: String(Date.now()),
                senderName,
                status: 'complete',
                i_tag: iTagManager.getLatest(activeChatId) || undefined,
                attachments: safeAttachments as any,
                receiverId,
                receiverName
            };
            
            const response = await get_ipc_api().chatApi.sendChat(messageData);
            if (!response.success) {
                logger.error('Failed to send message:', response.error);
                // UpdateMessageStatus为Error
                updateMessage(activeChatId, userMessage.id, { status: 'error' as const });
                return;
            }
            
            // Check if backend returned a new chatId (when chat was auto-created)
            const responseData = response.data as any;
            if (responseData && responseData.realChatId && responseData.originalChatId) {
                const newChatId = responseData.realChatId;
                const oldChatId = responseData.originalChatId;
                
                
                // Update activeChatId
                setActiveChatId(newChatId);
                
                // Update chat in chat list or create new chat entry
                setChats(prevChats => {
                    const existingChatIndex = prevChats.findIndex(c => c.id === oldChatId);
                    
                    if (existingChatIndex >= 0) {
                        // Update existing chat
                        return prevChats.map(chat => {
                            if (chat.id === oldChatId) {
                                return { ...chat, id: newChatId };
                            }
                            return chat;
                        });
                    } else {
                        // Create new chat entry (chat was deleted and recreated)
                        const newChat: Chat = {
                            id: newChatId,
                            name: receiverName || 'Chat',
                            avatar: undefined,
                            lastMsg: content as string,
                            lastMsgTime: Date.now(),
                            unread: 0,
                            pinned: false,
                            muted: false,
                            type: 'user-agent',
                            messages: [],
                            members: receiverId ? [
                                {
                                    userId: senderId,
                                    name: senderName,
                                    role: 'user',
                                    agentName: senderName
                                },
                                {
                                    userId: receiverId,
                                    name: receiverName!,
                                    role: 'agent',
                                    agentName: receiverName!
                                }
                            ] : []
                        };
                        return [newChat, ...prevChats];
                    }
                });
                
                // Update messages chatId through message hook
                // The message will be updated with the new chatId automatically
                // since we're updating the message with the server response
            }
            
            // UpdateMessageStatus为已Send，并使用Service器返回的Message ID
            if (response.data && (response.data as any).id) {
                // 替换乐观Update的Message，使用Service器返回的 ID
                const finalChatId = responseData?.realChatId || activeChatId;
                updateMessage(activeChatId, userMessage.id, { 
                    id: (response.data as any).id,
                    chatId: finalChatId, // Use the real chatId
                    status: 'complete' as const,
                    // 保留Service器返回的其他Field
                    ...(response.data as any)
                });
            } else {
                // IfService器没有返回Message ID，则只UpdateStatus
                updateMessage(activeChatId, userMessage.id, { status: 'complete' as const });
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error sending message:', errorMessage);
            
            // UpdateMessageStatus为Error
            updateMessage(activeChatId, userMessage.id, { status: 'error' as const });
        }
    }, [activeChatId, chats, myTwinAgentId, addMessageToChat, allMessages, updateMessage]);
    
    const currentChat = (!activeChatId || !chats || chats.length === 0)
        ? null
        : chats.find((c) => c.id === activeChatId) || null;

    // Compute left panel header agentId: DisplayWhen前Filter的 agent 的视频
    // 视频不跟随选中的 chat 改变，只跟随Filter器（agentId Parameter）改变
    const headerAgentId = useMemo(() => {
        // Priority：URL agentId（Filter器Select）> myTwinAgentId（Default）> fallback
        if (agentId) {
            return agentId;
        }
        
        if (myTwinAgentId) {
            return myTwinAgentId;
        }
        
        // Fallback：随机Select一个System agent
        if (chats.length === 0) {
            const systemAgents = agents.filter(a => a.card?.id?.startsWith('system_'));
            if (systemAgents.length > 0) {
                const randomIndex = Math.floor(Math.random() * systemAgents.length);
                const fallbackId = systemAgents[randomIndex].card?.id;
                return fallbackId;
            }
        }
        
        // 最终 fallback
        const fallbackId = agents && agents.length > 0 ? agents[0].card?.id : undefined;
        return fallbackId;
    }, [agentId, myTwinAgentId, agents, chats.length]);
    
    // Search防抖定时器 ref
    const searchDebounceTimer = useRef<NodeJS.Timeout | null>(null);
    
    // ProcessSearch
    const handleSearch = useCallback((text: string) => {
        setSearchText(text);
        searchTextRef.current = text;
        
        // 清除之前的定时器
        if (searchDebounceTimer.current) {
            clearTimeout(searchDebounceTimer.current);
            searchDebounceTimer.current = null;
        }
        
        // If清空Search，立即Execute（不Delay）
        if (!text || text.trim() === '') {
            if (effectsCompletedRef.current) {
                fetchChats();
            }
        } else {
            // 有Search文本时，使用防抖定时器
            searchDebounceTimer.current = setTimeout(() => {
                if (effectsCompletedRef.current) {
                    fetchChats();
                }
                searchDebounceTimer.current = null;
            }, 300);
        }
    }, []);
    
    // CleanupSearch防抖定时器
    useEffect(() => {
        return () => {
            if (searchDebounceTimer.current) {
                clearTimeout(searchDebounceTimer.current);
            }
        };
    }, []);
    
    // ProcessFilter器Select
    const handleFilterSelect = useCallback((selectedAgentId: string | null) => {
        setShowFilterModal(false);

        // Save or clear the agentId in ChatStateManager
        if (username) {
            if (selectedAgentId) {
                chatStateManager.saveAgentId(username, selectedAgentId);
            } else {
                // Clear the saved agentId when filter is cleared
                chatStateManager.saveAgentId(username, null);
            }
        }
        
        // Update URL Parameter
        if (selectedAgentId) {
            setSearchParams({ agentId: selectedAgentId });
        } else {
            setSearchParams({});
        }
    }, [setSearchParams, username]);

    // Filter chats based on agentId parameter
    // Always filter out chats that only have My Twin Agent as the sole member
    const filteredChats = useMemo(() => {
        if (!myTwinAgentId) {
            return chats;
        }
        
        const filtered = chats.filter(chat => {
            // 首先Check聊天Name - 任何名为 "My Twin Agent" 的聊天都要Filter掉
            if (chat.name === 'My Twin Agent') {
                return false;
            }
            
            // Check members（If存在）
            if (chat.members && chat.members.length > 0) {
                // Filter掉只有 My Twin Agent 的聊天
                const nonMyTwinMembers = chat.members.filter(m => m.userId !== myTwinAgentId);
                
                if (nonMyTwinMembers.length === 0) {
                    // Only My Twin Agent in this chat, filter it out
                    return false;
                }
                
                // If正在按 agentId Filter，DisplayAll剩余的聊天（已经Filter掉了只有 My Twin Agent 的）
                if (agentId) {
                    return true;
                }
                
                // Default视图：也Filter掉Include My Twin Agent 的聊天
                const hasMemberWithMyTwinAgent = chat.members.some(member => member.userId === myTwinAgentId);
                
                if (hasMemberWithMyTwinAgent) {
                    return false;
                }
                
                return true;
            }
            
            // If没有 members Information，通过 agent_id 判断
            if ((chat as any).agent_id === myTwinAgentId) {
                return false;
            }
            
            // Default保留
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
        
        // Note：由于Enabled了 KeepAlive，activeChatId 会自动保持
        // 不Need从 ChatStateManager RestoreStatus
        let restoredFromSavedState = false;
        try {
            // 旧的StatusRestore逻辑已Remove
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

    // ProcessMessage已读Callback
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

    // DisplayLoadStatus或ErrorInformation
    if (isLoading && chats.length === 0) {
        return <div className="loading-container">{t('common.loading')}</div>;
    }

    // Optimize：无论 chats 是否为空，都Render ChatLayout，只是 detailsContent 为空时DisplayPrompt
    return (
        <>
            <ChatLayout
                listTitle={<span style={{ fontSize: '16px', fontWeight: 600, lineHeight: '24px' }}>{t('pages.chat.title')}</span>}
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
            
            {/* Agent Filter器模态框 */}
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
