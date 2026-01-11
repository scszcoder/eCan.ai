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
  LoadingOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';
import { CuteRobotIcon } from './CuteRobotIcon';
import { ClarificationCard } from './ClarificationCard';
import { PlanCard } from './PlanCard';
import { skillEditorChatService } from '../../services/skill-editor-chat-service';
import { canvasController } from '../../services/canvas-controller';
import type { 
  ClarificationQuestion, 
  ImplementationPlan,
  PipelineState,
} from '../../types/skill-editor-chat.types';

const { TextArea } = Input;

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  attachments?: string[];
  clarification?: ClarificationQuestion[];
  clarificationAnswers?: Record<string, string[]>;  // Submitted answers for clarification
  plan?: ImplementationPlan;
  planAction?: 'approved' | 'revised';  // Action taken on plan (for read-only display)
  state?: PipelineState;
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

const SessionHistoryContainer = styled.div`
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
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

const SessionListWrapper = styled.div<{ $expanded: boolean }>`
  max-height: ${props => props.$expanded ? '160px' : '0px'};
  overflow: hidden;
  transition: max-height 0.3s ease;
`;

const SessionList = styled.div`
  overflow-y: auto;
  max-height: 160px;
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

const JsonBlock = styled.pre`
  margin: 0;
  padding: 8px 10px;
  background: rgba(15, 23, 42, 0.85);
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  font-family: 'Fira Code', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #cbd5f5;
  white-space: pre;
  max-width: 100%;
  overflow-x: auto;
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

const renderMessageContent = (msg: ChatMessage) => {
  const raw = msg.content ?? '';

  // If message has clarification with submitted answers, render read-only ClarificationCard
  if (msg.clarification && msg.clarification.length > 0 && msg.clarificationAnswers) {
    return (
      <>
        {renderTextContent(raw)}
        <ClarificationCard
          questions={msg.clarification}
          submittedAnswers={msg.clarificationAnswers}
        />
      </>
    );
  }

  // If message has plan with action taken, render read-only PlanCard
  if (msg.plan && msg.planAction) {
    return (
      <>
        {renderTextContent(raw)}
        <PlanCard
          plan={msg.plan}
          submittedAction={msg.planAction}
        />
      </>
    );
  }

  return renderTextContent(raw);
};

const renderTextContent = (raw: string) => {
  const trimmed = raw.trim();
  if (trimmed.length > 0) {
    const startsJson = trimmed.startsWith('{') || trimmed.startsWith('[');
    const endsJson = trimmed.endsWith('}') || trimmed.endsWith(']');

    if (startsJson && endsJson) {
      try {
        const parsed = JSON.parse(trimmed);
        return <JsonBlock>{JSON.stringify(parsed, null, 2)}</JsonBlock>;
      } catch (err) {
        // fall through to plain text rendering if JSON.parse fails
      }
    }
  }

  const lines = raw.split('\n');
  return (
    <>
      {lines.map((line, idx) => (
        <React.Fragment key={idx}>
          {line}
          {idx < lines.length - 1 && <br />}
        </React.Fragment>
      ))}
    </>
  );
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
  const [isLoading, setIsLoading] = useState(false);
  const [pendingClarification, setPendingClarification] = useState<ClarificationQuestion[] | null>(null);
  const [pendingPlan, setPendingPlan] = useState<ImplementationPlan | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState>('idle');
  const chatThreadRef = useRef<HTMLDivElement>(null);

  // Get active session
  const activeSession = sessions.find(s => s.id === activeSessionId);

  // Load sessions from backend on mount
  useEffect(() => {
    const loadSessions = async () => {
      console.log('[ChatPanel] Loading sessions from backend...');
      try {
        const backendSessions = await skillEditorChatService.getSessions();
        if (backendSessions && backendSessions.length > 0) {
          // Convert backend format to frontend format
          const convertedSessions: ChatSession[] = backendSessions.map(s => ({
            id: s.id,
            topic: s.name || 'Chat',
            messages: (s.messages || []).map(m => ({
              id: m.id,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: new Date(m.timestamp),
              attachments: m.attachments?.map((a: any) => a.path || a.name) as string[] | undefined,
              clarification: m.metadata?.clarification as ClarificationQuestion[] | undefined,
              plan: m.metadata?.plan as ImplementationPlan | undefined,
              state: m.metadata?.state as PipelineState | undefined,
            })),
            createdAt: new Date(s.createdAt),
            updatedAt: new Date(s.updatedAt),
          }));
          
          setSessions(convertedSessions);
          console.log(`[ChatPanel] Loaded ${convertedSessions.length} sessions from backend`);
          
          // Auto-select the most recent session if none selected
          if (!activeSessionId && convertedSessions.length > 0) {
            setActiveSessionId(convertedSessions[0].id);
          }
        } else {
          console.log('[ChatPanel] No sessions found in backend');
        }
      } catch (error) {
        console.error('[ChatPanel] Failed to load sessions:', error);
      }
    };
    
    loadSessions();
  }, []); // Only run on mount

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

  // Create new session (via backend for persistence)
  const handleNewSession = useCallback(async () => {
    try {
      // Create session via backend so it gets persisted
      const backendSession = await skillEditorChatService.createSession('New Chat');
      if (backendSession) {
        const newSession: ChatSession = {
          id: backendSession.id,
          topic: backendSession.name || 'New Chat',
          messages: [],
          createdAt: new Date(backendSession.createdAt),
          updatedAt: new Date(backendSession.updatedAt),
        };
        setSessions(prev => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        setMessages([]);
        console.log('[ChatPanel] Created new session via backend:', newSession.id);
      } else {
        // Fallback to local-only session if backend fails
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
        console.warn('[ChatPanel] Backend session creation failed, using local session');
      }
    } catch (error) {
      console.error('[ChatPanel] Error creating session:', error);
      // Fallback to local-only session
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
    }
  }, []);

  // Select session
  const handleSelectSession = useCallback((sessionId: string) => {
    setActiveSessionId(sessionId);
  }, []);

  // Toggle history panel
  const handleToggleHistory = useCallback(() => {
    setHistoryExpanded(prev => !prev);
  }, []);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading) return;

    console.log('[ChatPanel] Sending message...');
    const userContent = inputValue.trim();
    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: userContent,
      timestamp: new Date(),
    };

    // If no active session, create one via backend for persistence
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      try {
        const backendSession = await skillEditorChatService.createSession('New Chat');
        if (backendSession) {
          const newSession: ChatSession = {
            id: backendSession.id,
            topic: backendSession.name || 'New Chat',
            messages: [],
            createdAt: new Date(backendSession.createdAt),
            updatedAt: new Date(backendSession.updatedAt),
          };
          setSessions(prev => [newSession, ...prev]);
          currentSessionId = newSession.id;
          setActiveSessionId(currentSessionId);
          console.log('[ChatPanel] Created session via backend:', currentSessionId);
        } else {
          // Fallback to local session if backend fails
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
          console.warn('[ChatPanel] Backend session creation failed, using local session');
        }
      } catch (error) {
        console.error('[ChatPanel] Error creating session:', error);
        // Fallback to local session
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
    }

    // Update messages locally (optimistic update)
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

    // Send to backend via IPC
    setIsLoading(true);
    console.log('[ChatPanel] Getting canvas context and sending to backend...');
    try {
      // Get current canvas context for the AI
      const canvasState = canvasController.getCanvasState();
      const canvasContext = {
        nodes: canvasState.nodes.map(n => ({
          id: n.id,
          type: n.type,
          label: n.label,
          position: n.position,
          data: n.data,
        })),
        edges: canvasState.edges.map(e => ({
          id: e.id,
          source: e.source,
          target: e.target,
          sourceHandle: e.sourceHandle,
          targetHandle: e.targetHandle,
        })),
        // Include skill info so backend can load from disk if canvas is empty
        skillName: canvasState.flowgramName,
        skillId: canvasState.flowgramId,
      };
      console.log('[ChatPanel] Canvas context:', { 
        nodeCount: canvasContext.nodes.length, 
        edgeCount: canvasContext.edges.length,
        skillName: canvasContext.skillName 
      });

      const response = await skillEditorChatService.sendMessage(
        currentSessionId!,
        userContent,
        undefined, // attachments
        canvasContext
      );

      if (response) {
        console.log('[ChatPanel] Received response from backend, state:', response.state);
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: new Date(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
        };
        
        setMessages(prev => [...prev, assistantMessage]);
        
        // Update pipeline state
        setPipelineState(response.state || 'complete');
        
        // Handle clarification questions
        if (response.clarification && response.clarification.length > 0) {
          console.log('[ChatPanel] Received clarification questions:', response.clarification.length);
          setPendingClarification(response.clarification);
          setPendingPlan(null);
        }
        // Handle implementation plan
        else if (response.plan) {
          console.log('[ChatPanel] Received implementation plan');
          setPendingPlan(response.plan);
          setPendingClarification(null);
        }
        // Clear pending states on completion
        else {
          setPendingClarification(null);
          setPendingPlan(null);
        }
        
        // Load flowgram into canvas if present in response
        if (response.flowgram) {
          console.log('[ChatPanel] Loading generated flowgram into canvas...');
          const loadResult = await canvasController.loadFlowgram(response.flowgram);
          if (loadResult.success) {
            console.log('[ChatPanel] Flowgram loaded successfully:', loadResult.data);
          } else {
            console.error('[ChatPanel] Failed to load flowgram:', loadResult.error);
          }
        }
        
        // Update session with response
        setSessions(prev => prev.map(s => {
          if (s.id === currentSessionId) {
            return {
              ...s,
              messages: [...s.messages, assistantMessage],
              topic: response.sessionName || s.topic,
              updatedAt: new Date(),
            };
          }
          return s;
        }));
      } else {
        // Handle error - add error message
        const errorMessage: ChatMessage = {
          id: `msg-error-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, I encountered an error processing your message. Please try again.',
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } catch (error) {
      console.error('[ChatPanel] Error sending message:', error);
      const errorMessage: ChatMessage = {
        id: `msg-error-${Date.now()}`,
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please check if the backend is running.',
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [inputValue, activeSessionId, messages, isLoading]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Handle clarification submission
  const handleClarificationSubmit = useCallback(async (answers: Record<string, string[]>) => {
    if (!activeSessionId || isLoading) return;
    
    console.log('[ChatPanel] Submitting clarification answers:', answers);
    setIsLoading(true);
    
    // Store the answers in the message that had the clarification questions (before clearing pending)
    const currentClarification = pendingClarification;
    setMessages(prev => prev.map(msg => {
      // Find the message with matching clarification questions and add the answers
      if (msg.clarification && msg.clarification.length > 0 && 
          currentClarification && msg.clarification[0]?.id === currentClarification[0]?.id) {
        return { ...msg, clarificationAnswers: answers };
      }
      return msg;
    }));
    
    setPendingClarification(null);
    
    try {
      const canvasState = canvasController.getCanvasState();
      const canvasContext = {
        nodes: canvasState.nodes.map(n => ({
          id: n.id,
          type: n.type,
          label: n.label,
          position: n.position,
        })),
        edges: canvasState.edges.map(e => ({
          id: e.id,
          source: e.source,
          target: e.target,
        })),
      };
      
      // Send clarification responses
      const response = await skillEditorChatService.sendMessageWithClarification(
        activeSessionId,
        'Clarification answers submitted',
        answers,
        canvasContext
      );
      
      if (response) {
        console.log('[ChatPanel] Clarification response received:', {
          state: response.state,
          hasClarification: !!response.clarification?.length,
          hasPlan: !!response.plan,
        });
        
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: new Date(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
        };
        
        setMessages(prev => [...prev, assistantMessage]);
        setPipelineState(response.state || 'complete');
        console.log('[ChatPanel] Pipeline state updated to:', response.state || 'complete');
        
        if (response.clarification && response.clarification.length > 0) {
          console.log('[ChatPanel] Setting pending clarification:', response.clarification.length, 'questions');
          setPendingClarification(response.clarification);
        } else if (response.plan) {
          console.log('[ChatPanel] Setting pending plan:', response.plan.summary);
          setPendingPlan(response.plan);
        }
      } else {
        console.warn('[ChatPanel] No response received from clarification submission');
      }
    } catch (error) {
      console.error('[ChatPanel] Error submitting clarification:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeSessionId, isLoading]);
  
  // Handle plan approval
  const handlePlanApprove = useCallback(async () => {
    if (!activeSessionId || isLoading) return;
    
    console.log('[ChatPanel] Approving plan');
    setIsLoading(true);
    
    // Store the action in the message that had the plan (before clearing pending)
    const currentPlan = pendingPlan;
    setMessages(prev => prev.map(msg => {
      if (msg.plan && currentPlan && msg.plan.summary === currentPlan.summary) {
        return { ...msg, planAction: 'approved' as const };
      }
      return msg;
    }));
    
    setPendingPlan(null);
    
    try {
      const canvasState = canvasController.getCanvasState();
      const canvasContext = {
        nodes: canvasState.nodes.map(n => ({
          id: n.id,
          type: n.type,
          label: n.label,
          position: n.position,
        })),
        edges: canvasState.edges.map(e => ({
          id: e.id,
          source: e.source,
          target: e.target,
        })),
      };
      
      const response = await skillEditorChatService.sendMessage(
        activeSessionId,
        'Yes, proceed with the plan',
        undefined,
        canvasContext
      );
      
      if (response) {
        console.log('[ChatPanel] Plan approval response received:', {
          state: response.state,
          hasFlowgram: !!response.flowgram,
          hasValidation: !!response.validation,
        });
        
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: new Date(response.message.timestamp),
          state: response.state,
        };
        
        setMessages(prev => [...prev, assistantMessage]);
        setPipelineState(response.state || 'complete');
        console.log('[ChatPanel] Pipeline state updated to:', response.state || 'complete');
        
        // Load the generated flowgram into the canvas
        if (response.flowgram) {
          console.log('[ChatPanel] Loading generated flowgram into canvas...');
          const loadResult = await canvasController.loadFlowgram(response.flowgram);
          if (loadResult.success) {
            console.log('[ChatPanel] Flowgram loaded successfully:', loadResult.data);
          } else {
            console.error('[ChatPanel] Failed to load flowgram:', loadResult.error);
          }
        }
      } else {
        console.warn('[ChatPanel] No response received from plan approval');
      }
    } catch (error) {
      console.error('[ChatPanel] Error approving plan:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeSessionId, isLoading]);
  
  // Handle plan rejection
  const handlePlanReject = useCallback(async () => {
    if (!activeSessionId || isLoading) return;
    
    console.log('[ChatPanel] Rejecting plan');
    setIsLoading(true);
    
    // Store the action in the message that had the plan (before clearing pending)
    const currentPlan = pendingPlan;
    setMessages(prev => prev.map(msg => {
      if (msg.plan && currentPlan && msg.plan.summary === currentPlan.summary) {
        return { ...msg, planAction: 'revised' as const };
      }
      return msg;
    }));
    
    setPendingPlan(null);
    
    try {
      const response = await skillEditorChatService.sendMessage(
        activeSessionId,
        'No, I want to revise the plan',
        undefined,
        undefined
      );
      
      if (response) {
        console.log('[ChatPanel] Plan rejection response received:', {
          state: response.state,
        });
        
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: new Date(response.message.timestamp),
          state: response.state,
        };
        
        setMessages(prev => [...prev, assistantMessage]);
        setPipelineState(response.state || 'idle');
        console.log('[ChatPanel] Pipeline state reset to:', response.state || 'idle');
      } else {
        console.warn('[ChatPanel] No response received from plan rejection');
      }
    } catch (error) {
      console.error('[ChatPanel] Error rejecting plan:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeSessionId, isLoading]);

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
      <SessionHistoryContainer>
        <SessionHistoryHeader onClick={handleToggleHistory}>
          <SessionHistoryTitle>
            <HistoryOutlined />
            Chat History ({sessions.length})
          </SessionHistoryTitle>
          {historyExpanded ? <UpOutlined style={{ fontSize: 10, color: 'rgba(148, 163, 184, 0.6)' }} /> : <DownOutlined style={{ fontSize: 10, color: 'rgba(148, 163, 184, 0.6)' }} />}
        </SessionHistoryHeader>
        <SessionListWrapper $expanded={historyExpanded}>
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
        </SessionListWrapper>
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
            <>
              {messages.map(msg => (
                <MessageBubble key={msg.id} $isUser={msg.role === 'user'}>
                  <MessageContent $isUser={msg.role === 'user'}>
                    {renderMessageContent(msg)}
                  </MessageContent>
                  <MessageMeta>
                    {msg.role === 'user' ? 'You' : 'Assistant'} • {formatTime(msg.timestamp)}
                  </MessageMeta>
                </MessageBubble>
              ))}
              
              {/* Render pending clarification questions */}
              {pendingClarification && pendingClarification.length > 0 && (
                <ClarificationCard
                  questions={pendingClarification}
                  onSubmit={handleClarificationSubmit}
                  isSubmitting={isLoading}
                />
              )}
              
              {/* Render pending implementation plan */}
              {pendingPlan && (
                <PlanCard
                  plan={pendingPlan}
                  onApprove={handlePlanApprove}
                  onReject={handlePlanReject}
                  isSubmitting={isLoading}
                />
              )}
              
              {isLoading && !pendingClarification && !pendingPlan && (
                <MessageBubble $isUser={false}>
                  <MessageContent $isUser={false} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <LoadingOutlined spin style={{ fontSize: 14 }} />
                    <span>{pipelineState === 'planning' ? 'Planning...' : pipelineState === 'generating' ? 'Generating workflow...' : 'Thinking...'}</span>
                  </MessageContent>
                </MessageBubble>
              )}
            </>
          )}
        </ChatThread>

      {!isCollapsed && (
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
                disabled={!inputValue.trim() || isLoading}
              >
                {isLoading ? <LoadingOutlined spin /> : <SendOutlined />}
              </SendButton>
            </InputRow>
          </InputWrapper>
        </InputContainer>
      )}
      </ChatContentArea>
    </PanelContainer>
  );
};

export default ChatPanel;
