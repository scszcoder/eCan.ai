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
    const agentId = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    const agents = useAgentStore(state => state.agents);
    const getMyTwinAgent = useAgentStore(state => state.getMyTwinAgent);
    
    // 直接从 store 获取 myTwinAgent，确保始终是最新的
    const myTwinAgent = getMyTwinAgent();
    const myTwinAgentId = myTwinAgent?.card?.id;
    
    const initialized = useAppDataStore(state => state.initialized);

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
    const allChatsCache = useRef<Chat[]>([]); // 缓存所有聊天（无搜索时）

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
            
            // agents 加载完成后，设置标志
            setTimeout(() => {
                effectsCompletedRef.current = true;
            }, 100);
        };
        
        initializeComponent();
        
        return () => {
            effectsCompletedRef.current = false;
            isFetchingRef.current = false;
            isCreatingChatRef.current = false;
        };
    }, [username]);
    
    // 等待 myTwinAgentId 可用后再调用 fetchChats
    useEffect(() => {
        if (myTwinAgentId && !fetchOnceRef.current) {
            fetchOnceRef.current = true;
            fetchChats();
        }
    }, [myTwinAgentId]);
    
    // 监听initialized变化
    useEffect(() => {
        if (!effectsCompletedRef.current) return;
        
        prevInitialized.current = initialized;
        
        if (initialized && !hasFetched) {
            setHasFetched(true);
            fetchChats();
        }
    }, [initialized, hasFetched]);
    
    // 监听agentId变化
    useEffect(() => {
        if (!effectsCompletedRef.current) return;
        
        // 当 agentId 改变时（包括从有值变为 null），重新获取聊天
        if (agentId !== lastFetchedAgentId.current) {
            logger.info(`[Chat] agentId changed from ${lastFetchedAgentId.current} to ${agentId}, fetching chats...`);
            lastFetchedAgentId.current = agentId || undefined;
            
            if (!isFetchingRef.current) {
                // 延迟调用 fetchChats，确保它已经定义
                setTimeout(() => {
                    fetchChats();
                }, 0);
            }
        }
    }, [agentId]);

    // 同步消息管理器中的消息到聊天列表
    useEffect(() => {
        setChats(prevChats => {
            // console.log('[setChats] prevChats:', prevChats);
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
        // console.log('[setChats] newChats:', chats);
    }, [allMessages, unreadCounts]);

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
            // 确定要查询的用户ID：
            // 1. 如果有 agentId 参数（过滤器选择），使用该 agentId
            // 2. 否则使用 myTwinAgentId（默认显示 MyTwin 参与的聊天）
            // 注意：从 store 重新获取最新的 myTwinAgentId，避免闭包问题
            const currentMyTwinAgent = useAgentStore.getState().getMyTwinAgent();
            const currentMyTwinAgentId = currentMyTwinAgent?.card?.id;
            const targetUserId = agentId || currentMyTwinAgentId;
            
            if (!targetUserId) {
                logger.error("[fetchChats] No userId available (agentId or myTwinAgentId)");
                return;
            }
            
            // 使用 ref 获取最新的搜索文本
            const currentSearchText = searchTextRef.current;
            logger.info(`[fetchChats] Fetching chats for userId: ${targetUserId} (agentId: ${agentId}, myTwinAgentId: ${myTwinAgentId}), searchText: "${currentSearchText}"`);
            
            // 如果清空搜索且有缓存，直接使用缓存（避免闪烁）
            if ((!currentSearchText || currentSearchText.trim() === '') && allChatsCache.current.length > 0) {
                logger.info(`[fetchChats] Using cached chats (${allChatsCache.current.length} items)`);
                setChats(prevChats => {
                    // 如果缓存和当前数据相同，不更新（避免重新渲染）
                    if (prevChats === allChatsCache.current) {
                        return prevChats;
                    }
                    return allChatsCache.current;
                });
                return;
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
                    
                    logger.info(`[fetchChats] Found ${chatData.length} chats matching search`);
                    
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
                    
                    // 1. 查找是否存在包含该agentId的聊天
                    const chatWithAgent = chatData.find(chat => 
                        chat.members?.some(member => member.userId === agentId)
                    );
                    
                    if (chatWithAgent) {
                        // 2A. 如果找到，设置为活动聊天
                        // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                        setActiveChatIdAndFetchMessages(chatWithAgent.id);
                    } else {
                        // 2B. 如果没找到，创建新的聊天
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
        
        // 如果已经在创建聊天中，跳过
        if (isCreatingChatRef.current) {
            return;
        }
        
        // 设置创建聊天锁
        isCreatingChatRef.current = true;
        
        try {
            const my_twin_agent = useAgentStore.getState().getAgentById(currentMyTwinAgentId);
            const receiver_agent = useAgentStore.getState().getAgentById(targetAgentId);
            
            // 检查是否是和自己聊天（targetAgentId === currentMyTwinAgentId）
            const isSelfChat = targetAgentId === currentMyTwinAgentId;
            
            // 创建聊天数据
            const chatData = {
                members: isSelfChat 
                    ? [
                        // 和自己聊天时，只添加一个成员记录
                        {"userId": currentMyTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"}
                      ]
                    : [
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
        // 如果已经是当前活动聊天，不需要重复获取
        if (chatId === activeChatId) {
            return;
        }
        
        // 更新最后选择的聊天ID
        lastSelectedChatIdRef.current = chatId;
        // 设置活动聊天ID
        setActiveChatId(chatId);
        // 获取消息
        handleChatSelect(chatId);
    }, [activeChatId]);

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
            const systemAgents = agents.filter(a => a.card?.id?.startsWith('system_') || a.id?.startsWith('system_'));
            if (systemAgents.length > 0) {
                const randomIndex = Math.floor(Math.random() * systemAgents.length);
                const fallbackId = systemAgents[randomIndex].card?.id || systemAgents[randomIndex].id;
                logger.debug(`[headerAgentId] Using random system agent: ${fallbackId}`);
                return fallbackId;
            }
        }
        
        // 最终 fallback
        const fallbackId = agents && agents.length > 0 ? agents[0].card?.id || agents[0].id : undefined;
        logger.debug(`[headerAgentId] Using final fallback: ${fallbackId}`);
        return fallbackId;
    }, [agentId, myTwinAgentId, agents, chats.length]);
    
    // 处理搜索
    const handleSearch = useCallback((text: string) => {
        setSearchText(text);
        searchTextRef.current = text;
        
        // 如果清空搜索，立即执行（不延迟）
        if (!text || text.trim() === '') {
            if (effectsCompletedRef.current) {
                fetchChats();
            }
        } else {
            // 有搜索文本时，延迟调用以实现防抖
            setTimeout(() => {
                if (effectsCompletedRef.current) {
                    fetchChats();
                }
            }, 300);
        }
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

    const renderListContent = () => {
        // console.log('[renderListContent] chats:', chats);
        return (
            <ChatList
                chats={chats}
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

    const renderDetailsContent = () => (
        <Suspense fallback={<div className="loading-container">{t('common.loading')}</div>}>
            <ChatDetail 
                chatId={activeChatId} 
                chats={chats}
                onSend={handleMessageSend}
                setIsInitialLoading={setIsInitialLoading}
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
                detailsTitle={currentChat ? currentChat.name : t('pages.chat.chatDetails')}
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
