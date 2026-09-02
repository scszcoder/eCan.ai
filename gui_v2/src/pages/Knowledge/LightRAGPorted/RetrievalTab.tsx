import React, { useMemo, useRef, useState, useEffect } from 'react';
import { App, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';
import ChatMessage from './retrieval/components/ChatMessage';
import WorkspacePicker from './WorkspacePicker';
import { useWorkspace } from './useWorkspace';
import { eventBus } from '@/utils/eventBus';
import { fileDownloadProtocol } from '@/utils/fileDownloadProtocol';

type MessageState = { 
  id: string; 
  role: 'user' | 'assistant'; 
  content: string;
  isThinking?: boolean;
  thinkingTime?: number | null;
  confidence?: any; // Confidence score data from backend
  rawContent?: string;
  retrievalMetrics?: {
    elapsedMs?: number | null;
    firstTokenMs?: number | null;
  };
};

const RetrievalTab: React.FC = () => {
  const [messages, setMessages] = useState<MessageState[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'naive' | 'local' | 'global' | 'hybrid' | 'mix' | 'bypass'>('mix');
  const [stream, setStream] = useState(true); // Default to true for better UX
  // Shared LightRAG workspace (tenant). Backed by useWorkspace() so the
  // header picker, this picker, and DocumentsTab stay in lockstep.
  // Empty = server default.
  const [workspace, setWorkspace] = useWorkspace();
  const { t } = useTranslation();
  const { message: messageApi } = App.useApp();
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
  const streamTextRef = useRef<Record<string, string>>({});
  const streamFlushTimerRef = useRef<Record<string, number>>({});

  // Initialize file download protocol for LightRAG
  useEffect(() => {
    // 设置下载处理器
    fileDownloadProtocol.setDownloadHandler({
      downloadFile: async (fileName: string) => {
        const api = get_ipc_api();
        const result = await api.lightragApi.downloadFile<{ filePath: string; fileName: string }>({
          fileName
        });
        if (!result.success || !result.data) {
          throw new Error(result.error?.message || t('pages.knowledge.retrieval.downloadFailed', { error: 'Unknown error' }));
        }
        return result.data;
      },
      t,
      message: messageApi,
    });
    
    // 初始化协议处理器
    fileDownloadProtocol.init();
    
    return () => {
      fileDownloadProtocol.cleanup();
    };
  }, [messageApi, t]);

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
        // Updated for 8K context models (Qwen3.8-27B-AWQ-INT4): entity+relation
        // tokens must be capped so chunks can load without exceeding the context window.
        setTopK(Number(cfg.TOP_K ?? 10));
        setChunkTopK(Number(cfg.CHUNK_TOP_K ?? 12));
        setMaxEntityTokens(Number(cfg.MAX_ENTITY_TOKENS ?? 2000));
        setMaxRelationTokens(Number(cfg.MAX_RELATION_TOKENS ?? 2500));
        setMaxTotalTokens(Number(cfg.MAX_TOTAL_TOKENS ?? 30000));
        
        // Also respect RERANK_BY_DEFAULT
        if (cfg.RERANK_BY_DEFAULT !== undefined) {
            setEnableRerank(String(cfg.RERANK_BY_DEFAULT).toLowerCase() === 'true');
        }
      } catch (e) {
        console.error('Failed to load default settings, applying fallbacks', e);
        // Apply fallbacks on error - adjusted for 8K context models
        setTopK(10);
        setChunkTopK(12);
        setMaxEntityTokens(2000);
        setMaxRelationTokens(2500);
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
      if (!messageId) {
        console.warn('[RetrievalTab] Received chunk for unknown stream:', streamId);
        return;
      }
      
      console.log('[RetrievalTab] 💬 handleChunk received:', { streamId, hasChunk: !!chunk, chunkType: typeof chunk });

      if (chunk?.metrics) {
        setMessages(prev => prev.map(m => m.id === messageId ? {
          ...m,
          retrievalMetrics: {
            elapsedMs: chunk.metrics.elapsed_ms ?? null,
            firstTokenMs: chunk.metrics.time_to_first_token_ms ?? null,
          },
        } : m));
        return;
      }

      // Handle confidence data (can come with or without references)
      if (chunk?.confidence) {
        console.log('[RetrievalTab] 🎯 Received confidence data:', chunk.confidence);
        
        // Normalize confidence data to support different model formats
        const rawConfidence = chunk.confidence;
        const adjustedConfidence = {
          ...rawConfidence,
          // Support multiple field names for overall score
          overall_score: rawConfidence.overall_score ?? rawConfidence.score ?? rawConfidence.confidence ?? 0,
          // Support multiple field names for confidence level
          confidence_level: rawConfidence.confidence_level ?? rawConfidence.level ?? 'unknown',
          // Preserve decision if exists
          decision: rawConfidence.decision ?? {}
        };
        
        const shouldAnswer = adjustedConfidence?.decision?.should_answer;
        
        console.log('[RetrievalTab] 🎯 Normalized overall_score:', adjustedConfidence.overall_score);
        console.log('[RetrievalTab] 🎯 Should answer:', shouldAnswer);
        
        setMessages(prev => prev.map(m => {
          if (m.id !== messageId) return m;
          const next: any = { ...m, confidence: adjustedConfidence };
          if (shouldAnswer === false) {
            next.rawContent = m.content;
            next.content = chunk.no_answer_message || m.content;
          }
          return next;
        }));
      }
      
      // Store references if present in chunk
      if (chunk?.references) {
        console.log('[RetrievalTab] 📚 Received references:', chunk.references);
        console.log('[RetrievalTab] 📊 First reference structure:', chunk.references[0]);
        
        setMessages(prev => prev.map(m => 
          m.id === messageId ? { ...m, references: chunk.references } : m
        ));
      }
      
      // If this chunk only contains confidence/references (no response text), don't process as text
      if (!chunk?.response && (chunk?.confidence || chunk?.references)) {
        return;
      }

      const textChunk = chunk?.response || '';

      // Accumulate tiny upstream token chunks outside React and flush them in
      // batches. Re-rendering Markdown for every token causes visible reflow.
      const prevTarget = streamTextRef.current[messageId] || '';
      const nextTarget = !prevTarget || textChunk.startsWith(prevTarget)
        ? textChunk
        : (prevTarget + textChunk);
      streamTextRef.current[messageId] = nextTarget;

      if (!streamFlushTimerRef.current[messageId]) {
        streamFlushTimerRef.current[messageId] = window.setTimeout(() => {
          delete streamFlushTimerRef.current[messageId];
          const content = streamTextRef.current[messageId] || '';
          setMessages(prev => prev.map(m =>
            m.id === messageId ? { ...m, content, isThinking: false } : m
          ));
          scrollToEnd();
        }, 50);
      }
    };

    const handleDone = (data: any) => {
      const { id: streamId } = data;
      const messageId = streamMapRef.current.get(streamId);
      console.log('[RetrievalTab] ✅ handleDone called:', { streamId, messageId, messagesCount: 'see below' });
      if (messageId) {
        console.log('[RetrievalTab] ✅ Stream done, processing references...');
        const finalize = () => {
          const pendingTimer = streamFlushTimerRef.current[messageId];
          if (pendingTimer) {
            window.clearTimeout(pendingTimer);
            delete streamFlushTimerRef.current[messageId];
          }
          const finalStreamText = streamTextRef.current[messageId];

          // Append references to content when streaming is done
          setMessages(prev => prev.map(m => {
            if (m.id !== messageId) return m;

            const finalMessage = finalStreamText ? { ...m, content: finalStreamText } : m;

            console.log('[RetrievalTab] 📄 Final message content length:', finalMessage.content?.length);
            console.log('[RetrievalTab] 📄 Final message content preview:', finalMessage.content?.substring(0, 200));

            const refs = (finalMessage as any).references;
            if (!refs || !Array.isArray(refs) || refs.length === 0) {
              console.log('[RetrievalTab] ⚠️ No references found in message, keeping original content');
              return finalMessage;
            }

            console.log('[RetrievalTab] 📚 Processing', refs.length, 'references');

            // Build reference list with download buttons
            const refLines = refs.map((r: any, idx: number) => {
              if (!r || typeof r !== 'object') {
                return `- [${idx + 1}] ` + String(r);
              }

              const filePath = (r.file_path || r.filename || r.file_name) as string | undefined;
              const title = (r.title || r.name || filePath) as string | undefined;
              const source = (r.source || r.doc_id || r.document_id) as string | undefined;
              const score = (r.score ?? r.similarity) as number | undefined;

              console.log(`[RetrievalTab] 📊 Reference ${idx + 1}:`, JSON.stringify({
                filePath,
                title,
                source,
                score,
                rawKeys: Object.keys(r),
                fullObject: r
              }, null, 2));

              // Use file_path as the primary label, fallback to title or source
              let label = filePath || title || source || JSON.stringify(r).slice(0, 80) + '...';
              if (source && title && source !== title) {
                label = `${title} (${source})`;
              }

              // Format: filename [下载图标] (score: 0.xxx)
              // Use hash URL format that won't be filtered by ReactMarkdown
              let refText = `- [${idx + 1}] ${label}`;
              if (filePath) {
                refText += ` [⬇️](#download:${encodeURIComponent(filePath)})`;
              }

              if (score !== undefined) {
                refText += `  (score: ${score.toFixed ? score.toFixed(3) : score})`;
              }
              return refText;
            });

            // Remove existing references section from LLM response and add our version with download links
            // Match "References", "参考文献", etc. as a heading (with or without leading newlines)
            // Match from the heading to the end of content
            const referenceSectionRegex = /(\n+|^)(#{1,3}\s*)?(参考文献|参考文档|参考资料|References?)\s*([:：])?\s*\n[\s\S]*$/i;

            console.log('[RetrievalTab] 📝 Original content length:', finalMessage.content?.length);
            console.log('[RetrievalTab] 📝 Content has </think>:', finalMessage.content?.includes('</think>'));

            // Remove LLM-generated duplicate words (e.g., "References References" → "References")
            const deduplicateWords = (text: string): string => {
              return text.replace(/\b(\w+)\s+\1\b/gi, '$1');
            };

            let baseContent = deduplicateWords((finalMessage.content || '')).replace(referenceSectionRegex, '').trim();

            console.log('[RetrievalTab] 📝 After regex, content length:', baseContent.length);
            console.log('[RetrievalTab] 📝 After regex, has </think>:', baseContent.includes('</think>'));

            const newContent = `${baseContent}\n\n${t('pages.knowledge.retrieval.referenceDocs')}\n${refLines.join('\n')}`;
            return { ...finalMessage, content: newContent };
          }));

          delete streamTextRef.current[messageId];
          streamMapRef.current.delete(streamId);
          setLoading(false);
          thinkingStartTimeRef.current = null;
        };

        finalize();
      }
    };

    const handleError = (data: any) => {
      const { id: streamId, error } = data;
      const messageId = streamMapRef.current.get(streamId);
      if (messageId) {
        const pendingTimer = streamFlushTimerRef.current[messageId];
        if (pendingTimer) {
          window.clearTimeout(pendingTimer);
          delete streamFlushTimerRef.current[messageId];
        }
        delete streamTextRef.current[messageId];
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
      Object.values(streamFlushTimerRef.current).forEach(timer => window.clearTimeout(timer));
      streamFlushTimerRef.current = {};
      streamTextRef.current = {};
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
    const queryStartedAt = performance.now();
    
    const options = buildOptions();
    
    try {
      if (stream) {
        // Use streaming query
        const response = await get_ipc_api().lightragApi.queryStream({ text: userMsg.content, options, workspace: workspace || undefined });
        
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
        const response = await get_ipc_api().lightragApi.query({ text: userMsg.content, options, workspace: workspace || undefined });
        
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

              if (shouldAnswer === false) {
                content = base;
              } else if (hasRefs) {
                // Build a simple human-readable reference list with download buttons
                const refLines = refs.map((r: any, idx: number) => {
                  if (!r || typeof r !== 'object') {
                    return `- [${idx + 1}] ` + String(r);
                  }

                  const filePath = (r.file_path || r.filename || r.file_name) as string | undefined;
                  const title = (r.title || r.name || filePath) as string | undefined;
                  const source = (r.source || r.doc_id || r.document_id) as string | undefined;
                  const score = (r.score ?? r.similarity) as number | undefined;

                  // Use file_path as the primary label, fallback to title or source
                  let label = filePath || title || source || JSON.stringify(r).slice(0, 80) + '...';
                  if (source && title && source !== title) {
                    label = `${title} (${source})`;
                  }
                  
                  // Format: filename [下载图标] (score: 0.xxx)
                  // Use hash URL format that won't be filtered by ReactMarkdown
                  let refText = `- [${idx + 1}] ${label}`;
                  if (filePath) {
                    refText += ` [⬇️](#download:${encodeURIComponent(filePath)})`;
                  }
                  
                  if (score !== undefined) {
                    refText += `  (score: ${score.toFixed ? score.toFixed(3) : score})`;
                  }
                  return refText;
                });

                // Remove existing references section from LLM response and add our version with download links
                // Match "References", "参考文献", etc. as a heading (with or without leading newlines)
                // Match from the heading to the end of content
                const referenceSectionRegex = /(\n+|^)(#{1,3}\s*)?(参考文献|参考文档|参考资料|References?)\s*([:：])?\s*\n[\s\S]*$/i;
                
                // Remove LLM-generated duplicate words (e.g., "References References" → "References")
                const deduplicateWords = (text: string): string => {
                  return text.replace(/\b(\w+)\s+\1\b/gi, '$1');
                };
                
                const baseContent = deduplicateWords(base).replace(referenceSectionRegex, '').trim();
                
                content = `${baseContent}\n\n${t('pages.knowledge.retrieval.referenceDocs')}\n${refLines.join('\n')}`;
              } else {
                // No references available
                const hasReferencesSection = /(^|\n)\s*(references|reference|参考文档|参考资料|参考文献)\s*[:：]?/i.test(base);
                if (!hasReferencesSection) {
                  content = base + '\n\n' + t('pages.knowledge.retrieval.noReferencesFound');
                } else {
                  content = base;
                }
              }
            } else if (typeof resultData === 'string') {
              content = resultData;
            } else {
              content = JSON.stringify(resultData);
            }

            // Extract and normalize confidence if present (same as streaming mode)
            let confidence = resultData?.confidence;
            if (confidence) {
              // Normalize confidence data to support different model formats
              const rawConfidence = confidence;
              confidence = {
                ...rawConfidence,
                // Support multiple field names for overall score
                overall_score: rawConfidence.overall_score ?? rawConfidence.score ?? rawConfidence.confidence ?? 0,
                // Support multiple field names for confidence level
                confidence_level: rawConfidence.confidence_level ?? rawConfidence.level ?? 'unknown',
                // Preserve decision if exists
                decision: rawConfidence.decision ?? {}
              };
            }

            const shouldAnswer = confidence?.decision?.should_answer;
            const rawResponse = resultData?.raw_response;
            const responseTimeMs = typeof resultData?.response_time === 'number'
              ? resultData.response_time * 1000
              : performance.now() - queryStartedAt;
            setMessages(prev => prev.map(m => 
              m.id === assistantId ? {
                ...m,
                content,
                confidence,
                rawContent: shouldAnswer === false ? rawResponse : undefined,
                retrievalMetrics: { elapsedMs: responseTimeMs },
              } : m
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
      padding: '16px', 
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
            borderRadius: 12, 
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
              color: token.colorTextQuaternary,
              gap: 8
            }}>
              <div style={{ fontSize: 36, opacity: 0.15, marginBottom: 4 }}>💬</div>
              <div style={{ fontSize: 13, fontWeight: 500, opacity: 0.6 }}>{t('pages.knowledge.retrieval.startConversation')}</div>
              <div style={{ fontSize: 12, opacity: 0.45 }}>{t('pages.knowledge.retrieval.startConversationDesc')}</div>
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
                    retrievalMetrics={m.retrievalMetrics}
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
          borderRadius: 12,
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
        borderRadius: 12, 
        background: token.colorBgContainer, 
        display: 'flex', 
        flexDirection: 'column', 
        maxHeight: '100%', 
        overflow: 'hidden',
        boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
          <h4 style={{ margin: 0, fontSize: 13, fontWeight: 600, color: token.colorText }}>⚙️ {t('pages.knowledge.retrieval.querySettings')}</h4>
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
            <div className="param-row" style={{ alignItems: 'center' }}>
              <label>{t('pages.knowledge.lightrag.workspacePicker.label')}</label>
              <WorkspacePicker
                value={workspace}
                onChange={setWorkspace}
                placeholder={t('pages.knowledge.lightrag.workspacePicker.serverDefault')}
              />
            </div>
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
        /* .ec-btn is defined in styles/lightragTheme.css — do not duplicate here */
        [data-ec-scope="lightrag-ported"] .ec-btn-primary {
          background: ${token.colorPrimary};
          color: #ffffff;
          border-color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .ec-btn-primary:hover {
          background: ${token.colorPrimaryHover};
          border-color: ${token.colorPrimaryHover};
          color: #ffffff;
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:hover {
          border-color: ${token.colorPrimary};
          color: ${token.colorPrimary};
        }
        [data-ec-scope="lightrag-ported"] .param-group {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        [data-ec-scope="lightrag-ported"] .param-group-title {
          font-size: 12px;
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
