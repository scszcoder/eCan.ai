import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { Chat, Message, Attachment, Content } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
import AgentNotify from './components/AgentNotify';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';
import { useAppDataStore } from '@/stores/appDataStore';
import { eventBus } from '@/utils/eventBus';

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
    const [hasNewAgentNotifications, setHasNewAgentNotifications] = useState(true);
    const [agentNotifications, setAgentNotifications] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [hasFetched, setHasFetched] = useState(false);
    const lastFetchedAgentId = useRef<string | undefined>();
    const prevInitialized = useRef(initialized);
    const fetchOnceRef = useRef(false);

    useEffect(() => {
        const handler = (params: any) => {
            const { chatId, message } = params;
            const realChatId = chatId || message.chatId;
            //logger.debug('[eventBus] push_chat_message received:', { realChatId, message });
            setChats((prevChats: Chat[]) => {
                //logger.debug('[eventBus] prevChats:', prevChats.map(c => ({ id: c.id, messages: c.messages })));
                return prevChats.map((chat: Chat) => {
                    //logger.debug('[eventBus] checking chat:', chat.id, 'activeChatId:', activeChatId);
                    if (chat.id !== realChatId) return chat;
                    const messages: Message[] = Array.isArray(chat.messages) ? chat.messages : [];
                    if (messages.some((m: Message) => m.id === message.id)) {
                        // logger.debug('[eventBus] message already exists, skip:', message.id);
                        return chat;
                    }
                    // logger.debug('[eventBus] appending new message:', message);
                    return {
                        ...chat,
                        messages: [...messages, message],
                        lastMsg: message.content,
                        lastMsgTime: message.createAt,
                    };
                });
            });
        };
        eventBus.on('chat:newMessage', handler);
        return () => eventBus.off('chat:newMessage', handler);
    }, [activeChatId]);

    // tryCreateAndSelectChat 只定义一次
    const tryCreateAndSelectChat = async () => {
        if (agentId && myTwinAgentId) {
            if (!myTwinAgentId) return;
            const my_twin_agent = useAppDataStore.getState().getAgentById(myTwinAgentId);
            const receiver_agent = useAppDataStore.getState().getAgentById(agentId);
            // 1. 先调用 create_chat
            const chatData = {
                members:  [
                    {"userId": myTwinAgentId, "role": "user", "name": my_twin_agent?.card.name || "you"},
                    {"userId": agentId, "role": "agent", "name": receiver_agent?.card.name || "receiver agent"}
                  ],
                name: receiver_agent?.card.name || `Chat with ${agentId}`,
                type: 'user-agent',
            };
            console.log('[createChat] chatData:', chatData);
            const response = await get_ipc_api().chat.createChat(chatData);
            console.log('[createChat] response.data:', response.data);
            const resp: any = response;
            if (resp.success && resp.data && resp.data.data) {
                // 正确提取新 chat 数据，并兜底 name 字段
                const newChat = { ...resp.data.data, name: resp.data.data.name || chatData.name } as Chat;
                setChats(prevChats => {
                    const exists = prevChats.some(c => c.id === newChat.id);
                    const updated = exists
                        ? prevChats.map(c => c.id === newChat.id ? { ...c, ...newChat } : c)
                        : [...prevChats, newChat];
                    console.log('[createChat] setChats before:', prevChats);
                    console.log('[createChat] setChats after:', updated);
                    return updated;
                });
                setActiveChatId(newChat.id);
            }
        }
    };

    // 新增：监听 activeChatId，自动拉取消息并更新 ChatDetail（避免死循环）
    useEffect(() => {
        if (!activeChatId) return;
        handleChatSelect(activeChatId);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [activeChatId]);

    // 页面每次显示都拉取聊天，拉取完后如有agentId再创建
    useEffect(() => {
        if (!initialized) return;
        let cancelled = false;
        setIsLoading(true);

        const fetchChatsAndMaybeCreate = async () => {
            // 等待 myTwinAgentId 可用，最多重试 10 次
            let myTwinAgentId: string | undefined;
            let retry = 0;
            while (retry < 10) {
                const myTwinAgent = useAppDataStore.getState().myTwinAgent();
                myTwinAgentId = myTwinAgent?.card?.id;
                if (myTwinAgentId) break;
                await new Promise(res => setTimeout(res, 100)); // 100ms
                retry++;
            }
            if (!myTwinAgentId) {
                setIsLoading(false);
                return;
            }
            await getChatsAndSetState(myTwinAgentId);
            setIsLoading(false);
            if (agentId && !cancelled) {
                await tryCreateAndSelectChat();
            }
        };

        fetchChatsAndMaybeCreate();
        return () => { cancelled = true; };
    }, [initialized, agentId]);

    // 通用获取聊天数据的函数，使用新的 API
    const getChatsAndSetState = async (userId?: string) => {
        try {
            setIsLoading(true);
            // 使用新的 API 获取聊天数据
            const response = await get_ipc_api().chat.getChats(
                userId || '',
                false // deep 参数，按需可调整
            );
            console.log(response.data)
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
                setChats(chatData);
                // 选择 active chat 并拉取消息
                let selectedChatId: string | null = null;
                if (chatData.length > 0) {
                    if (agentId) {
                        const found = chatData.find(c => c.members?.some(m => m.userId === agentId));
                        if (found) {
                            selectedChatId = found.id;
                        } else {
                            selectedChatId = chatData[0].id;
                        }
                    } else {
                        selectedChatId = chatData[0].id;
                    }
                    setActiveChatId(selectedChatId);
                    // 等待 setChats 完成后再拉取详细消息
                    // 通过 setTimeout 0 保证 setState 执行后再调用 handleChatSelect
                    setTimeout(() => {
                        if (selectedChatId) {
                            handleChatSelect(selectedChatId);
                        }
                    }, 0);
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
        // 先本地更新未读
        const selectedChat = chats.find(c => c.id === chatId);
        if (!selectedChat) return;
        if (selectedChat.unread > 0) {
            const newChats = chats.map(chat =>
                chat.id === chatId ? { ...chat, unread: 0 } : chat
            );
            setChats(newChats);
        }
        setActiveChatId(chatId);
        // 获取最新消息
        try {
            const response = await get_ipc_api().chat.getChatMessages({ chatId });
            logger.debug("[chat message] result>>>")
            console.log(response.data)
            if (response.success && response.data) {
                let messages: Message[] = Array.isArray((response.data as any).data)
                    ? (response.data as any).data
                    : Array.isArray(response.data)
                        ? response.data as Message[]
                        : [];
                setChats(prevChats => prevChats.map(c =>
                    c.id === chatId ? { ...c, messages } : c
                ));
            } else {
                // 失败时清空消息并可选提示
                setChats(prevChats => prevChats.map(c =>
                    c.id === chatId ? { ...c, messages: [] } : c
                ));
                if (response.error) {
                    setError(typeof response.error === 'string' ? response.error : response.error.message || 'Failed to load messages');
                }
            }
        } catch (err) {
            logger.error('Error fetching chat messages:', err);
            setChats(prevChats => prevChats.map(c =>
                c.id === chatId ? { ...c, messages: [] } : c
            ));
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
                    status: resp.status || 'done',
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
            id: uuidv4(),
            chatId: activeChatId,
            role: "user",
            createAt: Date.now(),
            senderId,
            senderName,
            content: content,
            status: 'sending',
            attachment: safeAttachments
        };

        // 先乐观地更新 UI
        const updatedChats = chats.map(c => {
            if (c.id !== activeChatId) return c;
            return {
                ...c,
                messages: [...(c.messages || []), userMessage],
                lastMsg: content,
                lastMsgTime: userMessage.createAt,
            };
        });
        setChats(updatedChats);

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
                attachment: safeAttachments as any
            };
            
            const response = await get_ipc_api().chat.sendChat(messageData);
            console.log(response.data)
            if (!response.success) {
                logger.error('Failed to send message:', response.error);
                // 更新消息状态为错误
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'error' } : m),
                    };
                }));
                return;
            }
            
            // 更新消息状态为已发送，并使用服务器返回的消息 ID
            if (response.data && (response.data as any).id) {
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => 
                            m.id === userMessage.id 
                                ? { ...m, id: (response.data as any).id, status: 'complete' } 
                                : m
                        ),
                    };
                }));
            } else {
                // 如果服务器没有返回消息 ID，则只更新状态
                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    return {
                        ...c,
                        messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'complete' } : m),
                    };
                }));
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error sending message:', errorMessage);
            
            // 更新消息状态为错误
            setChats(prevChats => prevChats.map(c => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'error' } : m),
                };
            }));
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
        <AgentNotify notifications={agentNotifications} />
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
            hasNewAgentNotifications={hasNewAgentNotifications}
            onRightPanelToggle={(collapsed) => {
                if (!collapsed) {
                    setHasNewAgentNotifications(false);
                }
            }}
        />
    );
};

export default ChatPage;
