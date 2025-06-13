import { useSearchParams } from 'react-router-dom';
import React, { useState, useRef, useCallback, useEffect } from 'react';
import { List, Tag, Typography, Space, Button, Input, Avatar, Card, Badge, Tooltip } from 'antd';
import {
    MessageOutlined,
    SendOutlined,
    UserOutlined,
    RobotOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    MoreOutlined,
    SmileOutlined,
    PaperClipOutlined,
    AudioOutlined,
    CloseOutlined,
    DownloadOutlined,
    TeamOutlined,
    ReloadOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import EmojiPicker from 'emoji-picker-react';
import DetailLayout from '../../components/Layout/DetailLayout';
import { useDetailView } from '../../hooks/useDetailView';
import SearchFilter from '../../components/Common/SearchFilter';
import ActionButtons from '../../components/Common/ActionButtons';
import StatusTag from '../../components/Common/StatusTag';
import DetailCard from '../../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';
import {ipc_api, get_ipc_api} from '../../services/ipc_api';
import { create } from 'zustand';

const { Text, Title } = Typography;
const { TextArea } = Input;

const ChatItem = styled.div`
    padding: 12px;
    border-bottom: 1px solid var(--border-color);
    &:last-child {
        border-bottom: none;
    }
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: var(--bg-secondary);
    border-radius: 8px;
    margin: 4px 0;
    &:hover {
        background-color: var(--bg-tertiary);
        transform: translateX(4px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }
    .ant-typography {
        color: var(--text-primary);
    }
    .ant-tag {
        background-color: var(--bg-primary);
        border-color: var(--border-color);
    }
    .ant-progress-text {
        color: var(--text-primary);
    }
`;

const MessageItem = styled.div<{ isUser: boolean }>`
    display: flex;
    flex-direction: ${props => props.isUser ? 'row-reverse' : 'row'};
    margin-bottom: 16px;
    gap: 8px;
`;

const MessageContent = styled.div<{ isUser: boolean }>`
    max-width: 70%;
    padding: 12px;
    border-radius: 12px;
    background-color: ${props => props.isUser ? 'var(--primary-color)' : 'var(--bg-tertiary)'};
    color: ${props => props.isUser ? '#fff' : 'var(--text-primary)'};
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    display: flex;
    flex-direction: column; // <-- ensure column layout
    gap: 8px;               // <-- add spacing between text and attachments
`;

const AttachmentPreview = styled.div`
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 0 0; /* Only top margin */
    border-top: 1px dashed #e0e0e0; /* Optional: subtle border */
    padding-top: 4px;
`;

const AttachmentItem = styled.div`
    background: #f6f6f6;
    padding: 6px 10px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
`;

const MessageToolbar = styled('div')({
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px',
    borderTop: '1px solid var(--border-color)',
    borderRadius: '0 0 8px 8px',
});

export interface Chat {
    id: number;
    name: string;
    avatar?: string;
    type: 'user' | 'bot' | 'group';
    status: 'online' | 'offline' | 'busy';
    lastMessage: string;
    lastMessageTime: string;
    unreadCount: number;
    is_group?: boolean;
    members?: string[]; // user IDs
    messages?: Message[];
}

export interface Message {
    id: number;
    session_id: number;                 //simply session's epoch time in seconds.
    content: string;
    attachments: File[];
    sender: string;
    tx_timestamp: string;
    rx_timestamp: string;
    read_timestamp: string;
    status: 'sending' | 'sent' | 'delivered' | 'read';
    is_edited?: boolean;
    is_retracted?: boolean;
}

interface ChatState {
  chats: Chat[];
  activeChatId: number | null;
  addChat: (chat: Chat) => void;
  updateChat: (chat: Partial<Chat> & { id: number }) => void;
  setActiveChat: (chatId: number) => void;
  addMessage: (chatId: number, message: Message) => void;
  updateMessageStatus: (messageId: number, status: Message['status']) => void;
  sendMessage: (content: string) => Promise<void>;
  initialize: () => void;
}

const initialChats: Chat[] = [
    {
        id: 1,
        name: 'John Doe',
        type: 'user',
        status: 'online',
        lastMessage: 'Can you help me with the delivery schedule?',
        lastMessageTime: '10:30 AM',
        unreadCount: 2,
    },
    {
        id: 2,
        name: 'Support Bot',
        type: 'bot',
        status: 'online',
        lastMessage: 'How can I assist you today?',
        lastMessageTime: '09:15 AM',
        unreadCount: 0,
    },
    {
        id: 3,
        name: 'Team Alpha',
        type: 'group',
        status: 'busy',
        lastMessage: 'Meeting at 2 PM',
        lastMessageTime: 'Yesterday',
        unreadCount: 5,
    },
];

const initialMessages: Message[] = [
    {
        id: 1,
        session_id: 1,
        content: 'Hello! How can I help you today?',
        attachments: [],
        sender: 'Support Bot',
        tx_timestamp: '10:00 AM',
        rx_timestamp: '10:01 AM',
        read_timestamp: '10:01 AM',
        status: 'read',
    },
    {
        id: 2,
        session_id: 1,
        content: 'I need help with scheduling a delivery.',
        attachments: [],
        sender: 'You',
        tx_timestamp: '10:05 AM',
        rx_timestamp: '10:06 AM',
        read_timestamp: '10:06 AM',
        status: 'read',
    },
    {
        id: 3,
        session_id: 1,
        content: 'Sure! Here is the info you requested.',
        attachments: [
            // Simulate an agent-sent file attachment (use a Blob for demo)
            new File([new Blob(['Demo agent file content'], { type: 'text/plain' })], 'agent-info.txt'),
        ],
        sender: 'Support Bot',
        recipient: 'You',
        tx_timestamp: '10:06 AM',
        rx_timestamp: '10:07 AM',
        read_timestamp: '10:07 AM',
        status: 'read',
    },
    {
        id: 4,
        session_id: 1,
        content: 'Here is the document.',
        attachments: [
            // User message with attachment for demo
            new File([new Blob(['User attached content'], { type: 'text/plain' })], 'user-doc.txt'),
        ],
        sender: 'You',
        recipient: 'Support Bot',
        tx_timestamp: '10:10 AM',
        rx_timestamp: '10:11 AM',
        read_timestamp: '10:11 AM',
        status: 'read',
    },
];

interface UpdateChatsGUIParams {
    chat: Omit<Chat, 'messages'> & { messages?: Message[] };
    message: Message;
}


export const useChatStore = create<ChatState>((set) => ({
    chats: [],
    activeChatId: null,

    addChat: (chat) => set((state) => ({
        chats: [chat, ...state.chats],
        activeChatId: state.activeChatId ?? chat.id
    })),

    updateChat: (updates) => set((state) => ({
        chats: state.chats.map(chat =>
            chat.id === updates.id ? { ...chat, ...updates } : chat
        )
    })),

    setActiveChat: (chatId) => set((state) => ({
        activeChatId: chatId,
        // Reset unread count when switching to chat
        chats: state.chats.map(chat =>
            chat.id === chatId ? { ...chat, unread_count: 0 } : chat
        )
    })),

    addMessage: (chatId, message) => set((state) => {
        const chat = state.chats.find(c => c.id === chatId);
        if (!chat) return state;

        return {
            chats: state.chats.map(chat => {
                if (chat.id !== chatId) return chat;

                // Check if message already exists
                const messageExists = chat.messages.some(m => m.id === message.id);
                if (messageExists) return chat;

                return {
                    ...chat,
                    messages: [...chat.messages, message],
                    last_message: message.content,
                    last_message_time: new Date().toLocaleTimeString(),
                    last_session_time: new Date(message.tx_timestamp).toLocaleDateString(),
                    unread_count: state.activeChatId === chatId ? 0 : (chat.unread_count + 1)
                };
            })
        };
    })
}));


// 创建事件总线
const chatsEventBus = {
    listeners: new Set<(data: Message) => void>(),
    subscribe(listener: (data: Message) => void) {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    },
    emit(data: Message) {
        this.listeners.forEach(listener => listener(data));
    }
};

// 导出更新数据的函数
export const updateChatsGUI = ({ chat, message }: UpdateChatsGUIParams) => {
    const chatStore = useChatStore.getState();

    // Check if chat already exists
    const existingChat = chatStore.chats.find(c => c.id === chat.id);
    console.log('existingChat', existingChat);
    if (existingChat) {
        // Update existing chat
        console.log('existingChat true', existingChat);
        chatStore.updateChat({
            ...existingChat,
            last_message: message.content,
            last_message_time: new Date().toLocaleTimeString(),
            last_session_time: new Date(message.tx_timestamp).toLocaleDateString(),
            unread_count: chatStore.activeChatId === chat.id ? 0 : (existingChat.unread_count + 1)
        });

        // Add message to chat
        console.log('addMessage', message);
        chatStore.addMessage(chat.id, message);
    } else {
        // Create new chat with the message
        console.log('add new chat', existingChat);
        chatStore.addChat({
            ...chat,            messages: [message]
        });
    }
};

const Chat: React.FC = () => {
    const { t } = useTranslation();
    const [searchParams, setSearchParams] = useSearchParams();
    const agentId = searchParams.get('agentId');
    const [messages, setMessages] = useState<Message[]>([]);
    const [newMessage, setNewMessage] = useState('');
    const [attachments, setAttachments] = useState<File[]>([]);
    const [showEmojiPicker, setShowEmojiPicker] = useState(false);
    const [isRecording, setIsRecording] = useState(false);
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
    const [audioChunks, setAudioChunks] = useState<Blob[]>([]);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files.length > 0) {
            const newFiles = Array.from(e.target.files).map(file => ({
                file,
                name: file.name,
                type: file.type,
                size: file.size,
                lastModified: file.lastModified
            }));
            setAttachments(prev => [...prev, ...newFiles]);
        }
        // Reset the input value to allow selecting the same file again
        if (e.target) {
            e.target.value = '';
        }
    };

    const removeAttachment = (index: number) => {
        setAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mediaRecorder = new MediaRecorder(stream);
            const audioChunks: Blob[] = [];

            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);
                
                // Create a file from the blob
                const audioFile = new File([audioBlob], `recording-${Date.now()}.wav`, {
                    type: 'audio/wav',
                });

                // Add to attachments
                setAttachments(prev => [...prev, {
                    file: audioFile,
                    name: `Voice Message ${new Date().toLocaleTimeString()}`,
                    type: 'audio/wav',
                    size: audioBlob.size,
                    url: audioUrl
                }]);

                // Clean up
                stream.getTracks().forEach(track => track.stop());
                setAudioChunks([]);
            };

            mediaRecorder.start();
            setMediaRecorder(mediaRecorder);
            setIsRecording(true);
            setAudioChunks(audioChunks);
        } catch (error) {
            console.error('Error accessing microphone:', error);
            // TODO: Show error message to user
        }
    };

    const stopRecording = () => {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            setIsRecording(false);
            setMediaRecorder(null);
        }
    };

    const handleSendMessage = async () => {
        if (!selectedChat) return;
        
        const messageContent = newMessage.trim();
        if (!messageContent && attachments.length === 0) return;

        // Create a temporary message with a temporary ID
        const tempId = Date.now();
        const newMessageObj: Message = {
            id: tempId,
            chat_id: selectedChat.id,
            sender: 'You',
            content: messageContent,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            status: 'sending',
            attachments: attachments.map(att => ({
                name: att.name || 'Attachment',
                type: att.type || 'application/octet-stream',
                size: att.size || 0,
                content: att.url ? att.url.split(',')[1] : '' // Only store base64 data
            }))
        };

        // Add the message to the UI immediately
        setMessages(prev => [...prev, newMessageObj]);
        
        // Clear the input fields
        setNewMessage('');
        setAttachments([]);
        
        try {
            // Send the message via IPC
            const ipc_api = get_ipc_api();
            const response = await ipc_api.sendChat(newMessageObj);

            if (response && response.success) {
                // Update the message status to sent
                setMessages(prev => 
                    prev.map(msg => 
                        msg.id === tempId 
                            ? { ...msg, id: response.message_id, status: 'sent' } 
                            : msg
                    )
                );
                
                // Update the chat in the store
                useChatStore.getState().updateChat({
                    ...selectedChat,
                    last_message: messageContent || 'Attachment',
                    last_message_time: new Date().toISOString(),
                    unread_count: 0
                });
            } else {
                // Update the message status to failed
                setMessages(prev => 
                    prev.map(msg => 
                        msg.id === tempId 
                            ? { ...msg, status: 'failed' } 
                            : msg
                    )
                );
            }
        } catch (error) {
            console.error('Failed to send message:', error);
            // Update the message status to failed
            setMessages(prev => 
                prev.map(msg => 
                    msg.id === tempId 
                        ? { ...msg, status: 'failed' } 
                        : msg
                )
            );
        }
    };

    // Clean up media recorder on unmount
    useEffect(() => {
        return () => {
            if (mediaRecorder) {
                mediaRecorder.stream?.getTracks().forEach(track => track.stop());
            }
        };
    }, [mediaRecorder]);

    const {
        selectedItem: selectedChat,
        items: chats,
        selectItem,
        updateItem,
        setItems: setChats,
    } = useDetailView<Chat>(initialChats);

    // Get chats from the store
    const { chats: storeChats } = useChatStore();
    useEffect(() => {
        if (agentId) {
            const agentChat = chats.find(chat => chat.id.toString() === agentId);

            if (!agentChat) {
                const newChat: Chat = {
                    id: parseInt(agentId, 10),
                    name: `Agent ${agentId}`,
                    type: 'bot',
                    status: 'online',
                    last_message: t('pages.chat.startConversation'),
                    last_message_time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                    last_session_time: new Date().toLocaleDateString(),
                    unread_count: 0,
                    is_group: false,
                    members: [],
                    messages: []
                };

                // Add the new chat to the store
                useChatStore.getState().addChat(newChat);
                setChats(prevChats => [...prevChats, newChat]);
                selectItem(newChat);
                useChatStore.getState().setActiveChat(newChat.id);
        useChatStore.getState().setActiveChat(newChat.id);

        // Clear the agentId from URL
        searchParams.delete('agentId');
        setSearchParams(searchParams);
      } else {
        selectItem(agentChat);
        useChatStore.getState().setActiveChat(agentChat.id);
        // Update messages when selecting an existing chat
        const storeChat = useChatStore.getState().chats.find(c => c.id === agentChat.id);
        setMessages(storeChat?.messages || agentChat.messages || []);
      }
    }
  }, [agentId, chats, selectItem, setChats, searchParams, setSearchParams, t]);

    const renderListContent = () => (
    <>
      <Title level={2}>{t('pages.chat.title')}</Title>
      <SearchFilter
        onSearch={() => {}}
        onFilterChange={() => {}}
        onReset={() => {}}
        placeholder={t('pages.chat.searchPlaceholder')}
      />
      <ActionButtons
        onAdd={() => {}}
        onEdit={() => {}}
        onDelete={() => {}}
        onRefresh={() => {}}
        onExport={() => {}}
        onImport={() => {}}
        onSettings={() => {}}
        addText={t('pages.chat.addChat')}
        editText={t('pages.chat.editChat')}
        deleteText={t('pages.chat.deleteChat')}
        refreshText={t('pages.chat.refreshChat')}
        exportText={t('pages.chat.exportChat')}
        importText={t('pages.chat.importChat')}
        settingsText={t('pages.chat.chatSettings')}
      />
      <List
        dataSource={chats}
        renderItem={chat => {
          const storeChat = storeChats.find(c => c.id === chat.id);
          return (
            <ChatItem
              key={chat.id}
              onClick={() => {
                selectItem(chat);
                useChatStore.getState().setActiveChat(chat.id);
                // Update messages from store when selecting a chat
                const storeChat = storeChats.find(c => c.id === chat.id);
                setMessages(storeChat?.messages || chat.messages || []);
              }}
              style={{
                backgroundColor: selectedChat?.id === chat.id ? 'var(--bg-tertiary)' : 'inherit',
                cursor: 'pointer',
                transition: 'background-color 0.2s',
                '&:hover': {
                  backgroundColor: 'var(--bg-secondary)'
                }
              }}
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <Badge status={
                    chat.status === 'online' ? 'success' :
                    chat.status === 'busy' ? 'warning' : 'default'
                  } />
                  <Avatar icon={
                    chat.type === 'user' ? <UserOutlined /> :
                    chat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />
                  } />
                  <Text strong>{chat.name}</Text>
                  {(storeChat?.unread_count || 0) > 0 && (
                    <Badge count={storeChat?.unread_count} />
                  )}
                </Space>
                <Space>
                  <Text type="secondary" ellipsis={true} style={{ maxWidth: '200px' }}>
                    {storeChat?.last_message || chat.last_message || 'No messages yet'}
                  </Text>
                  <Text type="secondary">
                    {new Date(storeChat?.last_message_time || chat.last_message_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </Text>
                </Space>
              </Space>
            </ChatItem>
          );
        }}
      />
    </>
  );



    const renderDetailsContent = () => {
        if (!selectedChat) {
            return <Text type="secondary">{t('pages.chat.selectChat')}</Text>;
        }

        return (
            <Space direction="vertical" style={{ width: '100%', height: '100%' }}>
                <Card
                    title={
                        <Space>
                            <Badge status={
                                selectedChat.status === 'online' ? 'success' :
                                selectedChat.status === 'busy' ? 'warning' : 'default'
                            } />
                            <Avatar icon={
                                selectedChat.type === 'user' ? <UserOutlined /> :
                                selectedChat.type === 'bot' ? <RobotOutlined /> : <TeamOutlined />
                            } />
                            <Text strong>{selectedChat.name}</Text>
                            <Tag color={
                                selectedChat.type === 'user' ? 'blue' :
                                selectedChat.type === 'bot' ? 'green' : 'purple'
                            }>
                                {t(`pages.chat.${selectedChat.type}`)}
                            </Tag>
                        </Space>
                    }
                    extra={<Button icon={<MoreOutlined />} />}
                    bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
                >
                    <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
                        {messages.map(message => (
                            <MessageItem key={message.id} isUser={message.sender === 'You'}>
                                <Avatar icon={
                                    message.sender === 'You' ? <UserOutlined /> :
                                    message.sender === 'Support Bot' ? <RobotOutlined /> : <TeamOutlined />
                                } />
                                <Space direction="vertical" style={{ maxWidth: '70%' }}>
                                    <MessageContent isUser={message.sender === 'You'}>
                                        <div>{message.content}</div>
                                        {message.attachments && message.attachments.length > 0 && (
                                            <AttachmentPreview>
                                                {message.attachments.map((att, i) => {
                                                    // Case 1: If it's a File or Blob
                                                    if (att instanceof File || att instanceof Blob) {
                                                        return (
                                                            <AttachmentItem key={i}>
                                                                <PaperClipOutlined />
                                                                <a
                                                                    href={URL.createObjectURL(att)}
                                                                    download={att.name}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    style={{ marginLeft: 4, fontSize: 12 }}
                                                                >
                                                                    {att.name}
                                                                    <DownloadOutlined style={{ marginLeft: 6 }} />
                                                                </a>
                                                            </AttachmentItem>
                                                        );
                                                    }
                                                    // Case 2: If it's an object from backend { name, type, content }
                                                    if (att && att.content && att.type && att.name) {
                                                        const url = `data:${att.type};base64,${att.content}`;
                                                        return (
                                                            <AttachmentItem key={i}>
                                                                <PaperClipOutlined />
                                                                <a
                                                                    href={url}
                                                                    download={att.name}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                    style={{ marginLeft: 4, fontSize: 12 }}
                                                                >
                                                                    {att.name}
                                                                    <DownloadOutlined style={{ marginLeft: 6 }} />
                                                                </a>
                                                            </AttachmentItem>
                                                        );
                                                    }
                                                    return null;
                                                })}
                                            </AttachmentPreview>
                                        )}
                                    </MessageContent>

                                    <Space size={4}>
                                        <Text type="secondary" style={{ fontSize: '12px' }}>
                                            {message.timestamp}
                                        </Text>
                                        {message.sender === 'You' && (
                                            <Tooltip title={t(`pages.chat.${message.status}`)}>
                                                {message.status === 'sending' ? <ClockCircleOutlined /> :
                                                    message.status === 'sent' ? <CheckCircleOutlined /> :
                                                        message.status === 'delivered' ? <CheckCircleOutlined style={{ color: '#1890ff' }} /> :
                                                            <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                                            </Tooltip>
                                        )}
                                    </Space>
                                </Space>
                            </MessageItem>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>

                    <div style={{ padding: '16px', borderTop: '1px solid #f0f0f0' }}>
                        <MessageToolbar>
                            <Button icon={<SmileOutlined />} onClick={() => setShowEmojiPicker(p => !p)} />
                            <input
                                type="file"
                                ref={fileInputRef}
                                id="filePicker"
                                style={{ display: 'none' }}
                                multiple
                                onChange={handleFileChange}
                            />
                            <Button
                                icon={<PaperClipOutlined />}
                                onClick={() => fileInputRef.current?.click()}
                            />
                            <Button
                                icon={<AudioOutlined />}
                                onMouseDown={startRecording}
                                onMouseUp={stopRecording}
                                onMouseLeave={stopRecording}
                                danger={isRecording}
                            />
                            <TextArea
                                value={newMessage}
                                onChange={e => setNewMessage(e.target.value)}
                                placeholder={t('pages.chat.typeMessage')}
                                autoSize={{ minRows: 1, maxRows: 4 }}
                                onPressEnter={async e => {
                                    if (!e.shiftKey) {
                                        e.preventDefault();
                                        try {
                                            await handleSendMessage();
                                        } catch (err) {
                                            console.error("Failed to send message via Enter:", err);
                                        }
                                    }
                                }}
                            />
                            <Button
                                type="primary"
                                icon={<SendOutlined />}
                                onClick={handleSendMessage}
                                disabled={!newMessage.trim() && attachments.length === 0}
                            >
                                {t('pages.chat.send')}
                            </Button>
                        </MessageToolbar>

                        {/* File and audio preview (pending attachments before sending) */}
                        <AttachmentPreview>
                            {attachments.map((attObj, index) => (
                                <AttachmentItem key={index}>
                                    <PaperClipOutlined />
                                    <Text style={{ marginLeft: 4 }}>{attObj.file?.name || attObj.name}</Text>
                                    <Button
                                        size="small"
                                        type="text"
                                        icon={<CloseOutlined />}
                                        onClick={() => removeAttachment(index)}
                                    />
                                </AttachmentItem>
                            ))}
                        </AttachmentPreview>

                        {showEmojiPicker && (
                            <div style={{ position: 'absolute', bottom: 70, right: 20 }}>
                                <EmojiPicker onEmojiClick={handleEmojiClick} />
                            </div>
                        )}
                    </div>
                </Card>
            </Space>
        );
    };


    // Function to handle refresh button click
    const handleRefresh = useCallback(async () => {
        try {
            const ipc_api = get_ipc_api();
            const response = await ipc_api.get_chats();
            console.log('Chats refreshed:', response);
            if (response && response.success && response.data) {
                // Update the chats list with the new data
                // You might need to adjust this based on your actual data structure
                setChats(response.data);
            }
        } catch (error) {
            console.error('Error refreshing chats:', error);
        }
    }, []);

    // Add refresh button to the list title
    const listTitle = (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{t('pages.chat.title')}</span>
            <Button 
                type="text" 
                icon={<ReloadOutlined style={{ color: 'white' }} />} 
                onClick={handleRefresh}
                title={t('pages.chat.refresh')}
            />
        </div>
    );

    return (
        <DetailLayout
            listTitle={listTitle}
            detailsTitle={t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Chat;
