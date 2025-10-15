import React, { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ChatList from './components/ChatList';
const ChatDetail = lazy(() => import('./components/ChatDetail'));
import { Chat, Message, Attachment } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
const ChatNotification = lazy(() => import('./components/ChatNotification'));
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useAppDataStore } from '@/stores/appDataStore';
import { useAgentStore } from '@/stores/agentStore';
import { useChatNotifications, NOTIF_PAGE_SIZE } from './hooks/useChatNotifications';
import { useMessages } from './hooks/useMessages';
import { notificationManager } from './managers/NotificationManager';
import type { ChatNotificationItem } from './managers/NotificationManager';
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
    const myTwinAgent = useAgentStore(state => state.getMyTwinAgent());
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

    // 使用全局通知管理器和消息管理器
    const { hasNew, markAsRead } = useChatNotifications(activeChatId || '');
    const { allMessages, unreadCounts, markAsRead: markMessageAsRead, updateMessages, addMessageToChat, updateMessage } = useMessages();

    // 新增独立的 loading 状态
    const [isInitialLoadingNotifications, setIsInitialLoadingNotifications] = useState(false);

    // 添加日志，记录组件挂载和关键状态变化
    useEffect(() => {
        logger.debug("Chat page mounted. agentId:", agentId, "initialized:", initialized, "myTwinAgentId:", myTwinAgentId);
        
        // 确保我们至少尝试获取一次聊天数据，即使initialized为false
        if (!fetchOnceRef.current && agentId) {
            logger.debug("First render with agentId, forcing fetch");
            fetchOnceRef.current = true;
            fetchChats();
        }
        
        // 组件挂载完成后设置标志
        setTimeout(() => {
            effectsCompletedRef.current = true;
        }, 100);
        
        return () => {
            logger.debug("Chat page unmounted");
            // 重置所有状态
            effectsCompletedRef.current = false;
            isFetchingRef.current = false;
            isCreatingChatRef.current = false;
        };
    }, []);
    
    // 监听initialized变化
    useEffect(() => {
        // 如果还没完成初始化效果，跳过
        if (!effectsCompletedRef.current) return;
        
        logger.debug("initialized changed:", initialized, "previous:", prevInitialized.current);
        prevInitialized.current = initialized;
        
        if (initialized && !hasFetched) {
            logger.debug("initialized became true, fetching chats");
            setHasFetched(true);
            fetchChats();
        }
    }, [initialized, hasFetched]);
    
    // 监听agentId变化
    useEffect(() => {
        // 如果还没完成初始化效果，跳过
        if (!effectsCompletedRef.current) return;
        
        logger.debug("agentId changed:", agentId);
        if (agentId && agentId !== lastFetchedAgentId.current) {
            lastFetchedAgentId.current = agentId;
            if (chats.length > 0) {
                // 如果已经有聊天列表，尝试找到对应聊天或创建新聊天
                handleAgentIdChange(agentId);
            } else if (!isFetchingRef.current) {
                // 如果没有聊天列表且不在加载中，尝试加载聊天
                logger.debug("agentId changed but no chats, fetching");
                fetchChats();
            }
        }
    }, [agentId, chats.length]);

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
        logger.debug("Executing fetchChats function");
        
        // 如果已经在获取中，跳过
        if (isFetchingRef.current) {
            logger.debug("Already fetching chats, skip fetchChats");
            return;
        }
        
        // 设置加载状态和锁
        setIsLoading(true);
        isFetchingRef.current = true;
        
        try {
            // 获取 myTwinAgentId
            let currentTwinAgentId = myTwinAgentId;
            if (!currentTwinAgentId) {
                const myTwinAgent = useAgentStore.getState().getMyTwinAgent();
                currentTwinAgentId = myTwinAgent?.card?.id;
                
                if (!currentTwinAgentId) {
                    logger.error("Cannot find MyTwinAgent");
                    return;
                }
            }
            
            // 拉取聊天列表
            await getChatsAndSetState(currentTwinAgentId);
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
        
        logger.debug("[handleAgentIdChange] Processing targetAgentId:", targetAgentId);
        
        // 查找是否存在包含该agentId的聊天
        const chatWithAgent = chats.find(chat => 
            chat.members?.some(member => member.userId === targetAgentId)
        );
        
        if (chatWithAgent) {
            // 如果找到，设置为活动聊天并获取消息
            logger.debug("[handleAgentIdChange] Found existing chat:", chatWithAgent.id);
            // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
            setActiveChatIdAndFetchMessages(chatWithAgent.id);
        } else {
            // 如果没找到，创建新的聊天
            logger.debug("[handleAgentIdChange] No existing chat found, creating new one");
            await createChatWithAgent(targetAgentId);
        }
    };
    
    // 页面每次显示都拉取聊天（无论 agentId 是否存在）
    useEffect(() => {
        logger.debug("Chat page mounted or shown. agentId:", agentId, "initialized:", initialized, "myTwinAgentId:", myTwinAgentId);

        // 只要页面显示就拉取聊天（无论 agentId 是否存在）
        fetchChats();

        setTimeout(() => {
            effectsCompletedRef.current = true;
        }, 100);

        return () => {
            logger.debug("Chat page unmounted");
            effectsCompletedRef.current = false;
            isFetchingRef.current = false;
            isCreatingChatRef.current = false;
        };
    }, []);

    // 通用获取聊天数据的函数，使用新的 API，并在获取数据后处理agentId相关逻辑
    const getChatsAndSetState = async (userId?: string) => {
        if (!userId) {
            logger.error("[getChatsAndSetState] Missing userId");
            return;
        }
        
        try {
            logger.debug("[getChatsAndSetState] Getting chats for userId:", userId);
            // 使用新的 API 获取聊天数据
            const response = await get_ipc_api().chatApi.getChats(
                userId,
                false // deep 参数，按需可调整
            );
            console.log("[getChatsAndSetState] Got response:", response.data);
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
                
                logger.debug("[getChatsAndSetState] Parsed chat data, count:", chatData.length);
                // 这里直接对 lastMsg 做 display 解析
                setChats(chatData.map(chat => ({
                    ...chat,
                    lastMsg: getDisplayMsg(chat.lastMsg, t),
                })));
                
                // 处理agentId相关逻辑
                if (agentId) {
                    logger.debug("[getChatsAndSetState] Processing agentId:", agentId);
                    
                    // 1. 查找是否存在包含该agentId的聊天
                    const chatWithAgent = chatData.find(chat => 
                        chat.members?.some(member => member.userId === agentId)
                    );
                    
                    if (chatWithAgent) {
                        // 2A. 如果找到，设置为活动聊天
                        logger.debug("[getChatsAndSetState] Found existing chat with agent:", chatWithAgent.id);
                        // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                        setActiveChatIdAndFetchMessages(chatWithAgent.id);
                    } else {
                        // 2B. 如果没找到，创建新的聊天
                        logger.debug("[getChatsAndSetState] No existing chat found with agent, creating new one");
                        // 检查是否已经在创建聊天中
                        if (!isCreatingChatRef.current) {
                            await createChatWithAgent(agentId);
                        }
                    }
                } else if (chatData.length > 0) {
                    // 如果没有agentId，但有聊天列表，选择第一个聊天
                    const selectedChatId = chatData[0].id;
                    logger.debug("[getChatsAndSetState] No agentId, selecting first chat:", selectedChatId);
                    // 直接调用setActiveChatIdAndFetchMessages，避免重复调用handleChatSelect
                    setActiveChatIdAndFetchMessages(selectedChatId);
                }
                
                logger.debug('Chats loaded successfully:', chatData.length);
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
        if (!myTwinAgentId) {
            logger.error("[createChatWithAgent] Missing myTwinAgentId");
            return;
        }
        
        // 如果已经在创建聊天中，跳过
        if (isCreatingChatRef.current) {
            logger.debug("[createChatWithAgent] Already creating chat, skipping");
            return;
        }
        
        // 设置创建聊天锁
        isCreatingChatRef.current = true;
        
        try {
            const my_twin_agent = useAgentStore.getState().getAgentById(myTwinAgentId);
            const receiver_agent = useAgentStore.getState().getAgentById(targetAgentId);
            
            // 创建聊天数据
            const chatData = {
                members: [
                    {"userId": myTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"},
                    {"userId": targetAgentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                ],
                name: receiver_agent?.card.name || `Chat with ${targetAgentId}`,
                type: 'user-agent',
            };
            
            logger.debug('[createChatWithAgent] Creating chat for agent:', targetAgentId);
            const response = await get_ipc_api().chatApi.createChat(chatData);
            const resp: any = response;
            
            // Check if IPC call succeeded
            if (resp.success && resp.data) {
                // Check if backend operation succeeded (new chat created)
                if (resp.data.success && resp.data.data) {
                    // 提取新聊天数据
                    const newChat = { ...resp.data.data, name: resp.data.data.name || chatData.name } as Chat;
                    logger.debug('[createChatWithAgent] New chat created:', newChat.id);
                    
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
                    logger.debug('[createChatWithAgent] Chat already exists, using existing chat:', resp.data.id);
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

    const handleFilterChange = useCallback((filters: Record<string, any>) => {
        logger.debug('Filter changed:', filters);
    }, []);

    // 新增：设置activeChatId并获取消息的函数，避免重复调用handleChatSelect
    const setActiveChatIdAndFetchMessages = useCallback((chatId: string) => {
        // 如果已经是当前活动聊天，不需要重复获取
        if (chatId === activeChatId) {
            logger.debug(`[setActiveChatIdAndFetchMessages] Chat ${chatId} already active, skipping`);
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
                logger.debug(`Loaded ${messages.length} messages for chat ${chatId}`);
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
                let chatNotificationItems: ChatNotificationItem[] = [];
                const dataArray = (notificationResponse.data as any).data;
                if (Array.isArray(dataArray)) {
                    dataArray.reverse().forEach((item: any, index: number) => {
                        notificationManager.addNotification(chatId, item);
                    })
                }

                logger.debug(`Loaded ${chatNotificationItems.length} notifications for chat ${chatId}`);
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
            // 调用 API 删除聊天
            const response = await get_ipc_api().chatApi.deleteChat(chatId);
            
            if (response.success) {
                // 本地更新 UI
                const updatedChats = chats.filter(c => c.id !== chatId);
                setChats(updatedChats);

                // 如果删除的是当前聊天，则切换到第一个聊天
                if (activeChatId === chatId) {
                    const nextChatId = updatedChats[0]?.id || null;
                    if (nextChatId) {
                        setActiveChatIdAndFetchMessages(nextChatId);
                    } else {
                        setActiveChatId(null);
                    }
                }
                
                logger.debug('Chat deleted successfully:', chatId);
            } else {
                logger.error('Failed to delete chat:', response.error);
                setError(`Failed to delete chat: ${response.error?.message || 'Unknown error'}`);
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
            logger.debug("[sendChat] response:", JSON.stringify(response.data));
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

    // renderListContent 加 log
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
                currentAgentId={agentId || undefined}
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
    );
};

export default ChatPage;
