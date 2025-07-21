import React, { useRef, useEffect, useMemo, useState } from 'react';
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

interface ChatDetailProps {
    chatId?: string | null;
    chats?: Chat[];
    onSend?: (content: string, attachments: any[]) => void;
    onMessageDelete?: (messageId: string) => void;
    setIsInitialLoading?: (loading: boolean) => void;
}

function mergeAndSortMessages(...msgArrays: any[][]) {
  const map = new Map();
  msgArrays.flat().forEach(msg => {
    if (msg && msg.id) map.set(msg.id, msg);
  });
  // 按 createAt 升序（老消息在前，新消息在后）
  return Array.from(map.values()).sort((a, b) => (a.createAt || 0) - (b.createAt || 0));
}

const ChatDetail: React.FC<ChatDetailProps> = ({ chatId: rawChatId, chats = [], onSend, onMessageDelete, setIsInitialLoading }) => {
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
    const prevScrollHeightRef = useRef(0);
    const prevScrollTopRef = useRef(0);
    const isLoadingMoreRef = useRef(false);

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
    const focusInputArea = () => {
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
    };

    // 检测消息列表变化，如果有新消息，尝试聚焦输入框
    useEffect(() => {
        if (messages.length > lastMessageLengthRef.current) {
            // 消息列表增加了，可能是发送了新消息
            setTimeout(focusInputArea, 100);
        }
        lastMessageLengthRef.current = messages.length;
    }, [messages.length]);

    // 自定义消息发送处理函数
    const handleMessageSend = (content: string, attachments: any[]) => {
        justSentMessageRef.current = true;
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
        if (onSend) {
            onSend(content, attachments);
        }
        focusInputArea();
        
        // 使用多次尝试确保聚焦成功
        const attempts = [100, 200, 300, 500, 1000];
        attempts.forEach(delay => {
            setTimeout(() => {
                if (justSentMessageRef.current) {
                    focusInputArea();
                }
            }, delay);
        });
        
        // 最后一次尝试后重置标志
        setTimeout(() => {
            justSentMessageRef.current = false;
        }, Math.max(...attempts) + 100);
    };

    // 添加事件监听，防止输入框失去焦点
    useEffect(() => {
        // 找到输入框的容器
        const chatContainer = wrapperRef.current?.querySelector('.semi-chat-container');
        
        if (!chatContainer) return;
        
        // 创建事件处理函数
        const preventFocusLoss = (e: Event) => {
            // 如果刚刚发送了消息，确保输入框保持焦点
            if (justSentMessageRef.current) {
                setTimeout(focusInputArea, 0);
            }
        };
        
        // 添加事件监听
        chatContainer.addEventListener('click', preventFocusLoss, true);
        
        return () => {
            // 移除事件监听
            chatContainer.removeEventListener('click', preventFocusLoss, true);
        };
    }, []);

    // 聊天标题
    const chatTitle = currentChat ? currentChat.name : t('pages.chat.defaultTitle');

    // 为 Semi UI Chat 生成稳定的 key
    const chatKey = useMemo(() => {
        return `chat_${chatId}_${messages.length}`;
    }, [chatId, messages.length]);

    // 处理表单提交
    const handleFormSubmit = async (formId: string, values: any, chatId: string, messageId: string, processedForm: any) => {
        const response = await get_ipc_api().chatApi.chatFormSubmit(chatId, messageId, formId, processedForm)
        console.log(JSON.stringify(response))
        if (response.success) {
            Toast.success(t('pages.chat.formSubmitSuccess'));
        } else {
            Toast.error(t('pages.chat.formSubmitFail'));
        }
    };

    // 处理卡片动作
    const handleCardAction = (action: string) => {
        if (onSend) {
            // 创建卡片动作消息
            const actionContent = JSON.stringify({
                type: 'card_action',
                action
            });
            onSend(actionContent, []);
        }
    };

    // 删除消息处理函数
    const handleMessageDelete = async (message?: any) => {
        const messageId = message?.id;
        const chatId: string = message?.chatId ?? '';
        if (!messageId || !chatId) return;
        if (onMessageDelete) {
            onMessageDelete(messageId);
            return;
        }
        // 默认行为：调用 ipc_api 删除消息
        const response = await get_ipc_api().chatApi.deleteMessage(chatId, messageId);
        console.log(JSON.stringify(response))
        if (response.success) {
            Toast.success(t('pages.chat.deleteMessageSuccess'));
            // 本地移除消息
            updateMessages(chatId, removeMessageFromList(messages, messageId));
        } else {
            Toast.error(t('pages.chat.deleteMessageFail'));
        }
    };

    // 加载更多消息
    const handleLoadMore = async () => {
        console.log('handleLoadMore called', { loadingMore, isInitialLoading, hasMore, chatId });
        if (loadingMore || isInitialLoading || !hasMore || !chatId) {
            console.log('handleLoadMore exit due to', { loadingMore, isInitialLoading, hasMore, chatId });
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
        console.log('Pagination request params', { chatId, limit: PAGE_SIZE, offset: pageMessages.length, reverse: true });
        const res = await get_ipc_api().chatApi.getChatMessages({ chatId, limit: PAGE_SIZE, offset: pageMessages.length, reverse: true });
        let newMsgs: any[] = [];
        if (res.success && res.data && typeof res.data === 'object' && Array.isArray((res.data as any).data)) {
            newMsgs = (res.data as any).data;
        }
        console.log('Pagination response message count', newMsgs.length, newMsgs);
        setPageMessages(prev => mergeAndSortMessages(newMsgs, prev));
        setOffset(offset + newMsgs.length);
        setHasMore(newMsgs.length === PAGE_SIZE);
        setLoadingMore(false);
    };

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
        if (!wrapperRef.current) {
            console.log('wrapperRef.current is null');
            return;
        }
        const chatBox = wrapperRef.current.querySelector('.semi-chat-container');
        if (chatBox) chatBoxRef.current = chatBox as HTMLDivElement;
        if (!chatBox) return;
        const onScroll = (e: Event) => {
            const target = e.target as HTMLElement;
            // console.log('onScroll', target.scrollTop, target.scrollHeight, target.clientHeight);
            if (target.scrollTop === 0) {
                // console.log('Scrolled to top, will load more');
                handleLoadMore();
            }
        };
        chatBox.addEventListener('scroll', onScroll);
        return () => chatBox.removeEventListener('scroll', onScroll);
    }, [pageMessages]);

    // 初始化加载第一页
    useEffect(() => {
        setOffset(0);
        setHasMore(true);
        setPageMessages([]);
        if (setIsInitialLoading) setIsInitialLoading(true); else _setIsInitialLoading(true);
        if (chatId) {
            // 这里不直接调用 handleLoadMore，而是等 fetchAndProcessChatMessages 完成后再设为 false
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [chatId]);

    useEffect(() => {
        if (!chatId) return;
        setPageMessages(prev => {
            const globalMsgs = (allMessages.get(chatId) || []);
            // 移除本地“sending”且内容和新消息重复的
            const filteredPrev = prev.filter(
                m => !(m.status === 'sending' && globalMsgs.some(gm => gm.content === m.content))
            );
            // 只合并比当前最新消息 createAt 更晚的新消息
            const latestTime = filteredPrev.length > 0 ? filteredPrev[filteredPrev.length - 1].createAt : 0;
            const newMsgs = globalMsgs.filter(m => m.createAt > latestTime);
            return mergeAndSortMessages(filteredPrev, newMsgs);
        });
    }, [allMessages, chatId]);

    // 自定义渲染配置
    const chatBoxRenderConfig = {
        renderChatBoxContent: (props: any) => {
            const { message } = props;
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
            );
        }
    };

    // 上传组件的配置
    const uploadProps = getUploadProps();

    // 在组件挂载和更新时尝试聚焦输入框
    useEffect(() => {
        // 延迟聚焦，确保组件已经完全渲染
        const timer = setTimeout(focusInputArea, 200);
        return () => clearTimeout(timer);
    }, [chatId]); // 当聊天ID变化时重新聚焦

    return (
        <ChatDetailWrapper ref={wrapperRef}>
            {loadingMore && <div style={{textAlign: 'center'}}>加载中...</div>}
            {!hasMore && <div style={{textAlign: 'center'}}>没有更多消息了</div>}
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