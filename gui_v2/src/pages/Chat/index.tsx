import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { Chat, Message, Attachment, Content } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
import AgentNotify from './components/AgentNotify';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useAppDataStore } from '@/stores/appDataStore';
import { useNotifications } from './hooks/useNotifications';
import { useMessages } from './hooks/useMessages';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';
    const myTwinAgent = useAppDataStore(state => state.myTwinAgent());
    const myTwinAgentId = myTwinAgent?.card?.id;
    const initialized = useAppDataStore(state => state.initialized);

    const [chats, setChats] = useState<Chat[]>([]);
    const [activeChatId, setActiveChatId] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hasFetched, setHasFetched] = useState(false);
    const lastFetchedAgentId = useRef<string | undefined>();
    const prevInitialized = useRef(initialized);
    const fetchOnceRef = useRef(false);

    // 使用全局通知管理器和消息管理器
    const { hasNew, markAsRead } = useNotifications();
    const { allMessages, unreadCounts, markAsRead: markMessageAsRead, updateMessages, addMessageToChat, updateMessage } = useMessages();

    // 添加日志，记录组件挂载和关键状态变化
    useEffect(() => {
        logger.debug("Chat page mounted. agentId:", agentId, "initialized:", initialized, "myTwinAgentId:", myTwinAgentId);
        
        // 确保我们至少尝试获取一次聊天数据，即使initialized为false
        if (!fetchOnceRef.current && agentId) {
            logger.debug("First render with agentId, forcing fetch");
            fetchOnceRef.current = true;
            fetchChats();
        }
        
        return () => {
            logger.debug("Chat page unmounted");
        };
    }, []);
    
    // 监听initialized变化
    useEffect(() => {
        logger.debug("initialized changed:", initialized, "previous:", prevInitialized.current);
        prevInitialized.current = initialized;
        
        if (initialized && !hasFetched) {
            logger.debug("initialized became true, fetching chats");
            setHasFetched(true);
            fetchChats();
        }
    }, [initialized]);
    
    // 监听agentId变化
    useEffect(() => {
        logger.debug("agentId changed:", agentId);
        if (agentId && agentId !== lastFetchedAgentId.current) {
            lastFetchedAgentId.current = agentId;
            if (chats.length > 0) {
                // 如果已经有聊天列表，尝试找到对应聊天或创建新聊天
                handleAgentIdChange(agentId);
            } else if (!isLoading) {
                // 如果没有聊天列表且不在加载中，尝试加载聊天
                logger.debug("agentId changed but no chats, fetching");
                fetchChats();
            }
        }
    }, [agentId]);

    // 同步消息管理器中的消息到聊天列表
    useEffect(() => {
        setChats(prevChats => {
            return prevChats.map(chat => {
                const messages = allMessages.get(chat.id) || [];
                const unreadCount = unreadCounts.get(chat.id) || 0;
                
                // 更新最后一条消息信息
                const lastMessage = messages[messages.length - 1];
                const lastMsg = lastMessage 
                    ? (typeof lastMessage.content === 'string' ? lastMessage.content : JSON.stringify(lastMessage.content))
                    : chat.lastMsg;
                const lastMsgTime = lastMessage?.createAt || chat.lastMsgTime;
                
                return {
                    ...chat,
                    messages,
                    unread: unreadCount,
                    lastMsg,
                    lastMsgTime,
                };
            });
        });
    }, [allMessages, unreadCounts]);

    // 新增：监听 activeChatId，自动拉取消息并更新 ChatDetail（避免死循环）
    useEffect(() => {
        if (!activeChatId) return;
        handleChatSelect(activeChatId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeChatId]);

    // 抽取获取聊天的函数，可以在多个地方调用
    const fetchChats = async () => {
        logger.debug("Executing fetchChats function");
        if (isLoading) {
            logger.debug("Already loading, skip fetchChats");
            return;
        }
        
        setIsLoading(true);
        
        // 等待 myTwinAgentId 可用，最多重试 10 次
        let currentTwinAgentId = myTwinAgentId;
        if (!currentTwinAgentId) {
            logger.debug("myTwinAgentId not available, trying to get it");
            let retry = 0;
            while (retry < 10) {
                const myTwinAgent = useAppDataStore.getState().myTwinAgent();
                currentTwinAgentId = myTwinAgent?.card?.id;
                if (currentTwinAgentId) {
                    logger.debug("Got myTwinAgentId after retry:", currentTwinAgentId);
                    break;
                }
                await new Promise(res => setTimeout(res, 100)); // 100ms
                retry++;
            }
        }
        
        if (!currentTwinAgentId) {
            logger.error("Failed to get myTwinAgentId after retries");
            setIsLoading(false);
            return;
        }
        
        // 拉取聊天列表
        await getChatsAndSetState(currentTwinAgentId);
        setIsLoading(false);
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
            // 如果找到，设置为活动聊天
            logger.debug("[handleAgentIdChange] Found existing chat:", chatWithAgent.id);
            setActiveChatId(chatWithAgent.id);
            handleChatSelect(chatWithAgent.id);
        } else {
            // 如果没找到，创建新的聊天
            logger.debug("[handleAgentIdChange] No existing chat found, creating new one");
            await createChatWithAgent(targetAgentId);
        }
    };
    
    // 页面每次显示都拉取聊天
    useEffect(() => {
        if (!initialized && fetchOnceRef.current) {
            logger.debug("Skip fetchChats in main useEffect since we already tried once");
            return;
        }
        
        logger.debug("Main useEffect executing, initialized:", initialized);
        if (!initialized) return;
        
        let cancelled = false;
        setIsLoading(true);

        const fetchChatsAsync = async () => {
            await fetchChats();
            if (cancelled) return;
        };

        fetchChatsAsync();
        return () => { cancelled = true; };
    }, [initialized]);

    // 通用获取聊天数据的函数，使用新的 API，并在获取数据后处理agentId相关逻辑
    const getChatsAndSetState = async (userId?: string) => {
        try {
            logger.debug("[getChatsAndSetState] Getting chats for userId:", userId);
            // 使用新的 API 获取聊天数据
            const response = await get_ipc_api().chat.getChats(
                userId || '',
                false // deep 参数，按需可调整
            );
            logger.debug("[getChatsAndSetState] Got response:", response.success);
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
                setChats(chatData);
                
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
                        setActiveChatId(chatWithAgent.id);
                        handleChatSelect(chatWithAgent.id);
                    } else {
                        // 2B. 如果没找到，创建新的聊天
                        logger.debug("[getChatsAndSetState] No existing chat found with agent, creating new one");
                        await createChatWithAgent(agentId);
                    }
                } else if (chatData.length > 0) {
                    // 如果没有agentId，但有聊天列表，选择第一个聊天
                    const selectedChatId = chatData[0].id;
                    logger.debug("[getChatsAndSetState] No agentId, selecting first chat:", selectedChatId);
                    setActiveChatId(selectedChatId);
                    handleChatSelect(selectedChatId);
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
        } finally {
            setIsLoading(false);
        }
    };
    
    // 创建和Agent的聊天的辅助函数
    const createChatWithAgent = async (targetAgentId: string) => {
        if (!myTwinAgentId) {
            logger.error("[createChatWithAgent] Missing myTwinAgentId");
            return;
        }
        
        const my_twin_agent = useAppDataStore.getState().getAgentById(myTwinAgentId);
        const receiver_agent = useAppDataStore.getState().getAgentById(targetAgentId);
        
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
        try {
            const response = await get_ipc_api().chat.createChat(chatData);
            const resp: any = response;
            
            if (resp.success && resp.data && resp.data.data) {
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
                
                // 设置为活动聊天
                setActiveChatId(newChat.id);
                handleChatSelect(newChat.id);
            } else {
                logger.error('[createChatWithAgent] Failed to create chat:', resp.error);
            }
        } catch (error) {
            logger.error('[createChatWithAgent] Error creating chat:', error);
        }
    };

    // 页面初始化
    useEffect(() => {
        // 只要 initialized 变 true，重置 hasFetched
        if (initialized) setHasFetched(false);
    }, [initialized]);

    const handleFilterChange = (filters: Record<string, any>) => {
        logger.debug('Filter changed:', filters);
    };

    // 点击chat时
    const handleChatSelect = async (chatId: string) => {
        // 标记为已读
        markMessageAsRead(chatId);
        setActiveChatId(chatId);
        
        // 获取最新消息
        try {
            const response = await get_ipc_api().chat.getChatMessages({ chatId });
            console.log("[chat message] result>>>", response.data)
            if (response.success && response.data) {
                let messages: Message[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Message[]
                        : [];
                
                // 确保每个消息都有唯一的 ID
                messages = messages.map((message, index) => ({
                    ...message,
                    id: message.id || `server_msg_${Date.now()}_${index}_${Math.random().toString(36).substr(2, 9)}`
                }));
                
                // 使用消息管理器更新消息
                updateMessages(chatId, messages);
            } else {
                // 失败时清空消息并可选提示
                updateMessages(chatId, []);
                if (response.error) {
                    setError(typeof response.error === 'string' ? response.error : response.error.message || 'Failed to load messages');
                }
            }
        } catch (err) {
            logger.error('Error fetching chat messages:', err);
            updateMessages(chatId, []);
            setError('Error fetching chat messages');
        }
    };

    const handleChatDelete = async (chatId: string) => {
        try {
            // 调用 API 删除聊天
            const response = await get_ipc_api().chat.deleteChat(chatId);
            
            if (response.success) {
                // 本地更新 UI
                const updatedChats = chats.filter(c => c.id !== chatId);
                setChats(updatedChats);

                // 如果删除的是当前聊天，则切换到第一个聊天
                if (activeChatId === chatId) {
                    setActiveChatId(updatedChats[0]?.id || null);
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

    const handleMessageSend = async (content: string, attachments: Attachment[]) => {
        console.log('[handleMessageSend] attachments:', attachments);
        if (!activeChatId) {
            logger.error('No activeChatId!!!');
            return;
        }

        const chat = chats.find(c => c.id === activeChatId);
        if (!chat) return;

        if (!myTwinAgentId) return;
        const my_twin_agent = useAppDataStore.getState().getAgentById(myTwinAgentId);
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
            content: content,
            status: 'sending',
            attachments: safeAttachments
        };

        // 先乐观地更新 UI - 使用消息管理器
        addMessageToChat(activeChatId, userMessage);

        try {
            // 使用新的 API 发送消息
            const messageData = {
                chatId: activeChatId,
                senderId, // 明确为 string
                role: "user",
                content: content,
                createAt: String(Date.now()),
                senderName,
                status: 'sending',
                attachments: safeAttachments as any
            };
            
            const response = await get_ipc_api().chat.sendChat(messageData);
            console.log(response.data)
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
    };
    
    const currentChat = (!activeChatId || !chats || chats.length === 0)
        ? null
        : chats.find((c) => c.id === activeChatId) || null;

    const renderListContent = () => (
        <ChatList
            chats={chats}
            activeChatId={activeChatId}
            onChatSelect={handleChatSelect}
            onChatDelete={handleChatDelete}
            onChatPin={handleChatPin}
            onChatMute={handleChatMute}
            onFilterChange={handleFilterChange}
        />
    );

    const renderDetailsContent = () => (
        <ChatDetail 
            chatId={activeChatId} 
            chats={chats}
            onSend={handleMessageSend} 
        />
    );

    const renderRightPanel = () => (
        <AgentNotify />
    );

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
            detailsContent={currentChat ? renderDetailsContent() : <div className="empty-chat-placeholder">请选择一个聊天</div>}
            agentNotifyTitle={t('pages.chat.agentNotify')}
            agentNotifyContent={renderRightPanel()}
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
