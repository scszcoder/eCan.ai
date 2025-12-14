import React, { useMemo, useRef, useState, useEffect } from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import ChatMessage from './retrieval/components/ChatMessage';
import { eventBus } from '@/utils/eventBus';

type MessageState = { 
  id: string; 
  role: 'user' | 'assistant'; 
  content: string;
  isThinking?: boolean;
  thinkingTime?: number | null;
  confidence?: any; // Confidence score data from backend
  rawContent?: string;
};

const RetrievalTab: React.FC = () => {
  const [messages, setMessages] = useState<MessageState[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'naive' | 'local' | 'global' | 'hybrid' | 'mix' | 'bypass'>('mix');
  const [stream, setStream] = useState(true); // Default to true for better UX
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  // Right panel parameters
  const [onlyNeedContext, setOnlyNeedContext] = useState(false);
  const [onlyNeedPrompt, setOnlyNeedPrompt] = useState(false);
  const [enableRerank, setEnableRerank] = useState(false);
  const [topK, setTopK] = useState<number | ''>('' as any);
  const [chunkTopK, setChunkTopK] = useState<number | ''>('' as any);
  const [maxEntityTokens, setMaxEntityTokens] = useState<number | ''>('' as any);
  const [maxRelationTokens, setMaxRelationTokens] = useState<number | ''>('' as any);
  const [maxTotalTokens, setMaxTotalTokens] = useState<number | ''>('' as any);
  const [historyTurns, setHistoryTurns] = useState<number | ''>('' as any);
  const [responseType, setResponseType] = useState<string>('');
  const [userPrompt, setUserPrompt] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [isHistoryLoaded, setIsHistoryLoaded] = useState(false);

  // Input history state
  const [inputHistory, setInputHistory] = useState<string[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [historyMatches, setHistoryMatches] = useState<string[]>([]);
  const inputWrapperRef = useRef<HTMLDivElement>(null);
  
  // Track composition state for IME handling
  const isComposingRef = useRef(false);

  const endRef = useRef<HTMLDivElement>(null);
  const messagesAreaRef = useRef<HTMLDivElement>(null);
  const settingsPanelRef = useRef<HTMLDivElement>(null);

  const storagePrefix = 'lightrag-ported:tabs';
  const messagesScrollKey = `${storagePrefix}:innerScroll:retrieval:messages`;
  const settingsScrollKey = `${storagePrefix}:innerScroll:retrieval:settings`;

  const restoringRef = useRef(false);

  const saveScroll = () => {
    if (messagesAreaRef.current) {
      const v = messagesAreaRef.current.scrollTop;
      const saved = Number(sessionStorage.getItem(messagesScrollKey) || 0);
      if (v > 0 || saved === 0) sessionStorage.setItem(messagesScrollKey, String(v));
    }
    if (settingsPanelRef.current) {
      const v = settingsPanelRef.current.scrollTop;
      const saved = Number(sessionStorage.getItem(settingsScrollKey) || 0);
      if (v > 0 || saved === 0) sessionStorage.setItem(settingsScrollKey, String(v));
    }
  };

  const restoreScrollWithRetry = (attempts = 0) => {
    restoringRef.current = true;
    const msgSaved = Number(sessionStorage.getItem(messagesScrollKey) || 0);
    const settingsSaved = Number(sessionStorage.getItem(settingsScrollKey) || 0);

    console.log('[RetrievalTab] Restore attempt', attempts, 'msgSaved:', msgSaved, 'settingsSaved:', settingsSaved);

    const msgEl = messagesAreaRef.current;
    const settingsEl = settingsPanelRef.current;

    console.log('[RetrievalTab] Elements:', 'msgEl:', !!msgEl, 'settingsEl:', !!settingsEl);

    // refs 可能在外层 page 切换回来时短暂为 null，必须持续重试直到元素出现
    const needMsg = msgSaved > 0;
    const needSettings = settingsSaved > 0;

    if (msgEl && needMsg) {
      msgEl.scrollTop = msgSaved;
      console.log('[RetrievalTab] Set msgEl.scrollTop to', msgSaved, 'actual:', msgEl.scrollTop);
    }
    if (settingsEl && needSettings) {
      settingsEl.scrollTop = settingsSaved;
      console.log('[RetrievalTab] Set settingsEl.scrollTop to', settingsSaved, 'actual:', settingsEl.scrollTop);
    }

    const msgOk = !needMsg || (msgEl !== null && msgEl.scrollTop === msgSaved);
    const settingsOk = !needSettings || (settingsEl !== null && settingsEl.scrollTop === settingsSaved);

    console.log('[RetrievalTab] Status:', 'msgOk:', msgOk, 'settingsOk:', settingsOk);

    // 兼容：元素尚未挂载、或 scrollTop 设置后又被后续渲染覆盖
    if ((!msgOk || !settingsOk) && attempts < 80) {
      setTimeout(() => restoreScrollWithRetry(attempts + 1), 50);
    } else {
      console.log('[RetrievalTab] Restore complete at attempt', attempts);
      // 结束恢复窗口，允许后续正常写入（包括写回 0）
      restoringRef.current = false;
    }
  };

  useEffect(() => {
    const activeTab = sessionStorage.getItem(`${storagePrefix}:active`);
    console.log('[RetrievalTab] Mount effect, activeTab:', activeTab);
    if (activeTab === 'retrieval') {
      console.log('[RetrievalTab] Starting restore on mount');
      requestAnimationFrame(() => restoreScrollWithRetry());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onActivate = (e: Event) => {
      const ce = e as CustomEvent<{ key?: string }>;
      console.log('[RetrievalTab] Activate event, key:', ce.detail?.key);
      if (ce.detail?.key === 'retrieval') {
        console.log('[RetrievalTab] Starting restore on activate');
        requestAnimationFrame(() => restoreScrollWithRetry());
      }
    };

    const onDeactivate = (e: Event) => {
      const ce = e as CustomEvent<{ key?: string }>;
      if (ce.detail?.key === 'retrieval') {
        saveScroll();
      }
    };

    window.addEventListener('lightrag-tab-activate', onActivate);
    window.addEventListener('lightrag-tab-deactivate', onDeactivate);

    const onPageHide = () => saveScroll();
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') saveScroll();
    };
    window.addEventListener('pagehide', onPageHide);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      window.removeEventListener('lightrag-tab-activate', onActivate);
      window.removeEventListener('lightrag-tab-deactivate', onDeactivate);
      window.removeEventListener('pagehide', onPageHide);
      document.removeEventListener('visibilitychange', onVisibility);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const thinkingStartTimeRef = useRef<number | null>(null);
  // Map stream_id (from backend) to message_id (frontend)
  const streamMapRef = useRef<Map<string, string>>(new Map());

  // Load history on mount
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await get_ipc_api().lightragApi.getInputHistory();
        if (res.success && Array.isArray(res.data)) {
          setInputHistory(res.data as string[]);
        }
      } catch (e) {
        console.error('Failed to load input history from backend', e);
      }
    };
    loadHistory();

    // Load default settings from LightRAG env
    const loadSettings = async () => {
      try {
        const res = await get_ipc_api().lightragApi.getSettings();
        console.log('[RetrievalTab] Loaded settings:', res);
        
        // Extract config or use empty object if failed
        const cfg = (res.success && res.data) ? (res.data as any) : {};
        
        // Use backend values if present, otherwise use hardcoded defaults
        // This ensures the UI always shows a valid value
        setTopK(Number(cfg.TOP_K ?? 40));
        setChunkTopK(Number(cfg.CHUNK_TOP_K ?? 20));
        setMaxEntityTokens(Number(cfg.MAX_ENTITY_TOKENS ?? 6000));
        setMaxRelationTokens(Number(cfg.MAX_RELATION_TOKENS ?? 8000));
        setMaxTotalTokens(Number(cfg.MAX_TOTAL_TOKENS ?? 30000));
        
        // Also respect RERANK_BY_DEFAULT
        if (cfg.RERANK_BY_DEFAULT !== undefined) {
            setEnableRerank(String(cfg.RERANK_BY_DEFAULT).toLowerCase() === 'true');
        }
      } catch (e) {
        console.error('Failed to load default settings, applying fallbacks', e);
        // Apply fallbacks on error
        setTopK(40);
        setChunkTopK(20);
        setMaxEntityTokens(6000);
        setMaxRelationTokens(8000);
        setMaxTotalTokens(30000);
      }
    };
    loadSettings();

    // Click outside handler to close history
    const handleClickOutside = (event: MouseEvent) => {
      if (inputWrapperRef.current && !inputWrapperRef.current.contains(event.target as Node)) {
        setShowHistory(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Load conversation history on mount
  useEffect(() => {
    const loadConversation = async () => {
      try {
        const res = await get_ipc_api().lightragApi.getConversationHistory();
        if (res.success && Array.isArray(res.data)) {
          setMessages(res.data as MessageState[]);
          // Only scroll to end if there's no saved scroll position to restore
          const savedMsg = Number(sessionStorage.getItem(messagesScrollKey) || 0);
          if (savedMsg === 0) {
            setTimeout(scrollToEnd, 100);
          }
        }
      } catch (e) {
        console.error('Failed to load conversation history', e);
      } finally {
        setIsHistoryLoaded(true);
      }
    };
    loadConversation();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Save conversation history when messages change (debounced)
  useEffect(() => {
    if (!isHistoryLoaded) return;

    const timer = setTimeout(async () => {
      try {
        await get_ipc_api().lightragApi.saveConversationHistory(messages);
      } catch (e) {
        console.error('Failed to save conversation history', e);
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, [messages, isHistoryLoaded]);

  // Update matches when input changes
  useEffect(() => {
    if (!input.trim()) {
      setHistoryMatches([]);
      return;
    }
    const matches = inputHistory
      .filter(h => h.toLowerCase().includes(input.toLowerCase()) && h !== input)
      .slice(0, 5);
    setHistoryMatches(matches);
    setShowHistory(matches.length > 0);
  }, [input, inputHistory]);

  const saveToHistory = async (text: string) => {
    if (!text.trim()) return;
    const newHistory = [text, ...inputHistory.filter(h => h !== text)].slice(0, 50);
    setInputHistory(newHistory);
    try {
      await get_ipc_api().lightragApi.saveInputHistory(newHistory);
    } catch (e) {
      console.error('Failed to save input history to backend', e);
    }
  };

  const scrollToEnd = () => {
    // Use requestAnimationFrame to ensure DOM update is processed
    requestAnimationFrame(() => {
        endRef.current?.scrollIntoView({ behavior: 'smooth' });
    });
  };

  useEffect(() => {
    // Subscribe to LightRAG streaming events
    const handleChunk = (data: any) => {
      const { id: streamId, chunk } = data;
      const messageId = streamMapRef.current.get(streamId);
      if (!messageId) return;

      // Handle confidence data (sent as final chunk)
      if (chunk?.confidence) {
        const shouldAnswer = chunk?.confidence?.decision?.should_answer;
        
        // Adjust confidence based on actual references data and response content
        let adjustedConfidence = { ...chunk.confidence };
        
        // Get actual references from chunk data (this is what's displayed to user)
        const actualRefs = chunk?.references || [];
        const actualRefCount = Array.isArray(actualRefs) ? actualRefs.length : 0;
        
        // IMPORTANT: Always use actual reference count, not backend's metric
        // This ensures the displayed number matches the actual References list
        if (adjustedConfidence.metrics) {
          adjustedConfidence.metrics.reference_count = actualRefCount;  // Force sync with actual refs
        }
        
        // Get the current message content to check for relevance
        const currentMessage = messages.find(m => m.id === messageId);
        const responseContent = currentMessage?.content || '';
        
        // Check if response indicates inability to answer (irrelevant references)
        const noAnswerKeywords = [
          '无法回答', '不能回答', '没有相关', '没有找到', '不知道',
          'cannot answer', 'unable to answer', 'no relevant', 'not found', "don't know",
          '知识库中没有', '文档中没有', 'no information', 'no data'
        ];
        const hasNoAnswerIndicator = noAnswerKeywords.some(keyword => 
          responseContent.toLowerCase().includes(keyword.toLowerCase())
        );
        
        // If no references, or response indicates inability to answer
        if (actualRefCount === 0 || hasNoAnswerIndicator) {
          adjustedConfidence.overall_score = 0;
          adjustedConfidence.confidence_level = 'very_low';
        } else if (actualRefCount <= 2) {
          // Very few references (1-2): cap confidence at 30%
          adjustedConfidence.overall_score = Math.min(adjustedConfidence.overall_score || 0, 0.3);
          adjustedConfidence.confidence_level = adjustedConfidence.overall_score > 0.2 ? 'low' : 'very_low';
        }
        
        setMessages(prev => prev.map(m => {
          if (m.id !== messageId) return m;
          const next: any = { ...m, confidence: adjustedConfidence };
          if (shouldAnswer === false) {
            next.rawContent = m.content;
            next.content = chunk.no_answer_message || m.content;
          }
          return next;
        }));
        return;
      }

      const textChunk = chunk?.response || '';

      setMessages(prev => prev.map(m => {
        if (m.id !== messageId) return m;

        // Merge strategy:
        // - If backend streams cumulative content, replace.
        // - If backend streams incremental deltas, append.
        const prevContent = m.content || '';
        let mergedContent = '';
        if (!prevContent) {
          mergedContent = textChunk;
        } else if (textChunk.startsWith(prevContent)) {
          mergedContent = textChunk;
        } else if (prevContent.startsWith(textChunk)) {
          mergedContent = prevContent;
        } else {
          mergedContent = prevContent + textChunk;
        }

        // Thinking timing based on merged content (robust for cumulative streams)
        let thinkingTime: number | null = m.thinkingTime ?? null;
        if (thinkingStartTimeRef.current === null && mergedContent.includes('<think>')) {
          thinkingStartTimeRef.current = Date.now();
        }
        if (thinkingStartTimeRef.current !== null && mergedContent.includes('</think>')) {
          thinkingTime = parseFloat(((Date.now() - thinkingStartTimeRef.current) / 1000).toFixed(2));
          thinkingStartTimeRef.current = null;
        }
        const currentIsThinking = thinkingStartTimeRef.current !== null;

        return {
          ...m,
          content: mergedContent,
          isThinking: currentIsThinking,
          thinkingTime,
        };
      }));
      scrollToEnd();
    };

    const handleDone = (data: any) => {
      const { id: streamId } = data;
      const messageId = streamMapRef.current.get(streamId);
      if (messageId) {
        streamMapRef.current.delete(streamId);
        setLoading(false);
        thinkingStartTimeRef.current = null;
      }
    };

    const handleError = (data: any) => {
      const { id: streamId, error } = data;
      const messageId = streamMapRef.current.get(streamId);
      if (messageId) {
        setMessages(prev => prev.map(m => 
          m.id === messageId ? { ...m, content: m.content + `\n\n[Error: ${error}]` } : m
        ));
        streamMapRef.current.delete(streamId);
        setLoading(false);
        thinkingStartTimeRef.current = null;
      }
    };

    eventBus.on('lightrag:queryStream:chunk', handleChunk);
    eventBus.on('lightrag:queryStream:done', handleDone);
    eventBus.on('lightrag:queryStream:error', handleError);

    return () => {
      eventBus.off('lightrag:queryStream:chunk', handleChunk);
      eventBus.off('lightrag:queryStream:done', handleDone);
      eventBus.off('lightrag:queryStream:error', handleError);
    };
  }, []);

  const canSend = useMemo(() => input.trim().length >= 3 && !loading, [input, loading]);

  const handleClear = async () => {
    setMessages([]);
    // Also clear input history from backend
    try {
      await get_ipc_api().lightragApi.saveInputHistory([]);
      // Conversation history will be cleared by the useEffect hook
      setInputHistory([]);
    } catch (e) {
      console.error('Failed to clear input history', e);
    }
  };

  const buildOptions = () => {
    const opts: any = { mode, stream };
    if (onlyNeedContext) opts.only_need_context = true;
    if (onlyNeedPrompt) opts.only_need_prompt = true;
    if (enableRerank) opts.enable_rerank = true;
    if (topK !== '' && !Number.isNaN(topK)) opts.top_k = Number(topK);
    if (chunkTopK !== '' && !Number.isNaN(chunkTopK)) opts.chunk_top_k = Number(chunkTopK);
    if (maxEntityTokens !== '' && !Number.isNaN(maxEntityTokens)) opts.max_entity_tokens = Number(maxEntityTokens);
    if (maxRelationTokens !== '' && !Number.isNaN(maxRelationTokens)) opts.max_relation_tokens = Number(maxRelationTokens);
    if (maxTotalTokens !== '' && !Number.isNaN(maxTotalTokens)) opts.max_total_tokens = Number(maxTotalTokens);
    if (historyTurns !== '' && !Number.isNaN(historyTurns)) opts.history_turns = Number(historyTurns);
    if (responseType.trim()) opts.response_type = responseType.trim();
    if (userPrompt.trim()) opts.user_prompt = userPrompt.trim();
    
    // Pass history
    if (historyTurns !== '' && Number(historyTurns) > 0 && messages.length > 0) {
        opts.conversation_history = messages.slice(-Number(historyTurns) * 2).map(m => ({ role: m.role, content: m.content }));
    }
    
    return opts;
  };

  const handleSend = async () => {
    if (!canSend) return;
    saveToHistory(input);
    setShowHistory(false);
    
    const userMsg: MessageState = { 
        id: crypto.randomUUID?.() || String(Date.now()), 
        role: 'user', 
        content: input 
    };
    
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    thinkingStartTimeRef.current = null;
    
    const assistantId = crypto.randomUUID?.() || String(Date.now() + 1);
    const assistantMsg: MessageState = { 
        id: assistantId, 
        role: 'assistant', 
        content: '', 
        isThinking: false,
        thinkingTime: null
    };
    setMessages(prev => [...prev, assistantMsg]);
    
    const options = buildOptions();
    
    try {
      if (stream) {
        // Use streaming query
        const response = await get_ipc_api().lightragApi.queryStream({ text: userMsg.content, options });
        
        if (response.success && response.data) {
          const res = response.data as any;
          // Backend returns { status: 'streaming_started', stream_id: '...' }
          if (res.stream_id) {
            streamMapRef.current.set(res.stream_id, assistantId);
          } else {
             throw new Error('No stream_id returned from backend');
          }
        } else {
            throw new Error(response.error?.message || 'Unknown error');
        }
      } else {
        // Use normal query (unchanged)
        const response = await get_ipc_api().lightragApi.query({ text: userMsg.content, options });
        
        if (response.success && response.data) {
            const res = response.data as any;
            // Normal query returns { status: 'success', data: result }
            // The actual result is usually inside res.data
            let resultData: any;
            if (res && typeof res === 'object' && 'data' in res) {
              resultData = (res as any).data;
            } else {
              resultData = res;
            }

            let content: string;

            // If backend returns a structured result like { response: string, references: [...] }
            // show the human-friendly response field instead of raw JSON
            if (resultData && typeof resultData === 'object' && 'response' in resultData) {
              const resp = (resultData as any).response;
              const base = typeof resp === 'string' ? resp : JSON.stringify(resp);
              const refs = (resultData as any).references;
              const hasRefs = Array.isArray(refs) && refs.length > 0;

              const confidence = (resultData as any)?.confidence;
              const shouldAnswer = confidence?.decision?.should_answer;

              const hasReferencesSection = /(^|\n)\s*(references|reference|参考文档|参考资料)\s*[:：]?/i.test(base);

              if (shouldAnswer === false) {
                content = base;
              } else if (hasRefs && !hasReferencesSection) {
                // Build a simple human-readable reference list
                const refLines = refs.map((r: any, idx: number) => {
                  if (!r || typeof r !== 'object') {
                    return `- [${idx + 1}] ` + String(r);
                  }

                  const title = (r.title || r.name || r.filename || r.file_name) as string | undefined;
                  const source = (r.source || r.doc_id || r.document_id || r.id) as string | undefined;
                  const score = (r.score ?? r.similarity) as number | undefined;

                  let label = title || source || JSON.stringify(r).slice(0, 80) + '...';
                  if (source && title && source !== title) {
                    label = `${title} (${source})`;
                  }
                  if (score !== undefined) {
                    return `- [${idx + 1}] ${label}  (score: ${score.toFixed ? score.toFixed(3) : score})`;
                  }
                  return `- [${idx + 1}] ${label}`;
                });

                content = `${base}\n\n参考文档：\n${refLines.join('\n')}`;
              } else if (!hasReferencesSection) {
                // When there is no reference, append a friendly hint line
                content = base + '\n\n(没有检索到相关文档引用)';
              } else {
                content = base;
              }
            } else if (typeof resultData === 'string') {
              content = resultData;
            } else {
              content = JSON.stringify(resultData);
            }

            // Extract confidence if present
            let confidence = resultData?.confidence;
            
            // Adjust confidence based on actual references data and response content (non-streaming mode)
            if (confidence) {
              // Get actual references from result data (this is what's displayed to user)
              const actualRefs = (resultData as any)?.references || [];
              const actualRefCount = Array.isArray(actualRefs) ? actualRefs.length : 0;
              
              // IMPORTANT: Always use actual reference count, not backend's metric
              // This ensures the displayed number matches the actual References list
              confidence = {
                ...confidence,
                metrics: {
                  ...confidence.metrics,
                  reference_count: actualRefCount  // Force sync with actual refs
                }
              };
              
              // Check if response indicates inability to answer (irrelevant references)
              const noAnswerKeywords = [
                '无法回答', '不能回答', '没有相关', '没有找到', '不知道',
                'cannot answer', 'unable to answer', 'no relevant', 'not found', "don't know",
                '知识库中没有', '文档中没有', 'no information', 'no data'
              ];
              const hasNoAnswerIndicator = noAnswerKeywords.some(keyword => 
                content.toLowerCase().includes(keyword.toLowerCase())
              );
              
              // If no references, or response indicates inability to answer
              if (actualRefCount === 0 || hasNoAnswerIndicator) {
                confidence.overall_score = 0;
                confidence.confidence_level = 'very_low';
              } else if (actualRefCount <= 2) {
                // Very few references (1-2): cap confidence at 30%
                confidence.overall_score = Math.min(confidence.overall_score || 0, 0.3);
                confidence.confidence_level = confidence.overall_score > 0.2 ? 'low' : 'very_low';
              }
            }

            const shouldAnswer = confidence?.decision?.should_answer;
            const rawResponse = resultData?.raw_response;
            setMessages(prev => prev.map(m => 
              m.id === assistantId ? { ...m, content, confidence, rawContent: shouldAnswer === false ? rawResponse : undefined } : m
            ));
            setLoading(false); // Stop loading for normal request
        } else {
            throw new Error(response.error?.message || 'Unknown error');
        }
      }
      scrollToEnd();
    } catch (e: any) {
      setMessages(prev => prev.map(m => 
        m.id === assistantId ? { ...m, content: `Error: ${e?.message || String(e)}` } : m
      ));
      setLoading(false);
      thinkingStartTimeRef.current = null;
    }
  };

  return (
    <div style={{ 
      padding: '32px', 
      height: '100%', 
      display: 'flex', 
      gap: 20,
      background: token.colorBgLayout
    }} data-ec-scope="lightrag-ported">
      {/* Left panel */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* Messages area */}
        <div 
          ref={messagesAreaRef}
          onScroll={(e) => {
            const v = e.currentTarget.scrollTop;
            const saved = Number(sessionStorage.getItem(messagesScrollKey) || 0);
            if (restoringRef.current && v === 0 && saved > 0) return;
            if (v > 0 || saved === 0) sessionStorage.setItem(messagesScrollKey, String(v));
          }}
          style={{ 
            flex: 1, 
            minHeight: 0, 
            border: `1px solid ${token.colorBorder}`, 
            borderRadius: 16, 
            padding: 20, 
            overflow: 'auto', 
            background: token.colorBgContainer,
            boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
          }}
        >
          {messages.length === 0 ? (
            <div style={{ 
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              height: '100%',
              color: token.colorTextTertiary,
              gap: 12
            }}>
              <div style={{ fontSize: 48, opacity: 0.3 }}>💬</div>
              <div style={{ fontSize: 15, fontWeight: 600 }}>{t('pages.knowledge.retrieval.startConversation')}</div>
              <div style={{ fontSize: 13 }}>{t('pages.knowledge.retrieval.startConversationDesc')}</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {messages.map((m, idx) => (
                <ChatMessage 
                    key={m.id}
                    role={m.role}
                    content={m.content}
                    isThinking={m.isThinking}
                    thinkingTime={m.thinkingTime}
                    loading={loading && idx === messages.length - 1 && m.role === 'assistant'}
                    confidence={m.confidence}
                    rawContent={m.rawContent}
                />
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>
        {/* Input row */}
        <div style={{ 
          display: 'flex', 
          gap: 10, 
          padding: '16px 20px',
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: 16,
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
        }}>
          <button className="ec-btn" onClick={handleClear} disabled={loading} title={t('pages.knowledge.retrieval.clearConversation')}>
            <ClearOutlined /> {t('pages.knowledge.documents.clear')}
          </button>
          <div style={{ flex: 1, position: 'relative' }} ref={inputWrapperRef}>
            <textarea
              className="ec-input"
              rows={2}
              placeholder={t('pages.knowledge.retrieval.inputPlaceholder')}
              value={input}
              onChange={e => setInput(e.target.value)}
              onFocus={() => {
                if (input.trim() && historyMatches.length > 0) setShowHistory(true);
              }}
              onCompositionStart={() => { isComposingRef.current = true; }}
              onCompositionEnd={() => { isComposingRef.current = false; }}
              onKeyDown={(e) => { 
                if (isComposingRef.current || e.nativeEvent.isComposing) return;
                
                // Enter to send (prevent default newline)
                // Allow Shift+Enter for newline
                if (e.key === 'Enter' && !e.shiftKey) { 
                  e.preventDefault(); 
                  handleSend(); 
                }
                
                if (e.key === 'Escape') setShowHistory(false);
              }}
              style={{ width: '100%', resize: 'none', border: 'none', padding: '8px 0', background: 'transparent' }}
            />
            {showHistory && historyMatches.length > 0 && (
              <div className="history-dropdown">
                {historyMatches.map((match, idx) => (
                  <div 
                    key={idx} 
                    className="history-item"
                    onClick={() => {
                      setInput(match);
                      setShowHistory(false);
                      // Optional: auto-focus back to textarea
                    }}
                  >
                    {match}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button className="ec-btn ec-btn-primary" onClick={handleSend} disabled={!canSend} title={t('pages.knowledge.retrieval.sendMessage')}>
            <SendOutlined /> {t('common.send')}
          </button>
        </div>
      </div>

      {/* Right panel - parameters */}
      <div style={{ 
        width: 320, 
        flexShrink: 0, 
        border: `1px solid ${token.colorBorder}`, 
        borderRadius: 16, 
        background: token.colorBgContainer, 
        display: 'flex', 
        flexDirection: 'column', 
        maxHeight: '100%', 
        overflow: 'hidden',
        boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>⚙️ {t('pages.knowledge.retrieval.querySettings')}</h4>
        </div>
        <div 
          ref={settingsPanelRef}
          onScroll={(e) => {
            const v = e.currentTarget.scrollTop;
            const saved = Number(sessionStorage.getItem(settingsScrollKey) || 0);
            if (restoringRef.current && v === 0 && saved > 0) return;
            if (v > 0 || saved === 0) sessionStorage.setItem(settingsScrollKey, String(v));
          }}
          style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}
        >
          <div className="param-group">
            <div className="param-group-title">{t('pages.knowledge.retrieval.customPrompt')}</div>
            <textarea 
              className="ec-input" 
              value={userPrompt} 
              onChange={e => setUserPrompt(e.target.value)} 
              placeholder={t('pages.knowledge.retrieval.customPromptPlaceholder')}
              rows={3}
              style={{ resize: 'vertical', minHeight: 60 }}
            />
          </div>

          <div className="param-group">
            <div className="param-group-title">{t('pages.knowledge.retrieval.basic')}</div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.mode')}</label>
              <select className="ec-input ec-select" value={mode} onChange={e => setMode(e.target.value as any)}>
                <option value="naive">{t('pages.knowledge.retrieval.modes.naive')}</option>
                <option value="local">{t('pages.knowledge.retrieval.modes.local')}</option>
                <option value="global">{t('pages.knowledge.retrieval.modes.global')}</option>
                <option value="hybrid">{t('pages.knowledge.retrieval.modes.hybrid')}</option>
                <option value="mix">{t('pages.knowledge.retrieval.modes.mix')}</option>
                <option value="bypass">{t('pages.knowledge.retrieval.modes.bypass')}</option>
              </select>
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.responseType')}</label>
              <input className="ec-input" value={responseType} onChange={e => setResponseType(e.target.value)} placeholder={t('pages.knowledge.retrieval.responseTypePlaceholder')} />
            </div>
          </div>
          
          <div className="param-group">
            <div className="param-group-title">{t('pages.knowledge.retrieval.advanced')}</div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.topK')}</label>
              <input className="ec-input" type="number" value={topK as any} onChange={e => setTopK(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.chunkTopK')}</label>
              <input className="ec-input" type="number" value={chunkTopK as any} onChange={e => setChunkTopK(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.maxEntityTokens')}</label>
              <input className="ec-input" type="number" value={maxEntityTokens as any} onChange={e => setMaxEntityTokens(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.maxRelationTokens')}</label>
              <input className="ec-input" type="number" value={maxRelationTokens as any} onChange={e => setMaxRelationTokens(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.maxTotalTokens')}</label>
              <input className="ec-input" type="number" value={maxTotalTokens as any} onChange={e => setMaxTotalTokens(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
            <div className="param-row">
              <label>{t('pages.knowledge.retrieval.historyTurns')}</label>
              <input className="ec-input" type="number" value={historyTurns as any} onChange={e => setHistoryTurns(e.target.value === '' ? '' : Number(e.target.value))} placeholder={t('pages.knowledge.retrieval.defaultPlaceholder')} />
            </div>
          </div>
          
          <div className="param-group">
            <div className="param-group-title">{t('pages.knowledge.retrieval.options')}</div>
            <label className="checkbox-label">
              <input type="checkbox" checked={stream} onChange={e => setStream(e.target.checked)} />
              <span>{t('pages.knowledge.retrieval.streamResponse')}</span>
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={enableRerank} onChange={e => setEnableRerank(e.target.checked)} />
              <span>{t('pages.knowledge.retrieval.enableRerank')}</span>
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={onlyNeedContext} onChange={e => setOnlyNeedContext(e.target.checked)} />
              <span>{t('pages.knowledge.retrieval.onlyNeedContext')}</span>
            </label>
            <label className="checkbox-label">
              <input type="checkbox" checked={onlyNeedPrompt} onChange={e => setOnlyNeedPrompt(e.target.checked)} />
              <span>{t('pages.knowledge.retrieval.onlyNeedPrompt')}</span>
            </label>
          </div>
        </div>
      </div>

      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 8px;
          padding: 8px 12px;
          box-sizing: border-box;
          font-size: 13px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }
        [data-ec-scope="lightrag-ported"] .ec-input:focus {
          outline: none;
          border-color: ${token.colorPrimary};
          box-shadow: 0 0 0 2px ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 8px;
          padding: 8px 12px;
          cursor: pointer;
          font-size: 13px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          min-width: 40px;
          box-shadow: ${isDark ? '0 2px 8px rgba(0, 0, 0, 0.15)' : '0 2px 8px rgba(0, 0, 0, 0.05)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
          transform: translateY(-2px);
          box-shadow: ${isDark ? '0 4px 12px rgba(24, 144, 255, 0.3)' : '0 4px 12px rgba(24, 144, 255, 0.2)'};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
          transform: translateY(-2px);
          box-shadow: 0 6px 16px rgba(24, 144, 255, 0.4);
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        [data-ec-scope="lightrag-ported"] .param-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        [data-ec-scope="lightrag-ported"] .param-group-title {
          font-size: 11px;
          font-weight: 700;
          color: ${token.colorTextSecondary};
          text-transform: uppercase;
          letter-spacing: 0.5px;
          margin-bottom: 2px;
        }
        [data-ec-scope="lightrag-ported"] .param-row { 
          display: flex; 
          flex-direction: column; 
          gap: 4px; 
          width: 100%; 
        }
        [data-ec-scope="lightrag-ported"] .param-row > label { 
          font-size: 12px; 
          font-weight: 500;
          color: ${token.colorTextSecondary};
        }
        [data-ec-scope="lightrag-ported"] .param-row > .ec-input,
        [data-ec-scope="lightrag-ported"] .param-row select.ec-input,
        [data-ec-scope="lightrag-ported"] .param-row input.ec-input {
          width: 100%;
        }
        [data-ec-scope="lightrag-ported"] .checkbox-label {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 6px 10px;
          background: ${isDark ? token.colorBgElevated : token.colorBgLayout};
          border-radius: 6px;
          cursor: pointer;
          transition: all 0.2s;
          font-size: 12px;
          color: ${token.colorText};
        }
        [data-ec-scope="lightrag-ported"] .checkbox-label:hover {
          background: ${token.colorPrimaryBg};
        }
        [data-ec-scope="lightrag-ported"] .checkbox-label input[type="checkbox"] {
          margin: 0;
          cursor: pointer;
        }
        [data-ec-scope="lightrag-ported"] .ec-select {
          cursor: pointer;
        }
        [data-ec-scope="lightrag-ported"] .history-dropdown {
          position: absolute;
          bottom: 100%;
          left: 0;
          width: 100%;
          max-height: 200px;
          overflow-y: auto;
          background: ${token.colorBgElevated};
          border: 1px solid ${token.colorBorder};
          border-radius: 8px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
          z-index: 1000;
          margin-bottom: 8px;
        }
        [data-ec-scope="lightrag-ported"] .history-item {
          padding: 8px 12px;
          cursor: pointer;
          font-size: 13px;
          color: ${token.colorText};
          border-bottom: 1px solid ${token.colorBorderSecondary};
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          transition: background 0.2s;
        }
        [data-ec-scope="lightrag-ported"] .history-item:last-child {
          border-bottom: none;
        }
        [data-ec-scope="lightrag-ported"] .history-item:hover {
          background: ${token.colorBgTextHover};
        }
      `}</style>
    </div>
  );
};

export default RetrievalTab;
