import React, { useState, useEffect, useRef, useCallback, useMemo, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { App } from 'antd';
import ChatList from './components/ChatList';
const ChatDetail = lazy(() => import('./components/ChatDetail'));
import { Chat, Message, Attachment } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
const ChatNotification = lazy(() => import('./components/ChatNotification'));
import AgentFilterModal from './components/AgentFilterModal';
import { unifiedChatService } from '@/services/chat/unifiedChatService';
import { cloudChatApi } from '@/services/api/cloudChatApi';
import { isWebPlatform } from '@/config/platform';
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
import { UserStorageManager } from '@/services/storage/UserStorageManager';
import { subscribeToA2AChannel } from '@/services/web/appSyncSubscriptions';
import { streamChatCompletion, fetchLlmStreamConfig } from '@/services/llmStream';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const { message } = App.useApp();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentIdFromUrl = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    
    // DEPRECATED: My Twin Agent related code - kept for reference, will be removed later
    // const myTwinAgent = useAgentStore(state => state.getMyTwinAgent());
    // const myTwinAgentId = myTwinAgent?.card?.id;
    
    // Current user identification (replaced myTwinAgentId)
    const currentUserId = username ? `system_${username}` : 'system_user';
    const currentUserName = username || 'User';
    const agents = useAgentStore(state => state.agents);
    
    // Default agent selection (replaced My Twin Agent as default)
    const defaultAgentId = useMemo(() => {
        const nonSystemAgent = agents.find(agent => {
            const id = agent.card?.id || '';
            return !id.startsWith('system_');
        });
        return nonSystemAgent?.card?.id || agents[0]?.card?.id || null;
    }, [agents]);
    
    const initialized = useAppDataStore(state => state.initialized);
    
    // Compute effective agentId: URL parameter is the source of truth
    // When URL has agentId, use it; when URL is cleared, agentId should be null
    const agentId = agentIdFromUrl || null;
    
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
    const [, setError] = useState<string | null>(null);
    const [hasFetched, setHasFetched] = useState(false);
    const [, setIsInitialLoading] = useState(false);
    
    // Reference型Status，Used for跟踪和控制
    const lastFetchedAgentId = useRef<string | undefined>();
    const prevInitialized = useRef(initialized);
    const fetchOnceRef = useRef(false);
    const isFetchingRef = useRef(false);
    const isCreatingChatRef = useRef(false);
    const effectsCompletedRef = useRef(false);
    const allChatsCache = useRef<Chat[]>([]); // Cache all chats (when no search)
    const cachedUserId = useRef<string | undefined>(); // Track which userId the cache is for
    const hasAutoSelectedRef = useRef(false); // Track if we've auto-selected for current filter
    const lastAutoSelectAgentId = useRef<string | undefined>(); // Track agentId when last auto-selected
    const handleChatSelectRef = useRef<((chatId: string) => Promise<void>) | null>(null); // Ref to handleChatSelect
    const hasAutoFetchedCloudRef = useRef<string | null>(null); // Track if we've auto-fetched cloud messages for this agentId
    const fetchChatsDebounceRef = useRef<NodeJS.Timeout | null>(null); // Debounce rapid fetchChats calls
    const helloInitRef = useRef<Set<string>>(new Set()); // Track chatIds with auto hello sent
    const autoCreateChatRef = useRef<Set<string>>(new Set()); // Track agentIds with auto-create attempt
    
    // 每次Render都Update ref，确保它始终指向最新的 handleChatSelect
    handleChatSelectRef.current = null; // Will be set later after handleChatSelect is defined

    // 使用全局Notification管理器和Message管理器
    const { hasNew, markAsRead } = useChatNotifications(activeChatId || '');
    const { allMessages, unreadCounts, markAsRead: markMessageAsRead, updateMessages, addMessageToChat, updateMessage } = useMessages();

    // 新增独立的 loading Status
    const [isInitialLoadingNotifications, setIsInitialLoadingNotifications] = useState(false);
    
    // Filter器和SearchStatus
    const [, setSearchText] = useState('');
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
            // Cancel any pending debounced fetchChats
            if (fetchChatsDebounceRef.current) {
                clearTimeout(fetchChatsDebounceRef.current);
                fetchChatsDebounceRef.current = null;
            }
            // NOTE: Do NOT reset lastFetchedAgentId, fetchOnceRef, or lastAutoSelectAgentId here.
            // KeepAlive deactivation triggers this cleanup, and resetting these refs causes
            // a duplicate fetchChats() storm when the component reactivates because the
            // main useEffect sees agentId !== lastFetchedAgentId (undefined) and fires again.
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
            if (lastFetchedAgentId.current === undefined && defaultAgentId && !isFetchingRef.current) {
                // Reset fetchOnceRef to allow the main useEffect to trigger fetch
                fetchOnceRef.current = false;
                // The main useEffect will detect agentId !== lastFetchedAgentId and trigger fetch
            }
        }
        
        prevAgentIdFromUrlRef.current = currentAgentIdFromUrl;
    }, [searchParams, defaultAgentId]);

    // 统一的DataGet effect - 合并 initialized 和 agentId 的Listen
    useEffect(() => {
        // Check是否NeedGetData
        // 移除 agentId && 条件，允许 agentId 为 null 时也触发查询（清除筛选场景）
        const shouldFetch = (
            !isFetchingRef.current && // 不在Get中
            (
                !fetchOnceRef.current || // 首次Get
                (initialized && !hasFetched) || // initialized 变化
                agentId !== lastFetchedAgentId.current // agentId 变化（包括从有值变为null，或从null变为有值）
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
    }, [agentId, initialized, hasFetched]);

    // AUTO-FETCH CLOUD MESSAGES: When on web platform, auto-fetch A2A messages on first entry to agent's chat page
    // This runs after the main data fetch and triggers automatically when agentId is available
    // On web platform, we use user's email as senderId instead of myTwinAgentId
    useEffect(() => {
        // Only auto-fetch on web platform
        if (!isWebPlatform()) {
            return;
        }
        
        // Get user's email for web platform (used as senderId)
        const userInfo = UserStorageManager.getInstance().getUserInfo();
        const userEmail = userInfo?.email || userInfo?.username;
        
        // Need user email and agentId to construct channelId
        if (!userEmail || !agentId) {
            logger.info('[AutoCloudFetch] Waiting for userEmail and agentId:', { userEmail, agentId });
            return;
        }
        
        // Create a unique key for this user+agent combination
        const fetchKey = `${userEmail}~${agentId}`;
        
        // Check if we've already auto-fetched for this combination
        if (hasAutoFetchedCloudRef.current === fetchKey) {
            logger.info('[AutoCloudFetch] Already fetched for this combination, skipping');
            return;
        }
        
        // Mark as fetched for this combination BEFORE async call to prevent double fetch
        hasAutoFetchedCloudRef.current = fetchKey;
        
        // Perform the auto-fetch
        const autoFetchCloudMessages = async () => {
            // On web platform: channelId = userEmail~agentId
            const channelId = cloudChatApi.getChannelId(userEmail, agentId);
            logger.info('[AutoCloudFetch] Auto-fetching A2A messages for channel:', channelId);
            
            try {
                const result = await cloudChatApi.getA2AMessages(channelId, 50);
                logger.info('[AutoCloudFetch] Got result:', result.items?.length || 0, 'messages');
                
                if (result.items && result.items.length > 0) {
                    // Convert A2A messages to local message format
                    // Use message ID for deduplication - avoid duplicates by using stable IDs
                    const messages: Message[] = result.items.map((a2aMsg) => {
                        const textPart = a2aMsg.message?.parts?.find(p => p.type === 'text');
                        const roleMap: Record<string, 'user' | 'assistant' | 'system' | 'agent'> = {
                            'user': 'user',
                            'assistant': 'assistant',
                            'system': 'system',
                            'agent': 'agent',
                        };
                        return {
                            id: a2aMsg.id, // Use the stable ID from server
                            chatId: a2aMsg.channelId,
                            senderId: a2aMsg.senderId,
                            senderName: (a2aMsg.metadata as any)?.senderName || a2aMsg.senderId,
                            role: roleMap[a2aMsg.message?.role || 'user'] || 'user',
                            content: textPart?.text || '',
                            createAt: a2aMsg.timestamp ? new Date(a2aMsg.timestamp).getTime() : Date.now(),
                            status: 'complete' as const,
                            attachments: [],
                        };
                    });
                    
                    // Sort messages by time (oldest first)
                    messages.sort((a, b) => (a.createAt as number) - (b.createAt as number));
                    
                    // Update messages in the message manager (setMessages replaces, so no duplicates)
                    updateMessages(channelId, messages);
                    
                    // If we don't have this chat in the list, create it
                    setChats(prevChats => {
                        if (!prevChats.find(c => c.id === channelId)) {
                            const newChat: Chat = {
                                id: channelId,
                                name: `Chat with ${agentId || 'Agent'}`,
                                type: 'user-agent',
                                members: [
                                    { userId: userEmail || '', name: 'Me', role: 'user' },
                                    { userId: agentId || '', name: 'Agent', role: 'agent' }
                                ],
                                messages: [],
                                unread: 0,
                                lastMsg: messages[messages.length - 1]?.content || '',
                                lastMsgTime: messages[messages.length - 1]?.createAt as number,
                            };
                            // Set this chat as active
                            setActiveChatId(channelId);
                            return [...prevChats, newChat];
                        }
                        return prevChats;
                    });
                    
                    logger.info('[AutoCloudFetch] Updated messages for chat:', channelId, 'count:', messages.length);
                } else {
                    logger.info('[AutoCloudFetch] No messages found for channel:', channelId);
                }
            } catch (error) {
                logger.error('[AutoCloudFetch] Error fetching from cloud:', error);
            }
        };
        
        // Run the auto-fetch
        autoFetchCloudMessages();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [agentId]); // Only depend on agentId - updateMessages is stable via useMessages hook

    // CRITICAL FIX: Update MessageManager with active chat
    // This prevents MessageManager from incrementing unread count for active chat
    useEffect(() => {
        messageManager.setActiveChat(activeChatId);
    }, [activeChatId]);

    // Subscribe to A2A channel for real-time messages on web platform
    useEffect(() => {
        if (!isWebPlatform() || !activeChatId) {
            return;
        }
        
        logger.info('[Chat] Subscribing to A2A channel:', activeChatId);
        subscribeToA2AChannel(activeChatId);
    }, [activeChatId]);

    // --- SSE display streaming (optional; final message stays canonical) ---
    // Tracks the in-flight display stream and its temporary assistant bubble.
    // The persisted assistant message delivered by chatter (WS subscription /
    // local push) REPLACES the temp bubble — SSE is display-progress only.
    const llmStreamRef = useRef<{ chatId: string; tempId: string; abort: AbortController } | null>(null);

    const removeTempStreamBubble = useCallback((chatId: string, tempId: string) => {
        messageManager.setMessages(
            chatId,
            messageManager.getMessages(chatId).filter(m => m.id !== tempId)
        );
    }, []);

    // Replace the temp bubble when the persisted assistant message arrives,
    // on either inbound path (desktop: chat:newMessage, web: a2a:message).
    useEffect(() => {
        const clearOnFinalAssistant = (params: any) => {
            const stream = llmStreamRef.current;
            if (!stream) return;
            const msg = params?.message && params?.chatId !== undefined ? params.message : params;
            const chatId = params?.chatId || msg?.chatId || msg?.channelId;
            if (chatId !== stream.chatId) return;
            const role = msg?.role || msg?.message?.role;
            if (role !== 'assistant' && role !== 'agent') return;
            if (msg?.id === stream.tempId) return;
            logger.info('[Chat] Persisted assistant message arrived — replacing SSE temp bubble');
            stream.abort.abort();
            llmStreamRef.current = null;
            removeTempStreamBubble(stream.chatId, stream.tempId);
        };
        eventBus.on('chat:newMessage', clearOnFinalAssistant);
        eventBus.on('a2a:message', clearOnFinalAssistant);
        return () => {
            eventBus.off('chat:newMessage', clearOnFinalAssistant);
            eventBus.off('a2a:message', clearOnFinalAssistant);
        };
    }, [removeTempStreamBubble]);

    // Listen for incoming A2A messages from AppSync subscription
    useEffect(() => {
        if (!isWebPlatform()) {
            return;
        }
        
        const handleA2AMessage = (a2aMsg: any) => {
            logger.info('[Chat] Received A2A message via subscription:', a2aMsg);
            
            // Only process if it's for the active chat
            if (a2aMsg.channelId !== activeChatId) {
                logger.info('[Chat] A2A message is for different channel, ignoring');
                return;
            }
            
            // Convert A2A message to local message format
            const textPart = a2aMsg.message?.parts?.find((p: any) => p.type === 'text');
            const roleMap: Record<string, 'user' | 'assistant' | 'system' | 'agent'> = {
                'user': 'user',
                'assistant': 'assistant', 
                'system': 'system',
                'agent': 'agent',
            };
            
            const message: Message = {
                id: a2aMsg.id || `a2a_msg_${Date.now()}`,
                chatId: a2aMsg.channelId,
                senderId: a2aMsg.senderId,
                senderName: a2aMsg.senderId,
                role: roleMap[a2aMsg.message?.role || 'assistant'] || 'assistant',
                content: textPart?.text || '',
                createAt: a2aMsg.timestamp ? new Date(a2aMsg.timestamp).getTime() : Date.now(),
                status: 'complete' as const,
                attachments: [],
            };
            
            logger.info('[Chat] Adding A2A message to chat:', message);
            addMessageToChat(a2aMsg.channelId, message);
        };
        
        eventBus.on('a2a:message', handleA2AMessage);
        
        return () => {
            eventBus.off('a2a:message', handleA2AMessage);
        };
    }, [activeChatId, addMessageToChat]);

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
                   // Check if this is an incoming message (not from current user)
                   const senderId = message?.senderId;
                   if (senderId && senderId !== currentUserId) {
                       // Clear unread count for this chat (safety measure, MessageManager should already skip increment)
                       markMessageAsRead(activeChatId);
                   }
               }
        };
        
        eventBus.on('chat:newMessage', handleNewMessage);
        
        return () => {
            eventBus.off('chat:newMessage', handleNewMessage);
        };
    }, [activeChatId, currentUserId, markMessageAsRead]);

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
    // Debounced: collapses rapid calls (KeepAlive reactivation, agentId change, auto-select) into one
    const fetchChatsImmediate = async () => {
        // If已经在Get中，跳过
        if (isFetchingRef.current) {
            return;
        }
        
        // SettingsLoadStatus和锁
        setIsLoading(true);
        isFetchingRef.current = true;
        
        try {
            // Determine which userId to query:
            // 1. If agentId is provided (filter selected), query chats with that specific agent
            // 2. Otherwise query all chats for current user
            const targetUserId = agentId || currentUserId;
            
            if (!targetUserId) {
                logger.error("[fetchChats] No userId available");
                return;
            }
            
            logger.info(`[fetchChats] Querying chats - agentId: ${agentId}, currentUserId: ${currentUserId}, targetUserId: ${targetUserId}`);
            
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
                const response = await unifiedChatService.searchChats(
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

    // Debounced wrapper: collapses multiple fetchChats() calls within 50ms into one
    const fetchChats = () => {
        if (fetchChatsDebounceRef.current) {
            clearTimeout(fetchChatsDebounceRef.current);
        }
        fetchChatsDebounceRef.current = setTimeout(() => {
            fetchChatsDebounceRef.current = null;
            fetchChatsImmediate();
        }, 50);
    };
    
    // GeneralGet聊天Data的Function，使用新的 API，并在GetData后ProcessagentId相关逻辑
    const getChatsAndSetState = async (userId?: string) => {
        if (!userId) {
            logger.error("[getChatsAndSetState] Missing userId");
            return;
        }
        
        try {
            logger.info(`[getChatsAndSetState] Fetching chats for userId: ${userId}`);
            // 使用新的 API Get聊天Data
            const response = await unifiedChatService.getChats(
                userId,
                true // deep Parameter，包含 members 数据
            );
            logger.info(`[getChatsAndSetState] Response success: ${response.success}, data type: ${typeof response.data}`);
            
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
                
                logger.info(`[getChatsAndSetState] Loaded ${chatData.length} chats from database`);
                chatData.forEach((chat, index) => {
                    logger.info(`[getChatsAndSetState] Chat ${index + 1}: id=${chat.id}, name=${chat.name}, members=${chat.members?.map(m => m.userId).join(', ')}`);
                });
                
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
                    // 1. 查找是否存在Include该agentId的聊天
                    const chatWithAgent = chatData.find(chat => 
                        chat.members?.some(member => member.userId === agentId)
                    );
                    
                    if (chatWithAgent) {
                        // 2A. If找到，Settings为活动聊天
                        // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                        setActiveChatIdAndFetchMessages(chatWithAgent.id);
                    } else {
                        // 2B. If没找到，Create新的聊天
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
        const effectiveUserId = currentUserId;
        const effectiveUserName = currentUserName;
        
        // Check是否是和自己聊天
        const isSelfChat = targetAgentId === effectiveUserId;
        
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
        
        const ensureHelloMessage = async (chatId: string, agentName?: string, userName?: string) => {
            if (isWebPlatform()) {
                return;
            }
            if (!chatId || helloInitRef.current.has(chatId)) {
                return;
            }
            helloInitRef.current.add(chatId);
            try {
                const history = await unifiedChatService.getChatMessages({
                    chatId,
                    limit: 1,
                    offset: 0,
                    reverse: true,
                });
                const historyData: any = history.success ? history.data : null;
                const existingMessages = Array.isArray(historyData?.data)
                    ? historyData.data
                    : Array.isArray(historyData)
                        ? historyData
                        : [];
                if (existingMessages.length > 0) {
                    return;
                }
                const helloContent = 'Hello! How can I help you today?';
                const helloMessage: Message = {
                    id: `agent_hello_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
                    chatId,
                    role: 'agent',
                    createAt: Date.now(),
                    senderId: targetAgentId,
                    senderName: agentName || 'Agent',
                    content: helloContent,
                    status: 'sending',
                    attachments: [],
                };
                addMessageToChat(chatId, helloMessage);
                const helloPayload: any = {
                    chatId,
                    senderId: targetAgentId,
                    role: 'agent',
                    content: helloContent,
                    createAt: String(Date.now()),
                    senderName: agentName || 'Agent',
                    status: 'complete',
                    receiverId: effectiveUserId,
                    receiverName: userName || effectiveUserName,
                };
                const sendResp = await unifiedChatService.sendChat(helloPayload);
                if (!sendResp.success) {
                    updateMessage(chatId, helloMessage.id, { status: 'error' as const });
                }
            } catch (error) {
                logger.error('[createChatWithAgent] Failed to send hello message:', error);
            }
        };

        try {
            const receiver_agent = useAgentStore.getState().getAgentById(targetAgentId);
            
            // Create聊天Data（isSelfChat 已经在前面被阻止了，这里不会Execute）
            const chatData = {
                members: [
                    {"userId": effectiveUserId, "role": "user", "name": effectiveUserName},
                    {"userId": targetAgentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                ],
                name: receiver_agent?.card.name || `Chat with ${targetAgentId}`,
                type: 'user-agent',
                agent_id: targetAgentId,  // ✅ Add agent_id
            };
            
            const response = await unifiedChatService.createChat(chatData);
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
                    await ensureHelloMessage(newChat.id, receiver_agent?.card?.name, currentUserName);
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
                    await ensureHelloMessage(existingChat.id, receiver_agent?.card?.name, currentUserName);
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
    }, []);

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
            const response = await unifiedChatService.getChatMessages({
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
            const notificationResponse = await unifiedChatService.getChatNotifications({ 
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
            const response = await unifiedChatService.deleteChat(chatId);
            
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

    // Cloud refresh handler - fetches messages directly from cloud A2A API
    // On web platform, uses user's email as senderId instead of myTwinAgentId
    const handleCloudRefresh = useCallback(async () => {
        logger.info('[handleCloudRefresh] Triggered - fetching A2A messages from cloud');
        
        // Get user's email for web platform
        const userInfo = UserStorageManager.getInstance().getUserInfo();
        const userEmail = userInfo?.email || userInfo?.username;
        
        logger.info('[handleCloudRefresh] activeChatId:', activeChatId, 'userEmail:', userEmail, 'agentId:', agentId);
        
        // Determine channelId - use activeChatId or generate from userEmail and agentId
        let channelId = activeChatId;
        
        if (!channelId && userEmail && agentId) {
            // Generate channelId: userEmail=agentId format for web platform
            channelId = cloudChatApi.getChannelId(userEmail, agentId);
            logger.info('[handleCloudRefresh] Generated channelId:', channelId);
        }
        
        if (!channelId) {
            logger.warn('[handleCloudRefresh] No channelId available');
            message.warning('Please select a chat or filter by agent first');
            return;
        }
        
        try {
            message.loading({ content: 'Fetching messages from cloud...', key: 'cloudRefresh' });
            
            logger.info('[handleCloudRefresh] Calling cloudChatApi.getA2AMessages for channel:', channelId);
            const result = await cloudChatApi.getA2AMessages(channelId, 50);
            
            logger.info('[handleCloudRefresh] Got result:', JSON.stringify(result, null, 2));
            
            if (result.items && result.items.length > 0) {
                message.success({ content: `Found ${result.items.length} messages`, key: 'cloudRefresh' });
                
                // Convert A2A messages to local message format and update
                const messages: Message[] = result.items.map((a2aMsg, index) => {
                    const textPart = a2aMsg.message?.parts?.find(p => p.type === 'text');
                    const roleMap: Record<string, 'user' | 'assistant' | 'system' | 'agent'> = {
                        'user': 'user',
                        'assistant': 'assistant', 
                        'system': 'system',
                        'agent': 'agent',
                    };
                    return {
                        id: a2aMsg.id || `cloud_msg_${Date.now()}_${index}`,
                        chatId: a2aMsg.channelId,
                        senderId: a2aMsg.senderId,
                        senderName: (a2aMsg.metadata as any)?.senderName || a2aMsg.senderId,
                        role: roleMap[a2aMsg.message?.role || 'user'] || 'user',
                        content: textPart?.text || '',
                        createAt: a2aMsg.timestamp ? new Date(a2aMsg.timestamp).getTime() : Date.now(),
                        status: 'complete' as const,
                        attachments: [],
                    };
                });
                
                // Sort messages by time (oldest first)
                messages.sort((a, b) => (a.createAt as number) - (b.createAt as number));
                
                // Update messages in the message manager
                updateMessages(channelId, messages);
                
                // If we don't have this chat in the list, create it
                if (!chats.find(c => c.id === channelId)) {
                    const newChat: Chat = {
                        id: channelId,
                        name: `Chat with ${agentId || 'Agent'}`,
                        type: 'user-agent',
                        members: [
                            { userId: userEmail || '', name: 'Me', role: 'user' },
                            { userId: agentId || '', name: 'Agent', role: 'agent' }
                        ],
                        messages: [],
                        unread: 0,
                        lastMsg: messages[messages.length - 1]?.content || '',
                        lastMsgTime: messages[messages.length - 1]?.createAt as number,
                    };
                    setChats(prev => [...prev, newChat]);
                    setActiveChatId(channelId);
                }
                
                logger.info('[handleCloudRefresh] Updated messages for chat:', channelId, 'count:', messages.length);
            } else {
                message.info({ content: 'No messages found in cloud', key: 'cloudRefresh' });
                logger.info('[handleCloudRefresh] No messages found for channel:', channelId);
            }
        } catch (error) {
            logger.error('[handleCloudRefresh] Error fetching from cloud:', error);
            message.error({ content: `Error: ${error}`, key: 'cloudRefresh' });
        }
    }, [activeChatId, agentId, updateMessages, chats]);

    // handleMessageSend SendMessage时加 log
    // Open an SSE display stream for the reply and render it in a temporary
    // assistant bubble. Best-effort: any failure silently leaves the buffered
    // A2A-only flow intact.
    const startDisplayStream = useCallback(async (chatId: string, receiverId?: string, receiverName?: string) => {
        try {
            const config = await fetchLlmStreamConfig();
            if (!config.enabled) return;

            // One display stream at a time — drop any stale temp bubble.
            const prior = llmStreamRef.current;
            if (prior) {
                prior.abort.abort();
                llmStreamRef.current = null;
                removeTempStreamBubble(prior.chatId, prior.tempId);
            }

            // Recent history (includes the just-sent user message) as
            // OpenAI-style messages for the display completion.
            const history = messageManager.getMessages(chatId)
                .filter(m => (m.role === 'user' || m.role === 'assistant' || m.role === 'agent')
                    && typeof m.content === 'string' && m.content)
                .slice(-10)
                .map(m => ({ role: m.role === 'user' ? 'user' : 'assistant', content: m.content }));
            if (history.length === 0 || history[history.length - 1].role !== 'user') return;

            const requestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
            const tempId = `llm_stream_${requestId}`;
            const abort = new AbortController();
            llmStreamRef.current = { chatId, tempId, abort };
            let streamed = '';

            addMessageToChat(chatId, {
                id: tempId,
                chatId,
                role: 'assistant',
                content: '',
                createAt: Date.now(),
                status: 'incomplete',
                senderId: receiverId,
                senderName: receiverName,
            } as Message);

            await streamChatCompletion({
                config,
                messages: history,
                requestId,
                signal: abort.signal,
                onDelta: (text) => {
                    if (llmStreamRef.current?.tempId !== tempId) return;
                    streamed += text;
                    updateMessage(chatId, tempId, { content: streamed });
                },
                onDone: () => {
                    // Keep the bubble (and llmStreamRef) — the persisted A2A
                    // assistant message replaces it via clearOnFinalAssistant.
                    if (llmStreamRef.current?.tempId === tempId && streamed) {
                        updateMessage(chatId, tempId, { status: 'complete' });
                    }
                },
                onError: (err) => {
                    logger.warn(`[Chat] SSE display stream failed: ${err}`);
                    if (llmStreamRef.current?.tempId === tempId) {
                        llmStreamRef.current = null;
                        if (!streamed) {
                            removeTempStreamBubble(chatId, tempId);
                        } else {
                            updateMessage(chatId, tempId, { status: 'complete' });
                        }
                    }
                },
            });
        } catch (err) {
            logger.warn(`[Chat] Display stream skipped: ${err}`);
        }
    }, [addMessageToChat, updateMessage, removeTempStreamBubble]);

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

        // Determine sender info based on platform
        let senderId: string | undefined;
        let senderName: string | undefined;
        
        if (isWebPlatform()) {
            // On web platform, use user's email as senderId
            const userInfo = UserStorageManager.getInstance().getUserInfo();
            senderId = userInfo?.email || userInfo?.username;
            senderName = userInfo?.name || userInfo?.email || 'User';
            if (!senderId) {
                logger.error('[handleMessageSend] No user email available on web platform');
                return;
            }
        } else {
            // On desktop platform, use current user id
            senderId = currentUserId;
            senderName = currentUserName;
            if (!senderId || !senderName) return;
        }

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
            
            const response = await unifiedChatService.sendChat(messageData);
            if (!response.success) {
                logger.error('Failed to send message:', response.error);
                // UpdateMessageStatus为Error
                updateMessage(activeChatId, userMessage.id, { status: 'error' as const });
                return;
            }

            // Check if backend returned a new chatId (when chat was auto-created)
            const responseData = response.data as any;

            // Kick off optional SSE display streaming (fire-and-forget).
            // The canonical assistant message still arrives via the A2A
            // subscription and replaces the streamed bubble.
            const streamChatId = responseData?.realChatId || activeChatId;
            void startDisplayStream(streamChatId, receiverId, receiverName);
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
    }, [activeChatId, chats, addMessageToChat, allMessages, updateMessage, currentUserId, currentUserName, agentId, startDisplayStream]);
    
    const currentChat = (!activeChatId || !chats || chats.length === 0)
        ? null
        : chats.find((c) => c.id === activeChatId) || null;

    // Compute left panel header agentId: DisplayWhen前Filter的 agent 的视频
    // 视频不跟随选中的 chat 改变，只跟随Filter器（agentId Parameter）改变
    const headerAgentId = useMemo(() => {
        // Priority：URL agentId（Filter器Select）> fallback
        if (agentId) {
            return agentId;
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
    }, [agentId, agents, chats.length]);
    
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
    const filteredChats = useMemo(() => {
        if (!agentId) {
            // No filter: return all chats
            logger.info(`[filteredChats] No filter - returning all ${chats.length} chats`);
            return chats;
        }
        
        // Filter chats that include the selected agent
        const filtered = chats.filter(chat => 
            chat.members?.some(member => member.userId === agentId)
        );
        logger.info(`[filteredChats] Filtered by agentId=${agentId}: ${filtered.length}/${chats.length} chats`);
        return filtered;
    }, [chats, agentId]);

    // Desktop fallback: if filter selects an agent but no chats exist yet, auto-create one
    useEffect(() => {
        if (isWebPlatform()) {
            return;
        }
        if (!effectsCompletedRef.current || !agentId) {
            return;
        }
        if (filteredChats.length > 0) {
            return;
        }
        if (autoCreateChatRef.current.has(agentId)) {
            return;
        }
        autoCreateChatRef.current.add(agentId);
        createChatWithAgent(agentId);
    }, [agentId, filteredChats.length]);
    
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
        
        // Scenario 1: agentId changed - select first chat in filtered list
        // NOTE: Only set activeChatId here, do NOT call setActiveChatIdAndFetchMessages.
        // fetchChats() → getChatsAndSetState() already handles the full flow including
        // chat selection + message fetching. Calling it again here would create duplicate
        // get_chat_messages + get_chat_notifications requests that pile up on the serial
        // backend GraphQL handler and cause timeout errors.
        if (normalizedAgentId !== lastAutoSelectAgentId.current) {
            const firstChatId = filteredChats[0].id;
            logger.info(`[Auto-select] Agent filter changed from ${lastAutoSelectAgentId.current || 'none'} to ${normalizedAgentId || 'default'}, selecting first chat: ${firstChatId}`);
            if (activeChatId !== firstChatId) {
                setActiveChatId(firstChatId);
            }
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
                onCloudRefresh={handleCloudRefresh}
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
            // Filter out current user from members
            const filteredMembers = chat.members.filter(m => m.userId !== currentUserId);
            
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
    }, [agentId, currentUserId, t]);

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
