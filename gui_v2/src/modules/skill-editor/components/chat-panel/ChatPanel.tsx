/**
 * ChatPanel - Collapsible chat interface for the skill editor
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { Input, Tooltip, Upload, Popconfirm } from 'antd';
import {
  SendOutlined,
  AudioOutlined,
  PaperClipOutlined,
  DownOutlined,
  UpOutlined,
  PlusOutlined,
  HistoryOutlined,
  LoadingOutlined,
  DeleteOutlined,
  LeftOutlined,
} from '@ant-design/icons';
import styled from 'styled-components';
import { CuteRobotIcon } from './CuteRobotIcon';
import { ClarificationCard } from './ClarificationCard';
import { PlanCard } from './PlanCard';
import { skillEditorChatService } from '../../services/skill-editor-chat-service';
import { canvasController } from '../../services/canvas-controller';
import { eventBus } from '@/utils/eventBus';
import type { 
  ClarificationQuestion, 
  ChatAttachment,
  ImplementationPlan,
  PipelineState,
} from '../../types/skill-editor-chat.types';
import type { A2UIServerMessage } from './a2ui/types';

/** A2UI response data from LLM */
interface A2UIData {
  surfaceId: string;
  messages: A2UIServerMessage[];
}

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

/** Parse a timestamp value into a valid Date. Falls back to `new Date()` when the input is missing or produces an Invalid Date. */
const safeDate = (value: any): Date => {
  if (value == null) return new Date();
  const d = new Date(value);
  return isNaN(d.getTime()) ? new Date() : d;
};

const parseMaybeJson = (value: any) => {
  if (typeof value !== 'string') return value;
  const trimmed = value.trim();
  if (!trimmed) return value;
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }
  return value;
};

const buildMessageId = (rawId: any, role: 'user' | 'assistant', content: any, timestamp?: any) => {
  const normalizedId = rawId == null ? '' : String(rawId).trim();
  if (normalizedId) {
    return normalizedId;
  }
  const normalizedContent = String(content ?? '').slice(0, 80);
  const timePart = timestamp ? safeDate(timestamp).getTime() : Date.now();
  return `msg-${role}-${timePart}-${normalizedContent}`;
};

const mapContextMessages = (rawMessages: any[]): ChatMessage[] => {
  if (!Array.isArray(rawMessages)) return [];
  return rawMessages
    .filter((m) => m && typeof m === 'object' && m.id)
    .map((m) => {
      const metadata = m.metadata && typeof m.metadata === 'string' ? parseMaybeJson(m.metadata) : m.metadata;
      const attachments = m.attachments && typeof m.attachments === 'string' ? parseMaybeJson(m.attachments) : m.attachments;
      
      // Validate clarification data structure
      let clarification = metadata?.clarification;
      if (clarification && (!Array.isArray(clarification) || !clarification.every((q: any) => q?.id && q?.question && Array.isArray(q?.choices)))) {
        console.warn('[mapContextMessages] Invalid clarification data, skipping:', clarification);
        clarification = undefined;
      }
      
      // Validate plan data structure
      let plan = metadata?.plan;
      if (plan && (!plan.summary || !Array.isArray(plan.steps))) {
        console.warn('[mapContextMessages] Invalid plan data, skipping:', plan);
        plan = undefined;
      }
      
      return {
        id: buildMessageId(m.id, (m.role as 'user' | 'assistant') || 'assistant', m.content, m.timestamp),
        role: (m.role as 'user' | 'assistant') || 'assistant',
        content: String(m.content ?? ''),
        timestamp: safeDate(m.timestamp),
        attachments: Array.isArray(attachments)
          ? attachments.map((a: any) => a?.path || a?.name || String(a)).filter(Boolean)
          : undefined,
        clarification: clarification as ClarificationQuestion[] | undefined,
        clarificationAnswers: metadata?.clarificationAnswers as Record<string, string[]> | undefined,
        plan: plan as ImplementationPlan | undefined,
        planAction: metadata?.planAction as 'approved' | 'revised' | undefined,
        state: metadata?.state as PipelineState | undefined,
      } as ChatMessage;
    });
};

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

const SessionMain = styled.div`
  flex: 1;
  min-width: 0;
`;

const SessionTopRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const SessionTopic = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: #e2e8f0;
  flex: 1;
  min-width: 0;
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

const SessionPreview = styled.div`
  margin-top: 2px;
  font-size: 11px;
  color: rgba(148, 163, 184, 0.72);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const SessionDeleteButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-left: 8px;
  padding: 0;
  border: none;
  background: transparent;
  color: rgba(148, 163, 184, 0.7);
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;

  .anticon {
    font-size: 11px;
    line-height: 1;
  }

  &:hover {
    color: #f87171;
    background: rgba(239, 68, 68, 0.12);
  }
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
  padding: 16px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.72) 0%, rgba(30, 41, 59, 0.94) 100%);
`;

const InputWrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.92);
  box-shadow: 0 10px 28px rgba(2, 6, 23, 0.28);
`;

const InputRow = styled.div`
  display: flex;
  align-items: flex-end;
  gap: 10px;
`;

const ActionButtons = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
`;

const ActionButtonsLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const ComposerMeta = styled.div`
  font-size: 11px;
  color: rgba(148, 163, 184, 0.72);
  white-space: nowrap;
`;

const IconButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  background: rgba(30, 41, 59, 0.72);
  color: rgba(226, 232, 240, 0.82);
  cursor: pointer;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  
  .anticon {
    font-size: 13px;
    line-height: 1;
  }
  
  &:hover {
    color: #ffffff;
    background: rgba(59, 130, 246, 0.14);
    border-color: rgba(59, 130, 246, 0.22);
  }
`;

const SendButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  padding: 0;
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: white;
  cursor: pointer;
  border-radius: 12px;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
  flex-shrink: 0;
  
  .anticon {
    font-size: 16px;
    line-height: 1;
  }
  
  &:hover {
    background: linear-gradient(135deg, #60a5fa 0%, #2563eb 100%);
  }
  
  &:disabled {
    background: rgba(59, 130, 246, 0.32);
    box-shadow: none;
    cursor: not-allowed;
  }
`;

const StyledTextArea = styled(TextArea)`
  &.ant-input {
    width: 100%;
    background: transparent;
    border: none;
    box-shadow: none;
    color: #e2e8f0;
    font-size: 14px;
    line-height: 1.6;
    padding: 2px 0;
    resize: none;
  }

  &.ant-input::placeholder {
    color: rgba(148, 163, 184, 0.72);
  }

  &.ant-input:focus,
  &.ant-input-focused {
    border: none;
    box-shadow: none;
    background: transparent;
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
const generateTopic = (messages: ChatMessage[], defaultTopic: string): string => {
  if (messages.length === 0) return defaultTopic;
  const firstUserMsg = messages.find(m => m.role === 'user');
  if (!firstUserMsg) return defaultTopic;
  const content = firstUserMsg.content.replace(/\s+/g, ' ').trim();
  return content.length > 18 ? content.substring(0, 18) + '...' : content;
};

const getSessionPreview = (messages: ChatMessage[]): string => {
  if (!messages.length) return '';
  const lastMessage = messages[messages.length - 1];
  const content = String(lastMessage?.content || '').replace(/\s+/g, ' ').trim();
  return content.length > 36 ? content.substring(0, 36) + '...' : content;
};

// Helper to format date
const formatSessionDate = (date: Date, t: (key: string, options?: any) => string): string => {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  if (days === 0) return t('chatPanel.today');
  if (days === 1) return t('chatPanel.yesterday');
  if (days < 7) return t('chatPanel.daysAgo', { count: days });
  return date.toLocaleDateString();
};

const renderMessageContent = (msg: ChatMessage) => {
  const raw = msg.content ?? '';

  // Determine which read-only cards to show on this message
  const showClarification = msg.clarification && Array.isArray(msg.clarification) && msg.clarification.length > 0 && msg.clarificationAnswers;
  const showPlan = msg.plan && msg.plan.summary && Array.isArray(msg.plan.steps) && msg.planAction;

  if (showClarification || showPlan) {
    return (
      <>
        {renderTextContent(raw)}
        {showClarification && (
          <ClarificationCard
            questions={msg.clarification!}
            submittedAnswers={msg.clarificationAnswers!}
          />
        )}
        {showPlan && (
          <PlanCard
            plan={msg.plan!}
            submittedAction={msg.planAction!}
          />
        )}
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

export const ChatPanel: React.FC<ChatPanelProps> = ({ isCollapsed, onToggle, width }) => {
  const { t, i18n } = useTranslation('skillEditor');
  // Delay mounting the TextArea until after the CSS width transition (300ms) completes.
  // Without this, autoSize measures the container at width=0 during the animation and
  // produces NaN for the height CSS property.
  const [showInput, setShowInput] = useState(!isCollapsed);
  useEffect(() => {
    if (isCollapsed) {
      setShowInput(false);
    } else {
      const t = setTimeout(() => setShowInput(true), 320);
      return () => clearTimeout(t);
    }
  }, [isCollapsed]);

  // Session management state
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  
  // Current chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<ChatAttachment[]>([]);
  const [pendingClarification, setPendingClarification] = useState<ClarificationQuestion[] | null>(null);
  const [pendingA2UI, setPendingA2UI] = useState<A2UIData | null>(null);
  const [pendingPlan, setPendingPlan] = useState<ImplementationPlan | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState>('idle');
  const [streamingStatus, setStreamingStatus] = useState<string>('');
  const chatThreadRef = useRef<HTMLDivElement>(null);
  const hasLoadedSessionsRef = useRef(false);
  const lastFlowgramJsonRef = useRef<any>(null);  // cache last received flowgram for resending with edit approvals
  const approvingPlanRef = useRef(false);  // prevent double-click on approve button
  const planApprovedRef = useRef(false);   // once a plan is approved, block subscription from re-showing it
  const submittingClarificationRef = useRef(false);  // prevent handleDone from clearing isLoading during clarification submit
  const sendingRef = useRef(false);  // synchronous guard against double-click on Send

  // Get active session
  const activeSession = sessions.find(s => s.id === activeSessionId);
  const inputHintFallback = i18n.resolvedLanguage?.startsWith('zh')
    ? '回车发送 · Shift+回车换行'
    : 'Enter to send · Shift+Enter for newline';
  const deleteSessionLabelFallback = i18n.resolvedLanguage?.startsWith('zh') ? '删除会话' : 'Delete session';
  const confirmDeleteFallback = i18n.resolvedLanguage?.startsWith('zh') ? '删除' : 'Delete';
  const cancelDeleteFallback = i18n.resolvedLanguage?.startsWith('zh') ? '取消' : 'Cancel';

  // Load sessions lazily on first expansion to avoid competing with editor startup work
  useEffect(() => {
    if (isCollapsed || hasLoadedSessionsRef.current) {
      return;
    }

    hasLoadedSessionsRef.current = true;

    const loadSessions = async () => {
      console.log('[ChatPanel] Loading sessions from backend...');
      try {
        // 添加超时保护，避免长时间阻塞
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error(t('chatPanel.sessionLoadTimeout'))), 8000);
        });
        
        const backendSessions = await Promise.race([
          skillEditorChatService.getSessions(),
          timeoutPromise
        ]).catch(err => {
          console.warn('[ChatPanel] Failed to load sessions (timeout or error):', err);
          return [];
        });
        
        if (backendSessions && backendSessions.length > 0) {
          // Convert backend format to frontend format
          const convertedSessions: ChatSession[] = backendSessions.map(s => {
            const sessionMessages = (s.messages || []).map(m => ({
              id: buildMessageId(m.id, (m.role as 'user' | 'assistant') || 'assistant', m.content, m.timestamp),
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: safeDate(m.timestamp),
              attachments: m.attachments?.map((a: any) => a.path || a.name) as string[] | undefined,
              clarification: m.metadata?.clarification as ClarificationQuestion[] | undefined,
              plan: m.metadata?.plan as ImplementationPlan | undefined,
              state: m.metadata?.state as PipelineState | undefined,
            }));

            return {
              id: s.id,
              topic: generateTopic(sessionMessages, s.name || t('chatPanel.defaultSessionTopic')),
              messages: sessionMessages,
              createdAt: new Date(s.createdAt),
              updatedAt: new Date(s.updatedAt),
            };
          });

          convertedSessions.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
          
          setSessions(convertedSessions);
          console.log(`[ChatPanel] Loaded ${convertedSessions.length} sessions from backend`);

          // Hydrate session summaries in background so the list can show
          // title/preview without requiring the user to open each session first.
          const sessionsNeedingHistory = convertedSessions.filter(s => !s.messages || s.messages.length === 0);
          if (sessionsNeedingHistory.length > 0) {
            Promise.all(
              sessionsNeedingHistory.map(async (session) => {
                try {
                  const history = await skillEditorChatService.getHistory(session.id);
                  const mappedMessages: ChatMessage[] = history.map(m => ({
                    id: buildMessageId(m.id, (m.role as 'user' | 'assistant') || 'assistant', m.content, m.timestamp),
                    role: (m.role as 'user' | 'assistant') || 'assistant',
                    content: m.content,
                    timestamp: safeDate(m.timestamp),
                    attachments: m.attachments?.map((a: any) => a.path || a.name) as string[] | undefined,
                    clarification: m.metadata?.clarification as ClarificationQuestion[] | undefined,
                    plan: m.metadata?.plan as ImplementationPlan | undefined,
                    state: m.metadata?.state as PipelineState | undefined,
                  }));

                  return {
                    sessionId: session.id,
                    messages: mappedMessages,
                  };
                } catch (error) {
                  console.warn(`[ChatPanel] Failed to prefetch history for session ${session.id}:`, error);
                  return {
                    sessionId: session.id,
                    messages: [] as ChatMessage[],
                  };
                }
              })
            ).then((hydratedSessions) => {
              setSessions((prev) => prev.map((session) => {
                const hydrated = hydratedSessions.find((item) => item.sessionId === session.id);
                if (!hydrated || hydrated.messages.length === 0) {
                  return session;
                }
                return {
                  ...session,
                  messages: hydrated.messages,
                  topic: generateTopic(hydrated.messages, session.topic || t('chatPanel.defaultSessionTopic')),
                };
              }));
            });
          }
          
          // Don't auto-select any session — let the user either pick one from
          // history or type a new message (which creates a fresh session).
          // This mirrors the "coding agent" UX: history is visible, but a blank
          // input box always starts a new conversation.
        } else {
          console.log('[ChatPanel] No sessions found in backend');
        }
      } catch (error) {
        console.error('[ChatPanel] Failed to load sessions:', error);
      }
    };
    
    loadSessions();
  }, [isCollapsed, t]);

  useEffect(() => {
    const handleContextLoaded = (payload: any) => {
      try {
        const items = payload?.items;
        if (!Array.isArray(items) || items.length === 0) return;

        const matched = items.find((item: any) => {
          if (!item) return false;
          if (payload?.skillId && item.skillId === payload.skillId) return true;
          if (payload?.skillName && item.skillName === payload.skillName) return true;
          return false;
        }) || items[0];

        const context = parseMaybeJson(matched?.context) || {};
        const contextSessions = Array.isArray(context.sessions) ? context.sessions : undefined;
        const history = contextSessions ? undefined : (context.history || context);

        const newSessions: ChatSession[] = [];

        if (Array.isArray(contextSessions)) {
          contextSessions.forEach((s: any) => {
            if (!s?.id) return;
            const messages = mapContextMessages(s.messages || s.history?.messages || []);
            newSessions.push({
              id: String(s.id),
              topic: generateTopic(messages, s.name || matched?.skillName || t('chatPanel.defaultSessionTopic')),
              messages,
              createdAt: new Date(s.createdAt || Date.now()),
              updatedAt: new Date(s.updatedAt || s.createdAt || Date.now()),
            });
          });
        } else if (history && history.sessionId && Array.isArray(history.messages)) {
          const messages = mapContextMessages(history.messages);
          newSessions.push({
            id: String(history.sessionId),
            topic: generateTopic(messages, matched?.skillName || t('chatPanel.defaultSessionTopic')),
            messages,
            createdAt: new Date(history.createdAt || Date.now()),
            updatedAt: new Date(history.updatedAt || history.createdAt || Date.now()),
          });
        }

        if (newSessions.length === 0) {
          console.log('[ChatPanel] Context loaded but no sessions/messages found');
        } else {
          setSessions((prev) => {
            const map = new Map<string, ChatSession>();
            prev.forEach((s) => map.set(s.id, s));
            newSessions.forEach((s) => map.set(s.id, s));
            return Array.from(map.values()).sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
          });
          if (!activeSessionId && newSessions.length > 0) {
            setActiveSessionId(newSessions[0].id);
          }
        }

        if (context?.flowgram) {
          console.log('[ChatPanel] Context has flowgram, calling loadFlowgram...');
          lastFlowgramJsonRef.current = context.flowgram;
          canvasController.loadFlowgram(context.flowgram).catch((err) => {
            console.warn('[ChatPanel] Failed to load flowgram from context:', err);
          });
        } else {
          console.log('[ChatPanel] Context has no flowgram');
        }
      } catch (error) {
        console.warn('[ChatPanel] Failed to apply loaded context:', error);
      }
    };

    eventBus.on('skill_editor:context:loaded', handleContextLoaded);
    return () => {
      eventBus.off('skill_editor:context:loaded', handleContextLoaded);
    };
  }, [activeSessionId]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (chatThreadRef.current) {
      chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
    }
  }, [messages]);

  // Auto-scroll while loading/streaming so the status bubble stays visible.
  useEffect(() => {
    if (chatThreadRef.current) {
      chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
    }
  }, [isLoading, streamingStatus]);

  useEffect(() => {
    const handleChunk = (payload: any) => {
      try {
        if (!payload || payload.sessionId !== activeSessionId) return;
        const chunk = payload.chunk;
        if (typeof chunk !== 'string' || !chunk.trim()) return;
        setStreamingStatus(chunk);
      } catch {
        return;
      }
    };

    const handleDone = (payload: any) => {
      try {
        if (!payload || payload.sessionId !== activeSessionId) return;
        setStreamingStatus('');
        // Don't clear isLoading while handleClarificationSubmit is still
        // awaiting its synchronous IPC response — doing so would re-expose
        // the stale pendingClarification (old answered form) before the sync
        // response has a chance to set the new one.
        if (!submittingClarificationRef.current) {
          setIsLoading(false);
        }

        // Extract structured data forwarded from the subscription payload.
        // For Lambda-timeout responses the synchronous IPC result is a bare
        // "processing" placeholder — the real clarification / a2ui / plan
        // arrives here via the subscription relay's stream_end event.
        const content = payload.fullContent;
        const clarification = payload.clarification;
        const plan = payload.plan;
        const a2uiData = payload.a2ui;
        const state = payload.state;

        if (state) {
          // Don't let a late subscription event regress pipeline state
          // back to awaiting_plan_approval after the user has already approved.
          if (state === 'awaiting_plan_approval' && planApprovedRef.current) {
            // skip — the user already approved this plan
          } else {
            setPipelineState(state);
          }
        }

        // Build extra fields to attach to the assistant message when
        // clarification or plan data is present in this stream_end.
        const extraFields: Partial<ChatMessage> = {};
        if (Array.isArray(clarification) && clarification.length > 0) {
          extraFields.clarification = clarification;
        }
        if (plan) {
          extraFields.plan = plan;
        }
        if (state) {
          extraFields.state = state;
        }

        // If the stream_end carries actual content, render it as (or update)
        // the assistant message.  This is the primary delivery path when the
        // AppSync subscription relay is active — the synchronous IPC response
        // may only contain a placeholder "processing" message.
        //
        // IMPORTANT: We attach clarification/state in the SAME setMessages
        // call so that React batching doesn't lose the structured data.
        if (typeof content === 'string' && content.trim()) {
          const msgId = payload.messageId || `msg-stream-${Date.now()}`;
          setMessages(prev => {
            // If the last assistant message is the synthetic "processing"
            // placeholder, replace its content with the real response.
            // IMPORTANT: Skip messages that already have completed interactions
            // (clarificationAnswers or planAction) — they must be preserved as-is.
            // Also use planApprovedRef to catch the case where React hasn't flushed
            // the planAction state update yet (ref is set synchronously).
            const hasCompletedInteraction = (m: ChatMessage) =>
              m.clarificationAnswers || m.planAction || (m.plan && planApprovedRef.current);
            const last = prev.length > 0 ? prev[prev.length - 1] : null;
            if (
              last &&
              last.role === 'assistant' &&
              !hasCompletedInteraction(last) &&
              ((last as any).metadata?.placeholder === true || last.content === '⏳')
            ) {
              const updated = [...prev];
              updated[updated.length - 1] = { ...last, id: msgId, content, timestamp: new Date(), ...extraFields };
              return updated;
            }
            // Check if a message with this ID already exists (update it).
            // Preserve clarification/clarificationAnswers if already answered.
            const existingIdx = prev.findIndex(m => m.id === msgId);
            if (existingIdx >= 0) {
              const existing = prev[existingIdx];
              const updated = [...prev];
              if (hasCompletedInteraction(existing)) {
                // Preserve completed interaction fields, but still allow NEW
                // structured data (e.g. plan arriving after clarification answers)
                // to be attached.  We only protect the fields that were already set.
                updated[existingIdx] = {
                  ...existing,
                  content,
                  timestamp: new Date(),
                  ...extraFields,
                  // Re-apply the existing completed-interaction fields so
                  // extraFields can never overwrite them.
                  clarificationAnswers: existing.clarificationAnswers || (extraFields as any).clarificationAnswers,
                  planAction: existing.planAction || (extraFields as any).planAction,
                  // Keep existing clarification if it was already answered
                  ...(existing.clarificationAnswers && existing.clarification ? { clarification: existing.clarification } : {}),
                };
              } else {
                updated[existingIdx] = { ...existing, content, timestamp: new Date(), ...extraFields };
              }
              return updated;
            }
            // Append new assistant message with structured data included.
            const newMsg = {
              id: msgId,
              role: 'assistant' as const,
              content,
              timestamp: new Date(),
              ...extraFields,
            };
            return [...prev, newMsg];
          });
        } else if (Object.keys(extraFields).length > 0) {
          // No content in this stream_end, but we have structured data
          // (clarification/plan/state) — attach to the last assistant msg.
          // Even if the message has completed interactions, we still attach
          // NEW fields (e.g. plan arriving after clarification answers) while
          // preserving the existing completed fields.
          setMessages(prev => {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant') {
                const existing = prev[i];
                const updated = [...prev];
                updated[i] = {
                  ...existing,
                  ...extraFields,
                  // Re-apply existing completed-interaction fields
                  clarificationAnswers: existing.clarificationAnswers || (extraFields as any).clarificationAnswers,
                  planAction: existing.planAction || (extraFields as any).planAction,
                  ...(existing.clarificationAnswers && existing.clarification ? { clarification: existing.clarification } : {}),
                };
                return updated;
              }
            }
            return prev;
          });
        }

        if (Array.isArray(clarification) && clarification.length > 0) {
          setPendingClarification(clarification);
          if (a2uiData?.messages && a2uiData?.surfaceId) {
            setPendingA2UI({ surfaceId: a2uiData.surfaceId, messages: a2uiData.messages });
          }
          setPendingPlan(null);

          // Sync clarification to sessions so it survives session re-renders
          setSessions(prev => prev.map(s => {
            if (s.id !== activeSessionId) return s;
            const msgs = [...s.messages];
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].role === 'assistant' && !msgs[i].clarificationAnswers && !msgs[i].planAction) {
                msgs[i] = { ...msgs[i], clarification, state: state || msgs[i].state };
                break;
              }
            }
            return { ...s, messages: msgs };
          }));
        } else if (plan) {
          // Only set pendingPlan if the user hasn't already acted on it.
          // The subscription stream_end may arrive AFTER the user clicked
          // approve, which would re-show the plan card and allow a second
          // (duplicate) approval.
          if (!approvingPlanRef.current && !planApprovedRef.current) {
            setPendingPlan(plan);
            setPendingClarification(null);
            setPendingA2UI(null);
          }
        }
        // Don't clear pending states here for bare stream_end (no structured
        // data) — the synchronous response handler may still set them.
      } catch {
        return;
      }
    };

    const handleError = (payload: any) => {
      try {
        if (!payload || payload.sessionId !== activeSessionId) return;
        setStreamingStatus('');
      } catch {
        return;
      }
    };

    eventBus.on('skill_editor:chat:stream_chunk', handleChunk);
    eventBus.on('skill_editor:chat:stream_end', handleDone);
    eventBus.on('skill_editor:chat:error', handleError);

    // Listen for flowgram-loaded event to clear "Generating" status
    const handleFlowgramLoaded = (data: any) => {
      console.log('[ChatPanel] Flowgram loaded via subscription:', data);
      setStreamingStatus('');
      setPipelineState('complete');
      setIsLoading(false);
      if (data?.skillName) {
        const doneMessage: ChatMessage = {
          id: `msg-flowgram-done-${Date.now()}`,
          role: 'assistant',
          content: `✅ Workflow **${data.skillName}** loaded on canvas with ${data.nodeCount || 0} nodes.`,
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, doneMessage]);
      }
    };
    eventBus.on('skill_editor:flowgram_loaded', handleFlowgramLoaded);

    return () => {
      eventBus.off('skill_editor:chat:stream_chunk', handleChunk);
      eventBus.off('skill_editor:chat:stream_end', handleDone);
      eventBus.off('skill_editor:chat:error', handleError);
      eventBus.off('skill_editor:flowgram_loaded', handleFlowgramLoaded);
    };
  }, [activeSessionId]);

  // Sync messages with active session — only when switching sessions, not on
  // every sessions update (which could overwrite in-flight messages).
  useEffect(() => {
    if (activeSession) {
      setMessages(activeSession.messages);
    } else {
      setMessages([]);
    }
    setStreamingStatus('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSessionId]);

  // Create new session (via backend for persistence)
  const handleNewSession = useCallback(async () => {
    const resetComposerState = () => {
      setMessages([]);
      setInputValue('');
      setPendingAttachments([]);
      setPendingClarification(null);
      setPendingA2UI(null);
      setPendingPlan(null);
      setStreamingStatus('');
      setPipelineState('idle');
      setIsLoading(false);
      setHistoryExpanded(false);
    };

    try {
      // Create session via backend so it gets persisted
      const backendSession = await skillEditorChatService.createSession(t('chatPanel.newChat'));
      if (backendSession) {
        const newSession: ChatSession = {
          id: backendSession.id,
          topic: backendSession.name || t('chatPanel.newChat'),
          messages: [],
          createdAt: new Date(backendSession.createdAt),
          updatedAt: new Date(backendSession.updatedAt),
        };
        setSessions(prev => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        resetComposerState();
        console.log('[ChatPanel] Created new session via backend:', newSession.id);
      } else {
        // Fallback to local-only session if backend fails
        const newSession: ChatSession = {
          id: `session-${Date.now()}`,
          topic: t('chatPanel.newChat'),
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
        };
        setSessions(prev => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        resetComposerState();
        console.warn('[ChatPanel] Backend session creation failed, using local session');
      }
    } catch (error) {
      console.error('[ChatPanel] Error creating session:', error);
      // Fallback to local-only session
      const newSession: ChatSession = {
        id: `session-${Date.now()}`,
        topic: t('chatPanel.newChat'),
        messages: [],
        createdAt: new Date(),
        updatedAt: new Date(),
      };
      setSessions(prev => [newSession, ...prev]);
      setActiveSessionId(newSession.id);
      resetComposerState();
    }
  }, [t]);

  // Select session and load its history
  const handleSelectSession = useCallback(async (sessionId: string) => {
    setActiveSessionId(sessionId);
    setHistoryExpanded(false); // Collapse history panel after selection
    
    // Check if session already has messages loaded
    const existingSession = sessions.find(s => s.id === sessionId);
    if (existingSession && existingSession.messages && existingSession.messages.length > 0) {
      console.log(`[ChatPanel] Session ${sessionId} already has ${existingSession.messages.length} messages loaded`);
      return;
    }
    
    // Fetch history from backend
    console.log(`[ChatPanel] Fetching history for session ${sessionId}...`);
    try {
      const history = await skillEditorChatService.getHistory(sessionId);
      if (history && history.length > 0) {
        const mappedMessages: ChatMessage[] = history.map(m => ({
          id: buildMessageId(m.id, (m.role as 'user' | 'assistant') || 'assistant', m.content, m.timestamp),
          role: m.role as 'user' | 'assistant',
          content: m.content,
          timestamp: safeDate(m.timestamp),
          attachments: m.attachments?.map((a: any) => a.path || a.name) as string[] | undefined,
          clarification: m.metadata?.clarification as ClarificationQuestion[] | undefined,
          plan: m.metadata?.plan as ImplementationPlan | undefined,
          state: m.metadata?.state as PipelineState | undefined,
        }));
        
        // Update session with loaded messages
        setSessions(prev => prev.map(s => 
          s.id === sessionId ? { ...s, messages: mappedMessages } : s
        ));
        
        console.log(`[ChatPanel] Loaded ${mappedMessages.length} messages for session ${sessionId}`);
      } else {
        console.log(`[ChatPanel] No history found for session ${sessionId}`);
      }
    } catch (error) {
      console.error(`[ChatPanel] Failed to load history for session ${sessionId}:`, error);
    }
  }, [sessions]);

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      const ok = await skillEditorChatService.deleteSession(sessionId);
      if (!ok) {
        return;
      }

      setSessions(prev => {
        const nextSessions = prev.filter(s => s.id !== sessionId);

        if (activeSessionId === sessionId) {
          const nextActive = nextSessions[0]?.id ?? null;
          setActiveSessionId(nextActive);
          setMessages(nextActive ? (nextSessions[0]?.messages || []) : []);
          setInputValue('');
          setPendingAttachments([]);
          setPendingClarification(null);
          setPendingA2UI(null);
          setPendingPlan(null);
          setStreamingStatus('');
          setPipelineState('idle');
          setIsLoading(false);
        }

        return nextSessions;
      });
    } catch (error) {
      console.error(`[ChatPanel] Failed to delete session ${sessionId}:`, error);
    }
  }, [activeSessionId]);

  // Toggle history panel
  const handleToggleHistory = useCallback(() => {
    setHistoryExpanded(prev => !prev);
  }, []);

  const handleVoiceInput = useCallback(() => {
    setIsRecording(prev => !prev);
  }, []);

  const handleFileUpload = useCallback((info: any) => {
    try {
      const fileList = info?.fileList;
      if (!Array.isArray(fileList)) return;

      const attachments: ChatAttachment[] = fileList
        .map((f: any) => {
          const origin = f?.originFileObj;
          const name = String(f?.name || origin?.name || 'attachment');
          const type = String(f?.type || origin?.type || 'application/octet-stream');
          const size = Number(f?.size || origin?.size || 0);

          return {
            id: String(f?.uid || crypto.randomUUID()),
            name,
            type,
            size,
            content: '',
          };
        })
        .filter((a: any) => typeof a?.name === 'string');

      setPendingAttachments(attachments);
    } catch {
      return;
    }
  }, []);

  const handlePlanApprove = useCallback(async () => {
    if (!activeSessionId || isLoading || !pendingPlan) return;
    // Ref-based guard: React state updates are async, so a second click
    // could slip through before the re-render disables the button.
    if (approvingPlanRef.current) return;
    approvingPlanRef.current = true;
    planApprovedRef.current = true;

    setIsLoading(true);

    const currentPlan = pendingPlan;
    setPendingPlan(null);

    setMessages(prev => {
      const next = [...prev];
      let found = false;
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === 'assistant' && next[i].plan) {
          next[i] = { ...next[i], planAction: 'approved', plan: currentPlan || next[i].plan };
          found = true;
          break;
        }
      }
      if (!found) {
        // Fallback: attach planAction to last assistant message anyway
        for (let i = next.length - 1; i >= 0; i--) {
          if (next[i].role === 'assistant') {
            next[i] = { ...next[i], planAction: 'approved', plan: currentPlan! };
            break;
          }
        }
      }
      return next;
    });

    // Sync planAction to sessions so it survives session re-renders
    setSessions(prev => prev.map(s => {
      if (s.id !== activeSessionId) return s;
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant' && (msgs[i].plan || msgs[i].planAction)) {
          msgs[i] = { ...msgs[i], planAction: 'approved', plan: currentPlan || msgs[i].plan };
          break;
        }
      }
      return { ...s, messages: msgs };
    }));

    try {
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
        skillName: canvasState.flowgramName,
        skillId: canvasState.flowgramId,
        // When canvas returns 0 nodes (e.g. skill loaded from local but documentService empty),
        // send the last known flowgram so the backend can use it as fallback.
        ...(canvasState.nodes.length === 0 && lastFlowgramJsonRef.current
          ? { lastFlowgramJson: lastFlowgramJsonRef.current }
          : {}),
      };

      const response = await skillEditorChatService.sendMessage(
        activeSessionId,
        t('chatPanel.proceedWithPlan'),
        undefined,
        canvasContext
      );

      if (response) {
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: safeDate(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
        };
        // Dedup: handleDone (subscription) may have already added this message.
        // Preserve plan/planAction on any existing messages.
        setMessages(prev => {
          const definedFields: Record<string, any> = {};
          for (const [k, v] of Object.entries(assistantMessage)) {
            if (v !== undefined && v !== null) definedFields[k] = v;
          }
          let existingIdx = prev.findIndex(m => m.id === assistantMessage.id);
          if (existingIdx < 0) {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant' && prev[i].content === assistantMessage.content) {
                existingIdx = i;
                break;
              }
            }
          }
          if (existingIdx >= 0) {
            const existing = prev[existingIdx];
            const hasCompleted = existing.clarificationAnswers || existing.planAction || (existing.plan && planApprovedRef.current);
            const updated = [...prev];
            if (hasCompleted) {
              updated[existingIdx] = { ...existing, id: assistantMessage.id, content: assistantMessage.content, timestamp: assistantMessage.timestamp, state: assistantMessage.state };
            } else {
              updated[existingIdx] = { ...existing, ...definedFields };
            }
            return updated;
          }
          return [...prev, assistantMessage];
        });
        setPipelineState(response.state || 'complete');

        if (response.clarification && response.clarification.length > 0) {
          setPendingClarification(response.clarification);
          // Also capture A2UI data if provided by LLM
          if (response.a2ui?.messages && response.a2ui?.surfaceId) {
            setPendingA2UI({ surfaceId: response.a2ui.surfaceId, messages: response.a2ui.messages });
          } else {
            setPendingA2UI(null);
          }
        } else if (response.plan) {
          setPendingPlan(response.plan);
          setPendingA2UI(null);
        } else {
          setPendingClarification(null);
          setPendingA2UI(null);
          setPendingPlan(null);
        }

        if (response.flowgram) {
          lastFlowgramJsonRef.current = response.flowgram;
          await canvasController.loadFlowgram(response.flowgram);
        }
      }
    } catch (error: any) {
      const errorMsg = String(error?.message || error || '');
      const isTimeout = /timed?\s*out/i.test(errorMsg);
      console.warn('[ChatPanel] Error approving plan (isTimeout=' + isTimeout + '):', errorMsg);

      if (isTimeout) {
        // AppSync times out after ~30s, but the Lambda keeps running.
        // Show an informational message; the flowgram will arrive via event subscription.
        const infoMessage: ChatMessage = {
          id: `msg-generating-${Date.now()}`,
          role: 'assistant',
          content: t('chatPanel.generatingWorkflow'),
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, infoMessage]);
        setStreamingStatus(t('chatPanel.generatingFlowgram'));
        setPipelineState('generating');
      } else {
        const errMessage: ChatMessage = {
          id: `msg-error-${Date.now()}`,
          role: 'assistant',
          content: t('chatPanel.errorGeneratingWorkflow', { error: errorMsg }),
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errMessage]);
      }
    } finally {
      setIsLoading(false);
      approvingPlanRef.current = false;
    }
  }, [activeSessionId, isLoading, pendingPlan, t]);

  const handlePlanReject = useCallback(async () => {
    if (!activeSessionId || isLoading || !pendingPlan) return;

    console.log('[ChatPanel] Rejecting plan');
    setIsLoading(true);

    const currentPlan = pendingPlan;
    setPendingPlan(null);

    setMessages(prev => {
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === 'assistant' && next[i].plan) {
          next[i] = { ...next[i], planAction: 'revised', plan: currentPlan };
          break;
        }
      }
      return next;
    });

    // Sync planAction to sessions so it survives session re-renders
    setSessions(prev => prev.map(s => {
      if (s.id !== activeSessionId) return s;
      const msgs = [...s.messages];
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant' && msgs[i].plan) {
          msgs[i] = { ...msgs[i], planAction: 'revised', plan: currentPlan };
          break;
        }
      }
      return { ...s, messages: msgs };
    }));

    try {
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
        skillName: canvasState.flowgramName,
        skillId: canvasState.flowgramId,
        ...(canvasState.nodes.length === 0 && lastFlowgramJsonRef.current
          ? { lastFlowgramJson: lastFlowgramJsonRef.current }
          : {}),
      };

      const response = await skillEditorChatService.sendMessage(
        activeSessionId,
        t('chatPanel.rejectPlanMessage'),
        undefined,
        canvasContext
      );

      if (response) {
        const assistantMessage: ChatMessage = {
          id: response.message.id,
          role: 'assistant',
          content: response.message.content,
          timestamp: safeDate(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
        };
        // Dedup: handleDone (subscription) may have already added this message.
        // Preserve plan/planAction on any existing messages.
        setMessages(prev => {
          const definedFields: Record<string, any> = {};
          for (const [k, v] of Object.entries(assistantMessage)) {
            if (v !== undefined && v !== null) definedFields[k] = v;
          }
          let existingIdx = prev.findIndex(m => m.id === assistantMessage.id);
          if (existingIdx < 0) {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant' && prev[i].content === assistantMessage.content) {
                existingIdx = i;
                break;
              }
            }
          }
          if (existingIdx >= 0) {
            const existing = prev[existingIdx];
            const hasCompleted = existing.clarificationAnswers || existing.planAction || (existing.plan && planApprovedRef.current);
            const updated = [...prev];
            if (hasCompleted) {
              updated[existingIdx] = { ...existing, id: assistantMessage.id, content: assistantMessage.content, timestamp: assistantMessage.timestamp, state: assistantMessage.state };
            } else {
              updated[existingIdx] = { ...existing, ...definedFields };
            }
            return updated;
          }
          return [...prev, assistantMessage];
        });
        setPipelineState(response.state || 'complete');

        if (response.clarification && response.clarification.length > 0) {
          setPendingClarification(response.clarification);
          if (response.a2ui?.messages && response.a2ui?.surfaceId) {
            setPendingA2UI({ surfaceId: response.a2ui.surfaceId, messages: response.a2ui.messages });
          } else {
            setPendingA2UI(null);
          }
        } else if (response.plan) {
          setPendingPlan(response.plan);
          setPendingA2UI(null);
        } else {
          setPendingClarification(null);
          setPendingA2UI(null);
          setPendingPlan(null);
        }
      }
    } catch (error) {
      console.error('[ChatPanel] Error rejecting plan:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeSessionId, isLoading, pendingPlan]);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isLoading || sendingRef.current) return;
    sendingRef.current = true;  // synchronous guard — prevents double-click before React flushes

    // Reset plan-approval guard so the next plan can be displayed.
    planApprovedRef.current = false;

    console.log('[ChatPanel] Sending message...');
    const userContent = inputValue.trim();
    const newMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: userContent,
      timestamp: new Date(),
      attachments: pendingAttachments.map(a => a.name),
    };

    // If no active session, create one via backend for persistence
    let currentSessionId = activeSessionId;
    if (!currentSessionId) {
      try {
        const backendSession = await skillEditorChatService.createSession(t('chatPanel.newChat'));
        if (backendSession) {
          const newSession: ChatSession = {
            id: backendSession.id,
            topic: backendSession.name || t('chatPanel.newChat'),
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
            topic: t('chatPanel.newChat'),
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
          topic: t('chatPanel.newChat'),
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
          topic: generateTopic(newMessages, t('chatPanel.newChat')),
          updatedAt: new Date(),
        };
      }
      return s;
    }));

    // Send to backend via IPC
    setIsLoading(true);
    setStreamingStatus('');
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
        ...(canvasState.nodes.length === 0 && lastFlowgramJsonRef.current
          ? { lastFlowgramJson: lastFlowgramJsonRef.current }
          : {}),
      };
      console.log('[ChatPanel] Canvas context:', { 
        nodeCount: canvasContext.nodes.length, 
        edgeCount: canvasContext.edges.length,
        skillName: canvasContext.skillName 
      });

      const response = await skillEditorChatService.sendMessage(
        currentSessionId!,
        userContent,
        pendingAttachments.length ? pendingAttachments : undefined,
        canvasContext
      );

      if (response) {
        console.log('[ChatPanel] Received response from backend, state:', response.state);
        const isPlaceholder = response.state === 'processing' || response.message?.metadata?.placeholder === true;
        const assistantMessage: ChatMessage & { metadata?: any } = {
          id: buildMessageId(response.message.id, 'assistant', response.message.content, response.message.timestamp),
          role: 'assistant',
          content: isPlaceholder ? t('chatPanel.cloudProcessing') : response.message.content,
          timestamp: safeDate(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
          ...(isPlaceholder ? { metadata: { placeholder: true } } : {}),
        };
        
        // Deduplicate: the subscription relay (handleDone) may have already
        // added a message with the same content but a different ID (it uses
        // payload.messageId while the synchronous response uses
        // response.message.id).  Match by ID first, then by content to
        // prevent showing the response twice.
        setMessages(prev => {
          let existingIdx = prev.findIndex(m => m.id === assistantMessage.id);
          if (existingIdx < 0) {
            // Fallback: find the last assistant message with matching content
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant' && prev[i].content === assistantMessage.content) {
                existingIdx = i;
                break;
              }
            }
          }
          if (existingIdx >= 0) {
            // Update existing with richer metadata from synchronous response.
            // Preserve clarification/clarificationAnswers if already answered.
            const existing = prev[existingIdx];
            const updated = [...prev];
            const hasCompleted = existing.clarificationAnswers || existing.planAction || (existing.plan && planApprovedRef.current);
            if (hasCompleted) {
              updated[existingIdx] = { ...existing, id: assistantMessage.id, content: assistantMessage.content, timestamp: assistantMessage.timestamp, state: assistantMessage.state };
            } else {
              // Strip undefined values to avoid overwriting structured data with undefined
              const defined: Record<string, any> = {};
              for (const [k, v] of Object.entries(assistantMessage)) {
                if (v !== undefined && v !== null) defined[k] = v;
              }
              updated[existingIdx] = { ...existing, ...defined };
            }
            return updated;
          }
          return [...prev, assistantMessage];
        });
        
        // Update pipeline state
        setPipelineState(response.state || 'complete');
        setStreamingStatus('');
        
        // Apply structured data from the synchronous response.  Even when
        // state === 'processing' the response may carry real structured data
        // (local backend completes within the timeout but still reports
        // 'processing' as pipeline state).  Only fall back to "wait for
        // subscription" when there is truly no structured data.
        const hasStructuredData = (response.clarification && response.clarification.length > 0) || !!response.plan;
        if (hasStructuredData) {
          if (response.clarification && response.clarification.length > 0) {
            console.log('[ChatPanel] Received clarification questions:', response.clarification.length);
            setPendingClarification(response.clarification);
            if (response.a2ui?.messages && response.a2ui?.surfaceId) {
              setPendingA2UI({ surfaceId: response.a2ui.surfaceId, messages: response.a2ui.messages });
            } else {
              setPendingA2UI(null);
            }
            setPendingPlan(null);
          } else if (response.plan) {
            console.log('[ChatPanel] Received implementation plan');
            setPendingPlan(response.plan);
            setPendingClarification(null);
            setPendingA2UI(null);
          }
        } else if (response.state !== 'processing') {
          // No structured data and not processing — clear pending states
          setPendingClarification(null);
          setPendingA2UI(null);
          setPendingPlan(null);
        }
        // else: state=processing with no structured data — wait for subscription
        
        // Load flowgram into canvas if present in response
        if (response.flowgram) {
          lastFlowgramJsonRef.current = response.flowgram;
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
    } catch (error: any) {
      const errorMsg = String(error?.message || error || '');
      const isTimeout = /timed?\s*out/i.test(errorMsg);
      console.error('[ChatPanel] Error sending message (isTimeout=' + isTimeout + '):', errorMsg);

      if (isTimeout) {
        const infoMessage: ChatMessage = {
          id: `msg-generating-${Date.now()}`,
          role: 'assistant',
          content: '⏳',
          timestamp: new Date(),
          metadata: { placeholder: true },
        } as any;
        setMessages(prev => [...prev, infoMessage]);
        setStreamingStatus('Processing...');
      } else {
        const errorMessage: ChatMessage = {
          id: `msg-error-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please check if the backend is running.',
          timestamp: new Date(),
        };
        setMessages(prev => [...prev, errorMessage]);
      }
    } finally {
      sendingRef.current = false;
      setIsLoading(false);
      setPendingAttachments([]);
    }
  }, [inputValue, activeSessionId, messages, isLoading, pendingAttachments]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  // Handle clarification submission
  const handleClarificationSubmit = useCallback(async (answers: Record<string, string[]>) => {
    if (!activeSessionId || isLoading) return;

    setIsLoading(true);
    submittingClarificationRef.current = true;

    const currentClarification = pendingClarification;

    // Store the answers in the message that had the clarification questions.
    // All tiers skip messages that already have clarificationAnswers (previous
    // rounds' completed Q&A) so we never overwrite earlier rounds.
    const findTargetMsg = (msgs: ChatMessage[]): number => {
      // Primary: exact clarification[0].id match (no prior answers)
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (!msgs[i].clarificationAnswers &&
            msgs[i].clarification && msgs[i].clarification!.length > 0 &&
            currentClarification && msgs[i].clarification![0]?.id === currentClarification[0]?.id) {
          return i;
        }
      }
      // Fallback: last assistant with clarification but no answers yet
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (!msgs[i].clarificationAnswers &&
            msgs[i].role === 'assistant' && msgs[i].clarification && msgs[i].clarification!.length > 0) {
          return i;
        }
      }
      // Last resort: last assistant without completed interactions
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (!msgs[i].clarificationAnswers && !msgs[i].planAction && msgs[i].role === 'assistant') {
          return i;
        }
      }
      return -1;
    };

    setMessages(prev => {
      const targetIdx = findTargetMsg(prev);
      if (targetIdx >= 0) {
        const updated = [...prev];
        updated[targetIdx] = {
          ...updated[targetIdx],
          clarification: updated[targetIdx].clarification || currentClarification || undefined,
          clarificationAnswers: answers,
        };
        return updated;
      }
      console.warn('[ChatPanel][clarificationSubmit] No unanswered assistant message found to store answers!');
      return prev;
    });

    // Also sync the answers into sessions so they survive session-level re-renders
    setSessions(prev => prev.map(s => {
      if (s.id !== activeSessionId) return s;
      const targetIdx = findTargetMsg(s.messages);
      if (targetIdx < 0) return s;
      const msgs = [...s.messages];
      msgs[targetIdx] = {
        ...msgs[targetIdx],
        clarification: msgs[targetIdx].clarification || currentClarification || undefined,
        clarificationAnswers: answers,
      };
      return { ...s, messages: msgs };
    }));

    // Clear the old form BEFORE the await so it disappears immediately.
    // If the request fails we restore it in the catch block.
    setPendingClarification(null);
    setPendingA2UI(null);

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
        const assistantMessage: ChatMessage = {
          id: buildMessageId(response.message.id, 'assistant', response.message.content, response.message.timestamp),
          role: 'assistant',
          content: response.message.content,
          timestamp: safeDate(response.message.timestamp),
          clarification: response.clarification,
          plan: response.plan,
          state: response.state,
        };

        // Deduplicate: handleDone (subscription/local-ws push) may have
        // already appended a message with the same content but different ID.
        // IMPORTANT: When merging, strip undefined values from assistantMessage
        // so we never overwrite existing clarification/clarificationAnswers
        // with undefined (which destroys the read-only Q&A card).
        const definedFields: Record<string, any> = {};
        for (const [k, v] of Object.entries(assistantMessage)) {
          if (v !== undefined && v !== null) definedFields[k] = v;
        }
        setMessages(prev => {
          let existingIdx = prev.findIndex(m => m.id === assistantMessage.id);
          if (existingIdx < 0) {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === 'assistant' && prev[i].content === assistantMessage.content) {
                existingIdx = i;
                break;
              }
            }
          }
          if (existingIdx >= 0) {
            const existing = prev[existingIdx];
            // If the existing message already has completed interactions,
            // don't let this merge touch them — just update non-interaction fields.
            const hasCompleted = existing.clarificationAnswers || existing.planAction || (existing.plan && planApprovedRef.current);
            const merged = hasCompleted
              ? { ...existing, ...definedFields, clarification: existing.clarification, clarificationAnswers: existing.clarificationAnswers, plan: existing.plan, planAction: existing.planAction }
              : { ...existing, ...definedFields };
            const updated = [...prev];
            updated[existingIdx] = merged as ChatMessage;
            return updated;
          }
          return [...prev, assistantMessage];
        });

        // Persist the assistant message into the sessions list so that
        // re-renders reading from activeSession.messages stay in sync.
        setSessions(prev => prev.map(s => {
          if (s.id === activeSessionId) {
            return {
              ...s,
              messages: [...s.messages, assistantMessage],
              updatedAt: new Date(),
            };
          }
          return s;
        }));

        setPipelineState(response.state || 'complete');

        // Apply structured data from the sync response.  Even when
        // state === 'processing' the response may carry real structured
        // data (local backend completes within the timeout but still
        // reports 'processing' as pipeline state).  Only fall back to
        // the "wait for subscription" path when there is truly no data.
        const hasStructured = (response.clarification && response.clarification.length > 0) || !!response.plan;
        if (hasStructured) {
          if (response.clarification && response.clarification.length > 0) {
            setPendingClarification(response.clarification);
            if (response.a2ui?.messages && response.a2ui?.surfaceId) {
              setPendingA2UI({ surfaceId: response.a2ui.surfaceId, messages: response.a2ui.messages });
            }
          } else if (response.plan) {
            setPendingPlan(response.plan);
          }
        } else if (response.state === 'processing') {
          // Truly bare "processing" placeholder — the real structured data
          // will arrive via the subscription relay's stream_end event.
          setStreamingStatus(t('chatPanel.cloudProcessing'));
        }
      } else {
        console.warn('[ChatPanel] No response received from clarification submission');
        // Restore pending so user can retry and surface error
        if (currentClarification) {
          setPendingClarification(currentClarification);
        }
        const assistantMessage: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: 'Clarification submission failed (timeout or IPC error). Please try again.',
          timestamp: new Date(),
          state: pipelineState || 'awaiting_clarification',
        };
        setMessages(prev => [...prev, assistantMessage]);
        setPipelineState(prev => prev || 'awaiting_clarification');
      }
    } catch (error) {
      console.error('[ChatPanel] Error submitting clarification:', error);
      if (currentClarification) {
        setPendingClarification(currentClarification);
      }
      const errText = error instanceof Error ? error.message : 'Clarification submission failed.';
      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `${errText} Please try again.`,
        timestamp: new Date(),
        state: pipelineState || 'awaiting_clarification',
      };
      setMessages(prev => [...prev, assistantMessage]);
      setPipelineState(prev => prev || 'awaiting_clarification');
    } finally {
      submittingClarificationRef.current = false;
      setIsLoading(false);
    }
  }, [activeSessionId, canvasController, inputValue, isLoading, streamingStatus, pendingClarification, pipelineState, setMessages, setPendingPlan]);

  // Handle clarification cancel — dismiss the form and reset pipeline state
  const handleClarificationCancel = useCallback(() => {
    console.log('[ChatPanel] Clarification cancelled by user');
    setPendingClarification(null);
    setPendingA2UI(null);
    setPipelineState('idle');
    const cancelMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: 'Clarification cancelled. Feel free to describe what you\'d like to build whenever you\'re ready.',
      timestamp: new Date(),
      state: 'idle',
    };
    setMessages(prev => [...prev, cancelMsg]);
  }, [setMessages]);

// ...

  return (
    <PanelContainer $width={width} $collapsed={isCollapsed}>
      {/* ... */}

      {!isCollapsed && (
        <>
          <ChatHeader>
            <HeaderTitle>
              <CuteRobotIcon size={18} />
              {t('chatPanel.title')}
            </HeaderTitle>
            <HeaderActions>
              <Tooltip title={t('chatPanel.newChatTooltip')}>
                <HeaderButton onClick={handleNewSession}>
                  <PlusOutlined />
                </HeaderButton>
              </Tooltip>
              <Tooltip title={historyExpanded ? t('chatPanel.hideHistory') : t('chatPanel.showHistory')}>
                <HeaderButton onClick={handleToggleHistory}>
                  <HistoryOutlined />
                </HeaderButton>
              </Tooltip>
              <Tooltip title={t('chatPanel.close')}>
                <HeaderButton onClick={onToggle}>
                  <LeftOutlined />
                </HeaderButton>
              </Tooltip>
            </HeaderActions>
          </ChatHeader>

          <SessionHistoryContainer>
            <SessionHistoryHeader onClick={handleToggleHistory}>
              <SessionHistoryTitle>
                <HistoryOutlined />
                {t('chatPanel.sessions', { count: sessions.length })}
              </SessionHistoryTitle>
              {historyExpanded ? <UpOutlined /> : <DownOutlined />}
            </SessionHistoryHeader>
            <SessionListWrapper $expanded={historyExpanded}>
              <SessionList>
                {sessions.map(session => (
                  <SessionItem
                    key={session.id}
                    $active={session.id === activeSessionId}
                    onClick={() => handleSelectSession(session.id)}
                  >
                    <SessionMain>
                      <SessionTopRow>
                        <SessionTopic>{generateTopic(session.messages, session.topic || t('chatPanel.defaultSessionTopic'))}</SessionTopic>
                        <SessionDate>{formatSessionDate(session.updatedAt, t)}</SessionDate>
                      </SessionTopRow>
                      <SessionPreview>{getSessionPreview(session.messages)}</SessionPreview>
                    </SessionMain>
                    <Popconfirm
                      title={t('chatPanel.deleteSessionConfirm', {
                        topic: generateTopic(session.messages, session.topic || t('chatPanel.defaultSessionTopic')),
                        defaultValue: i18n.resolvedLanguage?.startsWith('zh')
                          ? `删除会话“${generateTopic(session.messages, session.topic || t('chatPanel.defaultSessionTopic'))}”？此操作不可撤销。`
                          : `Delete session "${generateTopic(session.messages, session.topic || t('chatPanel.defaultSessionTopic'))}"? This cannot be undone.`,
                      })}
                      okText={t('chatPanel.confirmDelete', { defaultValue: confirmDeleteFallback })}
                      cancelText={t('chatPanel.cancelDelete', { defaultValue: cancelDeleteFallback })}
                      onConfirm={(e) => {
                        e?.stopPropagation?.();
                        handleDeleteSession(session.id);
                      }}
                      onPopupClick={(e) => e.stopPropagation()}
                    >
                      <Tooltip title={t('chatPanel.deleteSession', { defaultValue: deleteSessionLabelFallback })}>
                        <SessionDeleteButton
                          onClick={(e) => {
                            e.stopPropagation();
                          }}
                        >
                          <DeleteOutlined />
                        </SessionDeleteButton>
                      </Tooltip>
                    </Popconfirm>
                  </SessionItem>
                ))}
              </SessionList>
            </SessionListWrapper>
          </SessionHistoryContainer>
        </>
      )}

      {/* Chat Content Area */}
      <ChatContentArea>
        <ChatThread ref={chatThreadRef}>
          {/* ... */}

          {messages.length === 0 && !isLoading ? (
            <EmptyState>
              <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 6 }}>{t('chatPanel.noMessages')}</div>
              <div style={{ fontSize: 12 }}>{t('chatPanel.startNewChat')}</div>
            </EmptyState>
          ) : (
            messages.map((msg, idx) => (
              <MessageBubble key={msg.id || `message-${idx}`} $isUser={msg.role === 'user'}>
                <MessageContent $isUser={msg.role === 'user'}>
                  {renderMessageContent(msg)}
                  {msg.attachments && msg.attachments.length > 0 && (
                    <div style={{ marginTop: 6, fontSize: 11, color: 'rgba(148, 163, 184, 0.8)' }}>
                      {t('chatPanel.attachments')}: {msg.attachments.join(', ')}
                    </div>
                  )}
                </MessageContent>
                <MessageMeta>{isNaN(msg.timestamp.getTime()) ? '' : msg.timestamp.toLocaleTimeString()}</MessageMeta>
              </MessageBubble>
            ))
          )}

          {!isLoading && pendingClarification && pendingClarification.length > 0 && (
            <ClarificationCard
              questions={pendingClarification}
              onSubmit={handleClarificationSubmit}
              isSubmitting={isLoading}
            />
          )}

          {!isLoading && pendingPlan && (
            <PlanCard
              plan={pendingPlan}
              onApprove={handlePlanApprove}
              onReject={handlePlanReject}
              isSubmitting={isLoading}
            />
          )}

          {isLoading && (
            <MessageBubble $isUser={false}>
              <MessageContent $isUser={false} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <LoadingOutlined spin style={{ fontSize: 14 }} />
                <span style={{ color: 'rgba(203, 213, 225, 0.85)' }}>
                  {streamingStatus || (pipelineState === 'planning' ? t('chatPanel.planning') : pipelineState === 'generating' ? t('chatPanel.generatingFlowgram') : t('chatPanel.thinking'))}
                </span>
              </MessageContent>
            </MessageBubble>
          )}
        </ChatThread>

      {showInput && (
        <InputContainer>
          <InputWrapper>
            <InputRow>
              <StyledTextArea
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('chatPanel.typeMessage')}
                autoSize={{ minRows: 1, maxRows: 4 }}
              />
              <SendButton
                onClick={handleSend}
                disabled={!inputValue.trim() || isLoading}
              >
                {isLoading ? <LoadingOutlined spin /> : <SendOutlined />}
              </SendButton>
            </InputRow>
            <ActionButtons>
              <ActionButtonsLeft>
                <Tooltip title={t('chatPanel.voiceInput')}>
                  <IconButton onClick={handleVoiceInput}>
                    <AudioOutlined style={{ color: isRecording ? '#ef4444' : undefined }} />
                  </IconButton>
                </Tooltip>
                <Upload
                  showUploadList={false}
                  beforeUpload={() => false}
                  onChange={handleFileUpload}
                >
                  <Tooltip title={t('chatPanel.attachFile')}>
                    <IconButton>
                      <PaperClipOutlined />
                    </IconButton>
                  </Tooltip>
                </Upload>
              </ActionButtonsLeft>
              <ComposerMeta>
                {pendingAttachments.length > 0
                  ? `${pendingAttachments.length} attachment${pendingAttachments.length > 1 ? 's' : ''}`
                  : t('chatPanel.inputHint', {
                      defaultValue: inputHintFallback,
                    })}
              </ComposerMeta>
            </ActionButtons>
          </InputWrapper>
        </InputContainer>
      )}
      </ChatContentArea>
    </PanelContainer>
  );
};

export default ChatPanel;
