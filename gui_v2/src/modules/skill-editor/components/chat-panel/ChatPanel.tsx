/**
 * ChatPanel - Collapsible chat interface for the skill editor
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Input, Tooltip, Upload } from 'antd';
import {
  SendOutlined,
  AudioOutlined,
  PaperClipOutlined,
  DownOutlined,
  UpOutlined,
  PlusOutlined,
  HistoryOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';
import { CuteRobotIcon } from './CuteRobotIcon';

const { TextArea } = Input;

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: string[];
}

interface ChatSession {
  id: string;
  topic: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}

interface ChatPanelProps {
  isCollapsed: boolean;
  onToggle: () => void;
  width: number;
}

const PanelContainer = styled.div<{ $width: number; $collapsed: boolean }>`
  display: flex;
  flex-direction: column;
  width: ${props => props.$collapsed ? '0px' : `${props.$width}px`};
  min-width: ${props => props.$collapsed ? '0px' : '280px'};
  max-width: ${props => props.$collapsed ? '0px' : '600px'};
  height: 100%;
  background: rgba(15, 23, 42, 0.95);
  border-right: 1px solid rgba(148, 163, 184, 0.2);
  transition: width 0.3s ease, min-width 0.3s ease, max-width 0.3s ease;
  overflow: hidden;
  position: relative;
`;

const ChatHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(30, 41, 59, 0.8);
`;

const HeaderTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 8px;
`;

const HeaderActions = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const HeaderButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: none;
  background: transparent;
  color: rgba(148, 163, 184, 0.8);
  cursor: pointer;
  border-radius: 4px;
  
  .anticon {
    font-size: 12px;
  }
  
  &:hover {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
  }
`;

const SessionHistoryContainer = styled.div<{ $expanded: boolean }>`
  display: flex;
  flex-direction: column;
  max-height: ${props => props.$expanded ? '200px' : '0px'};
  overflow: hidden;
  transition: max-height 0.3s ease;
  border-bottom: ${props => props.$expanded ? '1px solid rgba(148, 163, 184, 0.2)' : 'none'};
`;

const SessionHistoryHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: rgba(30, 41, 59, 0.6);
  cursor: pointer;
  
  &:hover {
    background: rgba(30, 41, 59, 0.8);
  }
`;

const SessionHistoryTitle = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: rgba(148, 163, 184, 0.8);
  display: flex;
  align-items: center;
  gap: 6px;
  
  .anticon {
    font-size: 11px;
  }
`;

const SessionList = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  background: rgba(15, 23, 42, 0.5);
`;

const SessionItem = styled.div<{ $active: boolean }>`
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  background: ${props => props.$active ? 'rgba(59, 130, 246, 0.2)' : 'transparent'};
  border: 1px solid ${props => props.$active ? 'rgba(59, 130, 246, 0.4)' : 'transparent'};
  
  &:hover {
    background: ${props => props.$active ? 'rgba(59, 130, 246, 0.2)' : 'rgba(51, 65, 85, 0.5)'};
  }
`;

const SessionTopic = styled.span`
  font-size: 12px;
  color: #e2e8f0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const SessionDate = styled.span`
  font-size: 10px;
  color: rgba(148, 163, 184, 0.6);
  margin-left: 8px;
  flex-shrink: 0;
`;

const ChatContentArea = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
`;

const ChatThread = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
`;

const MessageBubble = styled.div<{ $isUser: boolean }>`
  display: flex;
  flex-direction: column;
  align-items: ${props => props.$isUser ? 'flex-end' : 'flex-start'};
  gap: 4px;
`;

const MessageContent = styled.div<{ $isUser: boolean }>`
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.5;
  background: ${props => props.$isUser ? 'rgba(59, 130, 246, 0.8)' : 'rgba(51, 65, 85, 0.8)'};
  color: #e2e8f0;
  word-wrap: break-word;
`;

const MessageMeta = styled.span`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.6);
`;

const InputContainer = styled.div`
  padding: 12px 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(30, 41, 59, 0.8);
`;

const InputWrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const InputRow = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 8px;
`;

const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  gap: 2px;
`;

const IconButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  background: transparent;
  color: rgba(148, 163, 184, 0.8);
  cursor: pointer;
  border-radius: 2px;
  
  .anticon {
    font-size: 10px;
    line-height: 1;
  }
  
  &:hover {
    color: #3b82f6;
    background: rgba(59, 130, 246, 0.1);
  }
`;

const SendButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: none;
  background: #3b82f6;
  color: white;
  cursor: pointer;
  border-radius: 2px;
  
  .anticon {
    font-size: 10px;
    line-height: 1;
  }
  
  &:hover {
    background: #2563eb;
  }
  
  &:disabled {
    background: rgba(59, 130, 246, 0.4);
    cursor: not-allowed;
  }
`;

const EmptyState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: rgba(148, 163, 184, 0.6);
  text-align: center;
  padding: 24px;
  
  .anticon {
    font-size: 48px;
    margin-bottom: 16px;
    opacity: 0.5;
  }
`;

// Helper to generate topic from first message
const generateTopic = (messages: ChatMessage[]): string => {
  if (messages.length === 0) return 'New Chat';
  const firstUserMsg = messages.find(m => m.role === 'user');
  if (!firstUserMsg) return 'New Chat';
  const content = firstUserMsg.content;
  return content.length > 30 ? content.substring(0, 30) + '...' : content;
};

// Helper to format date
const formatSessionDate = (date: Date): string => {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
};

export const ChatPanel: React.FC<ChatPanelProps> = ({ isCollapsed, width }) => {
  // Session management state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  
  // Current chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const chatThreadRef = useRef<HTMLDivElement>(null);

  // Get active session
  const activeSession = sessions.find(s => s.id === activeSessionId);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatThreadRef.current) {
      chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
    }
  }, [messages]);

  // Sync messages with active session
  useEffect(() => {
    if (activeSession) {
      setMessages(activeSession.messages);
    } else {
      setMessages([]);
    }
  }, [activeSessionId]);

  // Create new session
  const handleNewSession = useCallback(() => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      topic: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date(),
    };
    setSessions(prev => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setMessages([]);
  }, []);

  // Select session
  const handleSelectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  // Toggle history panel
  const handleToggleHistory = useCallback(() => {
    setHistoryExpanded(prev => !prev);
  }, []);

  const handleSend = useCallback(() => {
    if (!inputValue.trim()) return;

    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    // If no active session, create one
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      const newSession: ChatSession = {
        id: `session-${Date.now()}`,
        topic: 'New Chat',
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      setSessions(prev => [newSession, ...prev]);
      currentSessionId = newSession.id;
      setActiveSessionId(currentSessionId);
    }

    // Update messages locally
    const updatedMessages = [...messages, newMessage];
    setMessages(updatedMessages);
    setInputValue('');

    // Update session in sessions list
    setSessions(prev => prev.map(s => {
      if (s.id === currentSessionId) {
        const newMessages = [...s.messages, newMessage];
        return {
          ...s,
          messages: newMessages,
          topic: generateTopic(newMessages),
          updatedAt: new Date(),
        };
      }
      return s;
    }));

    // TODO: Send to backend and handle response
    // For now, simulate an assistant response
    setTimeout(() => {
      const assistantMessage: ChatMessage = {
        id: `msg-${Date.now()}`,
        role: 'assistant',
        content: 'I received your message. This is a placeholder response. The chat functionality will be connected to the backend soon.',
        timestamp: new Date(),
      };
      
      setMessages(prev => [...prev, assistantMessage]);
      
      setSessions(prev => prev.map(s => {
        if (s.id === currentSessionId) {
          return {
            ...s,
            messages: [...s.messages, assistantMessage],
            updatedAt: new Date(),
          };
        }
        return s;
      }));
    }, 1000);
  }, [inputValue, activeSessionId, messages]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleVoiceInput = useCallback(() => {
    setIsRecording(prev => !prev);
    // TODO: Implement voice recording
    console.log('Voice input toggled');
  }, []);

  const handleFileUpload = useCallback((info: any) => {
    // TODO: Handle file attachment
    console.log('File uploaded:', info);
  }, []);

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  if (isCollapsed) {
    return <PanelContainer $width={width} $collapsed={true} />;
  }

  return (
    <PanelContainer $width={width} $collapsed={false}>
      <ChatHeader>
        <HeaderTitle>
          <CuteRobotIcon size={18} />
          AI Assistant
        </HeaderTitle>
        <HeaderActions>
          <Tooltip title="New chat">
            <HeaderButton onClick={handleNewSession}>
              <PlusOutlined />
            </HeaderButton>
          </Tooltip>
          <Tooltip title={historyExpanded ? 'Hide history' : 'Show history'}>
            <HeaderButton onClick={handleToggleHistory}>
              <HistoryOutlined />
            </HeaderButton>
          </Tooltip>
        </HeaderActions>
      </ChatHeader>

      {/* Collapsible Session History Panel */}
      <SessionHistoryContainer $expanded={historyExpanded}>
        <SessionHistoryHeader onClick={handleToggleHistory}>
          <SessionHistoryTitle>
            <HistoryOutlined />
            Chat History ({sessions.length})
          </SessionHistoryTitle>
          {historyExpanded ? <UpOutlined style={{ fontSize: 10, color: 'rgba(148, 163, 184, 0.6)' }} /> : <DownOutlined style={{ fontSize: 10, color: 'rgba(148, 163, 184, 0.6)' }} />}
        </SessionHistoryHeader>
        <SessionList>
          {sessions.length === 0 ? (
            <div style={{ padding: '12px', textAlign: 'center', color: 'rgba(148, 163, 184, 0.5)', fontSize: 11 }}>
              No chat history yet
            </div>
          ) : (
            sessions.map(session => (
              <SessionItem
                key={session.id}
                $active={session.id === activeSessionId}
                onClick={() => handleSelectSession(session.id)}
              >
                <SessionTopic>{session.topic}</SessionTopic>
                <SessionDate>{formatSessionDate(session.updatedAt)}</SessionDate>
              </SessionItem>
            ))
          )}
        </SessionList>
      </SessionHistoryContainer>

      {/* Chat Content Area */}
      <ChatContentArea>
        <ChatThread ref={chatThreadRef}>
          {messages.length === 0 ? (
            <EmptyState>
              <CuteRobotIcon size={48} />
              <div>Start a conversation</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>
                Ask questions about your workflow or get help building nodes
              </div>
            </EmptyState>
          ) : (
            messages.map(msg => (
              <MessageBubble key={msg.id} $isUser={msg.role === 'user'}>
                <MessageContent $isUser={msg.role === 'user'}>
                  {msg.content}
                </MessageContent>
                <MessageMeta>
                  {msg.role === 'user' ? 'You' : 'Assistant'} • {formatTime(msg.timestamp)}
                </MessageMeta>
              </MessageBubble>
            ))
          )}
        </ChatThread>

      <InputContainer>
        <InputWrapper>
          <ActionButtons>
            <Tooltip title="Voice input">
              <IconButton onClick={handleVoiceInput}>
                <AudioOutlined style={{ color: isRecording ? '#ef4444' : undefined }} />
              </IconButton>
            </Tooltip>
            <Upload
              showUploadList={false}
              beforeUpload={() => false}
              onChange={handleFileUpload}
            >
              <Tooltip title="Attach file">
                <IconButton>
                  <PaperClipOutlined />
                </IconButton>
              </Tooltip>
            </Upload>
          </ActionButtons>
          <InputRow>
            <TextArea
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              style={{
                flex: 1,
                background: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: 8,
                color: '#e2e8f0',
                resize: 'none',
              }}
            />
            <SendButton
              onClick={handleSend}
              disabled={!inputValue.trim()}
            >
              <SendOutlined />
            </SendButton>
          </InputRow>
        </InputWrapper>
      </InputContainer>
      </ChatContentArea>
    </PanelContainer>
  );
};

export default ChatPanel;
