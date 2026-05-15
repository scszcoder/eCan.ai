import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Tooltip, Typography, message as antdMessage } from 'antd';
import {
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  CheckOutlined,
  CloseOutlined,
  LoadingOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { IPCAPI, type APIResponse } from '../../../services/ipc/api';
import type { Prompt, PromptAgentChatMessage } from '../types';

interface PromptAgentChatProps {
  /**
   * The prompt currently being edited. Chat is keyed off `prompt.id`;
   * switching to a different prompt loads its persisted history.
   * Null when no prompt is selected (chat is disabled in that state).
   */
  prompt: Prompt | null;
  /**
   * Called when the user clicks "Apply" on a proposed change card.
   * The parent is responsible for mutating the prompt body (typically
   * by switching the editor to Markdown mode and overwriting mdContent).
   */
  onApplyProposedChange: (proposedMdContent: string) => void;
  /**
   * Called whenever the chat history changes (new turn, applied edit,
   * cleared, etc.).  Parent persists this on the prompt JSON.
   */
  onHistoryChange: (history: PromptAgentChatMessage[]) => void;
  /** Hide the panel entirely when the parent collapses it. */
  hidden?: boolean;
}

const Msg = Typography.Text;
const { TextArea } = Input;

/**
 * Bottom-of-page chat panel that drives the prompt-agent LangGraph
 * on the backend.  See `gui/ipc/w2p_handlers/prompt_agent_chat_handler.py`.
 *
 * Design notes:
 *   - History is per-prompt and persisted via `onHistoryChange`.
 *   - Assistant turns may include a `proposedMdContent`; we render
 *     an inline Apply / Discard card so the user can review before
 *     mutating their actual prompt.
 *   - We send the editor's CURRENT mdContent as part of the request
 *     so the agent's edits are anchored to whatever the user is
 *     looking at (including any unsaved tweaks they just made).
 */
const PromptAgentChat: React.FC<PromptAgentChatProps> = ({
  prompt,
  onApplyProposedChange,
  onHistoryChange,
  hidden,
}) => {
  const { t } = useTranslation();
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<any>(null);

  // Local mirror of the persisted history so the textarea-empty/send-disabled
  // logic doesn't depend on parent re-render timing.
  const [localHistory, setLocalHistory] = useState<PromptAgentChatMessage[]>(
    prompt?.agentChatHistory || []
  );

  // Resync when the selected prompt changes.
  useEffect(() => {
    setLocalHistory(prompt?.agentChatHistory || []);
    setInput('');
  }, [prompt?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pin scroll to bottom whenever the thread grows.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [localHistory.length]);

  const promptDisabled = !prompt || !!prompt.readOnly;
  const sendDisabled = promptDisabled || sending || !input.trim();

  const pushHistory = useCallback(
    (next: PromptAgentChatMessage[]) => {
      setLocalHistory(next);
      onHistoryChange(next);
    },
    [onHistoryChange]
  );

  const handleSend = useCallback(async () => {
    if (sendDisabled || !prompt) return;
    const text = input.trim();
    if (!text) return;

    const userMsg: PromptAgentChatMessage = {
      id: `u-${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    const optimistic = [...localHistory, userMsg];
    pushHistory(optimistic);
    setInput('');
    setSending(true);

    // Always send the LATEST mdContent so the agent's diff is anchored
    // to what's in front of the user right now.  Fall back to a
    // reconstructed body from sections when the prompt is JSON-mode
    // (the agent still gets text it can edit).
    const currentMd =
      prompt.mdContent ||
      reconstructMdFromSections(prompt) ||
      '';

    try {
      const res: APIResponse<{
        assistant_message: string;
        proposed_md_content: string;
        raw_llm_output: string;
        model: { provider_id: string; model_name: string };
      }> = await IPCAPI.getInstance().promptAgentChat({
        prompt_id: prompt.id,
        user_message: text,
        current_md_content: currentMd,
        history: optimistic.slice(-20).map((m) => ({
          role: m.role,
          content: m.content,
        })),
      });

      if (!res.success || !res.data) {
        const errMsg = res.error?.message || t('common.error', { defaultValue: 'Unknown error' });
        const failMsg: PromptAgentChatMessage = {
          id: `e-${Date.now()}`,
          role: 'assistant',
          content: `⚠️ ${errMsg}`,
          timestamp: new Date().toISOString(),
        };
        pushHistory([...optimistic, failMsg]);
        antdMessage.error(errMsg);
        return;
      }

      const reply: PromptAgentChatMessage = {
        id: `a-${Date.now()}-${Math.floor(Math.random() * 1e6)}`,
        role: 'assistant',
        content: res.data.assistant_message || '(empty response)',
        timestamp: new Date().toISOString(),
        proposedMdContent: res.data.proposed_md_content || undefined,
      };
      pushHistory([...optimistic, reply]);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      const failMsg: PromptAgentChatMessage = {
        id: `e-${Date.now()}`,
        role: 'assistant',
        content: `⚠️ ${errMsg}`,
        timestamp: new Date().toISOString(),
      };
      pushHistory([...optimistic, failMsg]);
      antdMessage.error(errMsg);
    } finally {
      setSending(false);
      // Give the textarea focus back for fast follow-ups.
      requestAnimationFrame(() => inputRef.current?.focus?.());
    }
  }, [sendDisabled, prompt, input, localHistory, pushHistory, t]);

  const handleApply = useCallback(
    (msgId: string, proposed: string) => {
      onApplyProposedChange(proposed);
      // Mark this turn as applied so the Apply/Discard card collapses.
      const next = localHistory.map((m) =>
        m.id === msgId ? { ...m, proposedMdContent: undefined } : m
      );
      pushHistory(next);
      antdMessage.success(
        t('pages.prompts.agentChat.applied', { defaultValue: 'Applied to editor' })
      );
    },
    [localHistory, onApplyProposedChange, pushHistory, t]
  );

  const handleDiscard = useCallback(
    (msgId: string) => {
      const next = localHistory.map((m) =>
        m.id === msgId ? { ...m, proposedMdContent: undefined } : m
      );
      pushHistory(next);
    },
    [localHistory, pushHistory]
  );

  const handleClearHistory = useCallback(() => {
    pushHistory([]);
  }, [pushHistory]);

  const placeholder = useMemo(() => {
    if (!prompt) {
      return t('pages.prompts.agentChat.noPrompt', {
        defaultValue: 'Select a prompt to chat with the agent…',
      });
    }
    if (prompt.readOnly) {
      return t('pages.prompts.agentChat.readonly', {
        defaultValue: 'This prompt is read-only — clone it first to edit with the agent.',
      });
    }
    return t('pages.prompts.agentChat.placeholder', {
      defaultValue:
        'Describe a change in natural language (e.g. "make the role more formal", "add a tone section saying always reply in Chinese")…',
    });
  }, [prompt, t]);

  if (hidden) return null;

  return (
    <div
      style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(15, 23, 42, 0.55)',
        borderTop: '1px solid rgba(148, 163, 184, 0.2)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 12px',
          borderBottom: '1px solid rgba(148, 163, 184, 0.14)',
          background: 'rgba(30, 41, 59, 0.6)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <RobotOutlined style={{ color: '#60a5fa' }} />
          <Msg strong style={{ color: '#e2e8f0', fontSize: 13 }}>
            {t('pages.prompts.agentChat.title', { defaultValue: 'Prompt Agent' })}
          </Msg>
          {localHistory.length > 0 && (
            <Msg style={{ color: 'rgba(148,163,184,0.7)', fontSize: 11 }}>
              ({localHistory.length} {t('pages.prompts.agentChat.turns', { defaultValue: 'turns' })})
            </Msg>
          )}
        </div>
        <Tooltip title={t('pages.prompts.agentChat.clear', { defaultValue: 'Clear conversation' })}>
          <Button
            type="text"
            size="small"
            icon={<DeleteOutlined />}
            onClick={handleClearHistory}
            disabled={localHistory.length === 0 || promptDisabled}
            style={{ color: 'rgba(148,163,184,0.8)' }}
          />
        </Tooltip>
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          padding: '8px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {localHistory.length === 0 ? (
          <div
            style={{
              color: 'rgba(148,163,184,0.65)',
              fontSize: 12,
              padding: '12px 4px',
              fontStyle: 'italic',
            }}
          >
            {t('pages.prompts.agentChat.empty', {
              defaultValue:
                'Ask the agent to draft, refine, or restructure your prompt. Your conversation is saved per prompt.',
            })}
          </div>
        ) : (
          localHistory.map((m) => <MessageBubble key={m.id} message={m} onApply={handleApply} onDiscard={handleDiscard} />)
        )}
        {sending && (
          <div style={{ color: '#60a5fa', fontSize: 12, padding: '4px 8px' }}>
            <LoadingOutlined /> {t('pages.prompts.agentChat.thinking', { defaultValue: 'Thinking…' })}
          </div>
        )}
      </div>

      {/* Input row */}
      <div
        style={{
          padding: '8px 12px',
          borderTop: '1px solid rgba(148, 163, 184, 0.14)',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
          background: 'rgba(15, 23, 42, 0.7)',
        }}
      >
        <TextArea
          ref={inputRef as any}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          autoSize={{ minRows: 1, maxRows: 4 }}
          disabled={promptDisabled || sending}
          onKeyDown={(e) => {
            // Cmd/Ctrl+Enter to send, plain Enter inserts a newline.
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleSend();
            }
          }}
          style={{
            background: 'rgba(30, 41, 59, 0.6)',
            borderColor: 'rgba(148, 163, 184, 0.25)',
            color: '#e2e8f0',
            resize: 'none',
          }}
        />
        <Tooltip
          title={t('pages.prompts.agentChat.sendHint', {
            defaultValue: 'Send (Ctrl+Enter / ⌘+Enter)',
          })}
        >
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={sendDisabled}
            loading={sending}
          />
        </Tooltip>
      </div>
    </div>
  );
};

// ───────────────────────────────────────────────────────────────────────────
// Sub-components
// ───────────────────────────────────────────────────────────────────────────

const MessageBubble: React.FC<{
  message: PromptAgentChatMessage;
  onApply: (msgId: string, proposed: string) => void;
  onDiscard: (msgId: string) => void;
}> = ({ message, onApply, onDiscard }) => {
  const { t } = useTranslation();
  const isUser = message.role === 'user';
  return (
    <div
      style={{
        display: 'flex',
        gap: 8,
        flexDirection: isUser ? 'row-reverse' : 'row',
        alignItems: 'flex-start',
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 24,
          height: 24,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: isUser ? 'rgba(59, 130, 246, 0.25)' : 'rgba(96, 165, 250, 0.18)',
          color: isUser ? '#93c5fd' : '#60a5fa',
          fontSize: 12,
        }}
      >
        {isUser ? <UserOutlined /> : <RobotOutlined />}
      </div>
      <div style={{ maxWidth: '85%', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div
          style={{
            padding: '6px 10px',
            borderRadius: 8,
            background: isUser ? 'rgba(59, 130, 246, 0.18)' : 'rgba(30, 41, 59, 0.85)',
            border: isUser ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid rgba(148, 163, 184, 0.18)',
            color: '#e2e8f0',
            fontSize: 13,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {message.content}
        </div>
        {!isUser && message.proposedMdContent && (
          <ProposedChangeCard
            proposed={message.proposedMdContent}
            onApply={() => onApply(message.id, message.proposedMdContent!)}
            onDiscard={() => onDiscard(message.id)}
            applyLabel={t('common.apply', { defaultValue: 'Apply' })}
            discardLabel={t('common.discard', { defaultValue: 'Discard' })}
            previewLabel={t('pages.prompts.agentChat.proposedPreview', {
              defaultValue: 'Proposed prompt body',
            })}
          />
        )}
      </div>
    </div>
  );
};

const ProposedChangeCard: React.FC<{
  proposed: string;
  onApply: () => void;
  onDiscard: () => void;
  applyLabel: string;
  discardLabel: string;
  previewLabel: string;
}> = ({ proposed, onApply, onDiscard, applyLabel, discardLabel, previewLabel }) => {
  const [expanded, setExpanded] = useState(false);
  const charCount = proposed.length;
  return (
    <div
      style={{
        border: '1px solid rgba(96, 165, 250, 0.35)',
        background: 'rgba(15, 23, 42, 0.85)',
        borderRadius: 8,
        padding: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Msg strong style={{ color: '#60a5fa', fontSize: 12 }}>
          ✎ {previewLabel} <span style={{ color: 'rgba(148,163,184,0.6)', fontWeight: 400 }}>({charCount} chars)</span>
        </Msg>
        <div style={{ display: 'flex', gap: 4 }}>
          <Button size="small" type="text" onClick={() => setExpanded((v) => !v)} style={{ color: 'rgba(148,163,184,0.85)' }}>
            {expanded ? '▼' : '▶'}
          </Button>
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={onApply}>
            {applyLabel}
          </Button>
          <Button size="small" icon={<CloseOutlined />} onClick={onDiscard}>
            {discardLabel}
          </Button>
        </div>
      </div>
      {expanded && (
        <pre
          style={{
            margin: 0,
            padding: 8,
            background: 'rgba(0,0,0,0.35)',
            border: '1px solid rgba(148,163,184,0.15)',
            borderRadius: 6,
            maxHeight: 200,
            overflow: 'auto',
            color: '#cbd5e1',
            fontSize: 11,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {proposed}
        </pre>
      )}
    </div>
  );
};

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

/**
 * Build a Markdown approximation of a JSON-format prompt so the agent
 * has something coherent to edit even when the user hasn't toggled to
 * Markdown mode yet.  This is intentionally simple — the real preview
 * generator lives in PromptsDetail and would be overkill here.
 */
function reconstructMdFromSections(p: Prompt): string {
  if (!p) return '';
  const out: string[] = [];
  if (p.title) out.push(`# ${p.title}`, '');
  for (const sec of p.sections || []) {
    if (!sec.items || sec.items.length === 0) continue;
    out.push(`## ${sec.type}`);
    for (const item of sec.items) {
      if (item && item.trim()) out.push(`- ${item}`);
    }
    out.push('');
  }
  return out.join('\n');
}

export default PromptAgentChat;
