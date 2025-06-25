import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { v4 as uuidv4 } from 'uuid';
import ChatList from './components/ChatList';
import ChatDetail from './components/ChatDetail';
import { Chat, Message, Attachment, Content } from './types/chat';
import { logger } from '@/utils/logger';
import ChatLayout from './components/ChatLayout';
import AgentNotify from './components/AgentNotify';
import { demoChatData } from './chatDemoData';
import { get_ipc_api } from '@/services/ipc_api';
import { useUserStore } from '@/stores/userStore';

const ChatPage: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const username = useUserStore(state => state.username) || 'default_user';

    const [chats, setChats] = useState<Chat[]>([]);
    const [activeChatId, setActiveChatId] = useState<string | null>(null);
    const [hasNewAgentNotifications, setHasNewAgentNotifications] = useState(true);
    const [agentNotifications, setAgentNotifications] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // 通用获取聊天数据的函数
    const getChatsAndSetState = async (chatIds: string[] = [], setActive: boolean = false) => {
        try {
            const username = useUserStore.getState().username || 'default_user';
            const response = await get_ipc_api().getChats<Chat[]>(username, chatIds);
            
            if (response.success && response.data) {
                let chatData = response.data.chats;
                if (!Array.isArray(chatData)) {
                    if (chatData && typeof chatData === 'object') {
                        chatData = Object.values(chatData);
                    } else {
                        chatData = [];
                    }
                }
                if (chatIds.length === 1) {
                    // 单聊更新
                    setChats(prevChats => prevChats.map(c => c.id === chatIds[0] ? chatData[0] : c));
                } else {
                    setChats(chatData);
                    if (setActive) setActiveChatId(chatData[0]?.id || null);
                }
                logger.debug('Chats loaded successfully:', chatData.length);
            } else {
                logger.error('Failed to load chats:', response.error);
                setError(response.error?.message || 'Failed to load chats');
                setChats(demoChatData);
                if (setActive) setActiveChatId(demoChatData[0]?.id || null);
            }
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : 'Unknown error';
            logger.error('Error loading chats:', errorMessage);
            setError(`Error loading chats: ${errorMessage}`);
            setChats(demoChatData);
            if (setActive) setActiveChatId(demoChatData[0]?.id || null);
        } finally {
            setIsLoading(false);
        }
    };

    // 页面初始化
    useEffect(() => {
        setIsLoading(true);
        setError(null);
        (async () => {
            // 第一步：获取全部聊天
            try {
                const username = useUserStore.getState().username || 'default_user';
                const response = await get_ipc_api().getChats<Chat[]>(username, []);
                if (response.success && response.data) {
                    let chatData = response.data.chats;
                    if (!Array.isArray(chatData)) {
                        if (chatData && typeof chatData === 'object') {
                            chatData = Object.values(chatData);
                        } else {
                            chatData = [];
                        }
                    }
                    setChats(chatData);
                    const firstId = chatData[0]?.id || null;
                    setActiveChatId(firstId);
                    logger.debug('Chats loaded successfully:', chatData.length);
                    // 第二步：获取第一个聊天的详细数据
                    if (firstId) {
                        await getChatsAndSetState([firstId], false);
                    }
                } else {
                    logger.error('Failed to load chats:', response.error);
                    setError(response.error?.message || 'Failed to load chats');
                    setChats(demoChatData);
                    setActiveChatId(demoChatData[0]?.id || null);
                }
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : 'Unknown error';
                logger.error('Error loading chats:', errorMessage);
                setError(`Error loading chats: ${errorMessage}`);
                setChats(demoChatData);
                setActiveChatId(demoChatData[0]?.id || null);
            } finally {
                setIsLoading(false);
            }
        })();
    }, [username]);

    const handleFilterChange = (filters: Record<string, any>) => {
        logger.debug('Filter changed:', filters);
    };

    // 点击chat时
    const handleChatSelect = async (chatId: string) => {
        // 先本地更新未读
        const selectedChat = chats.find(c => c.id === chatId);
        if (selectedChat && selectedChat.unread > 0) {
            const newChats = chats.map(chat =>
                chat.id === chatId ? { ...chat, unread: 0 } : chat
            );
            setChats(newChats);
        }
        setActiveChatId(chatId);
        // 获取最新chat
        await getChatsAndSetState([chatId], false);
    };

    const handleChatDelete = (chatId: string) => {
        const updatedChats = chats.filter(c => c.id !== chatId);
        setChats(updatedChats);

        if (activeChatId === chatId) {
            setActiveChatId(updatedChats[0]?.id || null);
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
        if (!activeChatId) return;

        const chat = chats.find(c => c.id === activeChatId);
        if (!chat) return;

        // 获取当前用户信息（假设第一个 user 角色为当前用户）
        const userMember = chat.members.find(m => m.role === 'user') || chat.members[0];
        
        // 确保角色类型正确
        const userRole = userMember.role === 'user' ? 'user' : 
                        userMember.role === 'assistant' ? 'assistant' : 
                        userMember.role === 'system' ? 'system' : 'agent';
                        
        const userMessage: Message = {
            id: uuidv4(),
            role: userRole,
            createAt: Date.now(),
            senderId: userMember.id,
            senderName: userMember.name,
            content: content,
            status: 'sending',
            attachment: attachments
        };

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
            // 发送消息到后端
            const ipcApi = get_ipc_api();
            if (ipcApi) {
                // 准备发送消息的数据
                const chatData = {
                    chat_id: activeChatId,
                    message: {
                        content,
                        attachments: attachments || [],
                        sender_id: userMember.id,
                        role: userRole
                    }
                };
                
                // 发送消息
                const response = await ipcApi.sendChat(chatData);
                
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
            }
            
            // 更新消息状态为已发送
            setChats(prevChats => prevChats.map(c => {
                if (c.id !== activeChatId) return c;
                return {
                    ...c,
                    messages: c.messages.map(m => m.id === userMessage.id ? { ...m, status: 'complete' } : m),
                };
            }));

            // 模拟接收回复（在实际应用中，这应该由WebSocket或其他实时通信机制触发）
            setTimeout(() => {
                // 获取 AI/Agent 信息（假设第一个非 user 角色为 agent/assistant）
                const agentMember = chat.members.find(m => m.role !== 'user') || chat.members[0];
                
                // 确保角色类型正确
                const agentRole = agentMember.role === 'user' ? 'user' : 
                                agentMember.role === 'assistant' ? 'assistant' : 
                                agentMember.role === 'system' ? 'system' : 'agent';
                                
                const aiResponse: Message = {
                    id: uuidv4(),
                    role: agentRole,
                    createAt: Date.now(),
                    senderId: agentMember.id,
                    senderName: agentMember.name,
                    content: `Echo: "${content}"`,
                    status: 'complete',
                };

                setChats(prevChats => prevChats.map(c => {
                    if (c.id !== activeChatId) return c;
                    const isMuted = c.muted || false;
                    return {
                        ...c,
                        messages: [...c.messages, aiResponse],
                        lastMsg: aiResponse.content.toString(),
                        lastMsgTime: aiResponse.createAt,
                        unread: isMuted ? c.unread : (c.unread || 0) + 1,
                    };
                }));
            }, 1000);
        } catch (err) {
            logger.error('Error sending message:', err);
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
    
    const currentChat = chats.find((c) => c.id === activeChatId);

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

    return (
        <ChatLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={currentChat ? currentChat.name : t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
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
