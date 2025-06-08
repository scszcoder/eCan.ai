import React, { useState, useRef, useEffect } from 'react';
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
    TeamOutlined
} from '@ant-design/icons';
import styled from '@emotion/styled';
import EmojiPicker from 'emoji-picker-react';
import DetailLayout from '../components/Layout/DetailLayout';
import { useDetailView } from '../hooks/useDetailView';
import SearchFilter from '../components/Common/SearchFilter';
import ActionButtons from '../components/Common/ActionButtons';
import StatusTag from '../components/Common/StatusTag';
import DetailCard from '../components/Common/DetailCard';
import { useTranslation } from 'react-i18next';
import {ipc_api, get_ipc_api} from '../services/ipc_api';

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

const MessageToolbar = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-top: 1px solid var(--border-color);
    border-radius: 0 0 8px 8px;
`;

interface Chat {
    id: number;
    name: string;
    type: 'user' | 'bot' | 'group';
    status: 'online' | 'offline' | 'busy';
    lastMessage: string;
    lastMessageTime: string;
    unreadCount: number;
}

interface Message {
    id: number;
    content: string;
    attachments: File[];
    sender: string;
    timestamp: string;
    status: 'sending' | 'sent' | 'delivered' | 'read';
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
        content: 'Hello! How can I help you today?',
        attachments: [],
        sender: 'Support Bot',
        timestamp: '10:00 AM',
        status: 'read',
    },
    {
        id: 2,
        content: 'I need help with scheduling a delivery.',
        attachments: [],
        sender: 'You',
        timestamp: '10:05 AM',
        status: 'read',
    },
    {
        id: 3,
        content: 'Sure! Here is the info you requested.',
        attachments: [
            // Simulate an agent-sent file attachment (use a Blob for demo)
            new File([new Blob(['Demo agent file content'], { type: 'text/plain' })], 'agent-info.txt'),
        ],
        sender: 'Support Bot',
        timestamp: '10:06 AM',
        status: 'read',
    },
    {
        id: 4,
        content: 'Here is the document.',
        attachments: [
            // User message with attachment for demo
            new File([new Blob(['User attached content'], { type: 'text/plain' })], 'user-doc.txt'),
        ],
        sender: 'You',
        timestamp: '10:10 AM',
        status: 'read',
    },
];

const Chat: React.FC = () => {
    const { t } = useTranslation();
    const {
        selectedItem: selectedChat,
        items: chats,
        selectItem,
        updateItem,
    } = useDetailView<Chat>(initialChats);

    const [messages, setMessages] = useState<Message[]>(initialMessages);
    const [newMessage, setNewMessage] = useState('');
    const [filters, setFilters] = useState<Record<string, any>>({});
    const [attachments, setAttachments] = useState<File[]>([]);
    const [showEmojiPicker, setShowEmojiPicker] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const mediaRecorderRef = useRef<MediaRecorder | null>(null);
    const [recording, setRecording] = useState(false);
    const [recordingReady, setRecordingReady] = useState(false);
    const chunksRef = useRef<Blob[]>([]);
    const fileInputRef = useRef<HTMLInputElement | null>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    // FIX: Attachments included in new message!
    const handleSendMessage = async () => {
        if ((!newMessage.trim() && attachments.length === 0) || !selectedChat) return;

        const newMsg: Message = {
            id: messages.length + 1,
            content: newMessage,
            attachments: [...attachments], // <--- FIXED: copy over attachments here
            sender: 'You',
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            status: 'sending',
        };

        setMessages(prev => [...prev, newMsg]);

        status = sendMessage(newMsg); // send to python section if needed
        setNewMessage('');
        setAttachments([]); // <--- Clear after send!


        setTimeout(() => {
            setMessages(prev =>
                prev.map(msg =>
                    msg.id === newMsg.id ? { ...msg, status: 'sent' } : msg
                )
            );
        }, 1000);

        setTimeout(() => {
            setMessages(prev =>
                prev.map(msg =>
                    msg.id === newMsg.id ? { ...msg, status: 'delivered' } : msg
                )
            );
        }, 2000);

        setTimeout(() => {
            const botResponse: Message = {
                id: messages.length + 2,
                content: 'I understand. Let me help you with that.',
                attachments: [],
                sender: selectedChat.name,
                timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                status: 'read',
            };
            setMessages(prev => [...prev, botResponse]);
        }, 3000);
    };


    // Read files as base64 (async utility)
    function fileToBase64(file: File): Promise<string> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => {
                if (e.target?.result) resolve(e.target.result as string);
                else reject(new Error('No file result'));
            };
            reader.onerror = e => {
                reject(e);
            };
            reader.readAsDataURL(file);
        });
    }



//     const sendMessage = async (msg: any) => {
//       const ipc_api = get_ipc_api();
//       const payload = {
//         ...msg,
//         attachments: msg.attachments.map(file => ({
//           name: file.name,
//           path: (file as any).path || null, // only works if WebEngine or your file picker exposes this
//           // or use file.webkitRelativePath if set, or add your own IPC file dialog that returns the path!
//         }))
//       };
//       await ipc_api.sendChat(payload);
//     };

    const sendMessage = async (msg: any) => {
        console.log("adding 1 chat...", msg);
        const ipc_api = get_ipc_api();

        const filesPayload = msg.attachments.map(att => ({
            name: att.file.name,
            type: att.file.type,
            content: att.base64, // send base64 to backend
        }));
        const payload = { ...msg, attachments: filesPayload };

        await ipc_api.sendChat([payload]);
    };

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        if (!e.target.files) return;
        const files = Array.from(e.target.files);

        // Immediately process to base64 for sending
        const processedFiles = await Promise.all(
            files.map(async (file) => ({
                file,
                preview: URL.createObjectURL(file),
                base64: await fileToBase64(file),
            }))
        );
        // Store these objects (with raw file, preview url, and base64)
        setAttachments(processedFiles);
    };


    const handleSearch = (value: string) => {};
    const handleFilterChange = (newFilters: Record<string, any>) => {
        setFilters(prev => ({ ...prev, ...newFilters }));
    };
    const handleReset = () => { setFilters({}); };

    const handleEmojiClick = (emojiData: any) => {
        setNewMessage(prev => prev + emojiData.emoji);
        setShowEmojiPicker(false);
    };

//     const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
//         if (!e.target.files) return;
//         console.log("filessssss:", e.target.files);
//         setAttachments(prev => [...prev, ...Array.from(e.target.files)]);
//     };

    const removeAttachment = (index: number) => {
        setAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const startRecording = async () => {
        try {
            setRecording(true);
            setRecordingReady(false);
            console.log("Requesting audio stream...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            setRecordingReady(true);
            const mediaRecorder = new MediaRecorder(stream);
            mediaRecorderRef.current = mediaRecorder;
            chunksRef.current = [];

            mediaRecorder.ondataavailable = e => {
                if (e.data.size > 0) chunksRef.current.push(e.data);
            };
            mediaRecorder.onstop = () => {
                if (chunksRef.current.length > 0) {
                    const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
                    const file = new File([blob], `voice_${Date.now()}.webm`, { type: 'audio/webm' });
                    setAttachments(prev => [...prev, file]);
                    console.log('Audio file attached:', file);
                }
                stream.getTracks().forEach(track => track.stop());
            };
            mediaRecorder.start();
        } catch (err) {
            setRecording(false);
            setRecordingReady(false);
            alert('Microphone permission denied or not available.');
            console.error('Audio record error:', err);
        }
    };

    const stopRecording = () => {
        if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
            mediaRecorderRef.current.stop();
            setRecording(false);
            setRecordingReady(false);
        } else {
            setRecording(false);
            setRecordingReady(false);
        }
    };

    const handleRecordButton = () => {
        if (!recording) {
            startRecording();
        } else {
            stopRecording();
        }
    };
    const handleDownload = (att) => {
        // Instead of downloading via browser, use IPC
        window.ipc.downloadAttachment(att.name); // send filename or file id to backend
    };

    const handleDownloadAttachment = (file: File) => {
        // For a local File, we can trigger download directly:
        console.log("downloading.... attachment");
        const url = URL.createObjectURL(file);

        // Create a hidden <a> tag and click it programmatically
        const a = document.createElement('a');
        a.href = url;
        a.download = file.name;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        // Release the URL after download
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        console.log("done downloading.... attachment");
    };

    const renderListContent = () => (
        <>
            <Title level={2}>{t('pages.chat.title')}</Title>
            <SearchFilter
                onSearch={handleSearch}
                onFilterChange={handleFilterChange}
                onReset={handleReset}
                filterOptions={[
                    {
                        key: 'type',
                        label: t('pages.chat.type'),
                        options: [
                            { label: t('pages.chat.user'), value: 'user' },
                            { label: t('pages.chat.bot'), value: 'bot' },
                            { label: t('pages.chat.group'), value: 'group' },
                        ],
                    },
                    {
                        key: 'status',
                        label: t('pages.chat.status'),
                        options: [
                            { label: t('pages.chat.online'), value: 'online' },
                            { label: t('pages.chat.offline'), value: 'offline' },
                            { label: t('pages.chat.busy'), value: 'busy' },
                        ],
                    },
                ]}
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
                renderItem={chat => (
                    <ChatItem onClick={() => selectItem(chat)}>
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
                                {chat.unreadCount > 0 && (
                                    <Badge count={chat.unreadCount} />
                                )}
                            </Space>
                            <Space>
                                <Text type="secondary">{chat.lastMessage}</Text>
                                <Text type="secondary">{chat.lastMessageTime}</Text>
                            </Space>
                        </Space>
                    </ChatItem>
                )}
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
                >
                    <div style={{ height: 'calc(100vh - 300px)', overflowY: 'auto' }}>
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
                            danger={recording}
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
                </Card>
            </Space>
        );
    };


    return (
        <DetailLayout
            listTitle={t('pages.chat.title')}
            detailsTitle={t('pages.chat.chatDetails')}
            listContent={renderListContent()}
            detailsContent={renderDetailsContent()}
        />
    );
};

export default Chat;
