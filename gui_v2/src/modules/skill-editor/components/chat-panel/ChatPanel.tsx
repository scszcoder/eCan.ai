/**
 * ChatPanel - Collapsible chat interface for the skill editor
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Input, Button, Tooltip, Upload } from 'antd';
import {
  SendOutlined,
  AudioOutlined,
  PaperClipOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';

const { TextArea } = Input;

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: string[];
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
  gap: 4px;
`;

const IconButton = styled(Button)`
  &.ant-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    padding: 0;
    border: none;
    background: transparent;
    color: rgba(148, 163, 184, 0.8);
    
    &:hover {
      color: #3b82f6;
      background: rgba(59, 130, 246, 0.1);
    }
  }
`;

const SendButton = styled(Button)`
  &.ant-btn {
    height: 32px;
    background: #3b82f6;
    border: none;
    
    &:hover {
      background: #2563eb;
    }
    
    &:disabled {
      background: rgba(59, 130, 246, 0.4);
    }
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

export const ChatPanel: React.FC<ChatPanelProps> = ({ isCollapsed, width }) => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const chatThreadRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatThreadRef.current) {
      chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = useCallback(() => {
    if (!inputValue.trim()) return;

    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, newMessage]);
    setInputValue('');

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
    }, 1000);
  }, [inputValue]);

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
          <RobotOutlined />
          AI Assistant
        </HeaderTitle>
      </ChatHeader>

      <ChatThread ref={chatThreadRef}>
        {messages.length === 0 ? (
          <EmptyState>
            <RobotOutlined />
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
              type="primary"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!inputValue.trim()}
            />
          </InputRow>
          <ActionButtons>
            <Tooltip title="Voice input">
              <IconButton
                icon={<AudioOutlined style={{ color: isRecording ? '#ef4444' : undefined }} />}
                onClick={handleVoiceInput}
              />
            </Tooltip>
            <Upload
              showUploadList={false}
              beforeUpload={() => false}
              onChange={handleFileUpload}
            >
              <Tooltip title="Attach file">
                <IconButton icon={<PaperClipOutlined />} />
              </Tooltip>
            </Upload>
          </ActionButtons>
        </InputWrapper>
      </InputContainer>
    </PanelContainer>
  );
};

export default ChatPanel;
