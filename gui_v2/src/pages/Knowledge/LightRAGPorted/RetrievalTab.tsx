import React, { useMemo, useRef, useState } from 'react';
import { theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { lightragIpc } from '@/services/ipc/lightrag';
import { SendOutlined, ClearOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';

type ChatMessage = { id: string; role: 'user' | 'assistant'; content: string };

const RetrievalTab: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'naive' | 'local' | 'global' | 'hybrid' | 'mix' | 'bypass'>('mix');
  const [stream, setStream] = useState(false);
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  // Right panel parameters (subset of LightRAG QuerySettings)
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

  const endRef = useRef<HTMLDivElement>(null);
  const scrollToEnd = () => endRef.current?.scrollIntoView({ behavior: 'auto' });

  const canSend = useMemo(() => input.trim().length > 0 && !loading, [input, loading]);

  const handleClear = () => {
    setMessages([]);
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
    return opts;
  };

  const handleSend = async () => {
    if (!canSend) return;
    const userMsg: ChatMessage = { id: crypto.randomUUID?.() || String(Date.now()), role: 'user', content: input };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    
    const assistantId = crypto.randomUUID?.() || String(Date.now() + 1);
    const assistantMsg: ChatMessage = { id: assistantId, role: 'assistant', content: '' };
    setMessages(prev => [...prev, assistantMsg]);
    
    const options = buildOptions();
    
    try {
      if (stream) {
        // Use streaming query
        const res = await lightragIpc.queryStream({ text: userMsg.content, options });
        
        // Handle streaming response
        if (res && res.chunks && Array.isArray(res.chunks)) {
          // Simulate typing effect with chunks
          let currentContent = '';
          for (const chunk of res.chunks) {
            currentContent += chunk;
            setMessages(prev => prev.map(m => 
              m.id === assistantId ? { ...m, content: currentContent } : m
            ));
            scrollToEnd();
            // Small delay for typing effect
            await new Promise(resolve => setTimeout(resolve, 20));
          }
        } else if (res && res.response) {
          // Fallback to full response
          setMessages(prev => prev.map(m => 
            m.id === assistantId ? { ...m, content: String(res.response) } : m
          ));
        }
      } else {
        // Use normal query
        const res = await lightragIpc.query({ text: userMsg.content, options });
        const content = typeof res === 'object' && res && 'response' in res 
          ? String((res as any).response) 
          : JSON.stringify(res);
        setMessages(prev => prev.map(m => 
          m.id === assistantId ? { ...m, content } : m
        ));
      }
      scrollToEnd();
    } catch (e: any) {
      setMessages(prev => prev.map(m => 
        m.id === assistantId ? { ...m, content: `Error: ${e?.message || String(e)}` } : m
      ));
    } finally {
      setLoading(false);
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
        <div style={{ 
          flex: 1, 
          minHeight: 0, 
          border: `1px solid ${token.colorBorder}`, 
          borderRadius: 16, 
          padding: 20, 
          overflow: 'auto', 
          background: token.colorBgContainer,
          boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
        }}>
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
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {messages.map(m => (
                <div key={m.id} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div style={{ 
                    maxWidth: '75%', 
                    whiteSpace: 'pre-wrap', 
                    background: m.role === 'user' 
                      ? `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`
                      : isDark ? token.colorBgTextHover : token.colorBgLayout,
                    color: m.role === 'user' ? '#ffffff' : token.colorText,
                    padding: '10px 14px', 
                    borderRadius: 12,
                    boxShadow: '0 2px 8px rgba(0,0,0,0.08)',
                    lineHeight: 1.6
                  }}>
                    {m.content}
                  </div>
                </div>
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
            <ClearOutlined />
          </button>
          <textarea
            className="ec-input"
            rows={2}
            placeholder={t('pages.knowledge.retrieval.askQuestion')}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            style={{ flex: 1, resize: 'none', border: 'none', padding: '8px 0' }}
          />
          <button className="ec-btn ec-btn-primary" onClick={handleSend} disabled={!canSend} title={t('pages.knowledge.retrieval.sendMessage')}>
            <SendOutlined />
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
        <div style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
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
          
          <div className="param-group">
            <div className="param-group-title">{t('pages.knowledge.retrieval.customPrompt')}</div>
            <textarea 
              className="ec-input" 
              value={userPrompt} 
              onChange={e => setUserPrompt(e.target.value)} 
              placeholder={t('pages.knowledge.retrieval.customPromptPlaceholder')}
              rows={4}
              style={{ resize: 'vertical', minHeight: 80 }}
            />
          </div>
        </div>
      </div>

      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 14px;
          box-sizing: border-box;
          font-size: 14px;
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
          border-radius: 10px;
          padding: 10px 14px;
          cursor: pointer;
          font-size: 14px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          min-width: 44px;
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
          gap: 12px;
        }
        [data-ec-scope="lightrag-ported"] .param-group-title {
          font-size: 12px;
          font-weight: 700;
          color: ${token.colorTextSecondary};
          text-transform: uppercase;
          letter-spacing: 0.8px;
          margin-bottom: 4px;
        }
        [data-ec-scope="lightrag-ported"] .param-row { 
          display: flex; 
          flex-direction: column;
          gap: 6px; 
          width: 100%; 
        }
        [data-ec-scope="lightrag-ported"] .param-row > label { 
          font-size: 13px; 
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
          padding: 8px 12px;
          background: ${isDark ? token.colorBgElevated : token.colorBgLayout};
          border-radius: 8px;
          cursor: pointer;
          transition: all 0.2s;
          font-size: 13px;
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
      `}</style>
    </div>
  );
};

export default RetrievalTab;
