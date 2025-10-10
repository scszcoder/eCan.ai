import React, { useMemo, useRef, useState } from 'react';
import { lightragIpc } from '@/services/ipc/lightrag';

type ChatMessage = { id: string; role: 'user' | 'assistant'; content: string };

const RetrievalTab: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [mode, setMode] = useState<'naive' | 'local' | 'global' | 'hybrid' | 'mix' | 'bypass'>('mix');
  const [stream, setStream] = useState(false);
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
    try {
      const res = await lightragIpc.query({ text: userMsg.content, options: buildOptions() });
      const content = typeof res === 'object' && res && 'response' in res ? String((res as any).response) : JSON.stringify(res);
      const assistantMsg: ChatMessage = { id: crypto.randomUUID?.() || String(Date.now()+1), role: 'assistant', content };
      setMessages(prev => [...prev, assistantMsg]);
      scrollToEnd();
    } catch (e: any) {
      const assistantMsg: ChatMessage = { id: crypto.randomUUID?.() || String(Date.now()+1), role: 'assistant', content: `Error: ${e?.message || String(e)}` };
      setMessages(prev => [...prev, assistantMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 16, height: '100%', display: 'flex', gap: 12 }} data-ec-scope="lightrag-ported">
      {/* Left panel */}
      <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Messages area */}
        <div style={{ flex: 1, minHeight: 0, border: '1px solid var(--ant-color-border, #d9d9d9)', borderRadius: 8, padding: 12, overflow: 'auto', background: 'var(--ant-color-bg-container, #fff)' }}>
          {messages.length === 0 ? (
            <div style={{ opacity: 0.6, textAlign: 'center', marginTop: 24 }}>Type your question below and press Send.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {messages.map(m => (
                <div key={m.id} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                  <div style={{ maxWidth: '80%', whiteSpace: 'pre-wrap', background: m.role === 'user' ? '#e6f4ff' : '#f5f5f5', color: '#111', padding: '8px 10px', borderRadius: 8 }}>
                    {m.content}
                  </div>
                </div>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>
        {/* Input row (horizontal: Clear | textarea | Send) */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'stretch', marginTop: 8 }}>
          <button className="ec-btn" onClick={handleClear} disabled={loading} style={{ alignSelf: 'stretch', whiteSpace: 'nowrap' }}>Clear</button>
          <textarea
            className="ec-input"
            rows={3}
            placeholder="Enter your question"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            style={{ flex: 1, resize: 'vertical' }}
          />
          <button className="ec-btn" onClick={handleSend} disabled={!canSend} style={{ alignSelf: 'stretch', whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>Send</span>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2 21L23 12L2 3L2 10L17 12L2 14L2 21Z" fill="#111111"/>
            </svg>
          </button>
        </div>
      </div>

      {/* Right panel - parameters */}
      <div style={{ width: 214, flexShrink: 0, border: '1px solid var(--ant-color-border, #d9d9d9)', borderRadius: 8, background: 'var(--ant-color-bg-container, #fff)', padding: 12, display: 'flex', flexDirection: 'column', gap: 10, maxHeight: '100%', overflowY: 'auto', overflowX: 'hidden' }}>
        <h4 style={{ margin: 0 }}>Parameters</h4>
        <div className="param-row">
          <label>Mode</label>
          <select className="ec-input" value={mode} onChange={e => setMode(e.target.value as any)}>
            <option value="naive">naive</option>
            <option value="local">local</option>
            <option value="global">global</option>
            <option value="hybrid">hybrid</option>
            <option value="mix">mix</option>
            <option value="bypass">bypass</option>
          </select>
        </div>
        <div className="param-row"><label>Response Type</label><input className="ec-input" value={responseType} onChange={e => setResponseType(e.target.value)} placeholder="e.g. Bullet Points" /></div>
        <div className="param-row"><label>User Prompt</label><input className="ec-input" value={userPrompt} onChange={e => setUserPrompt(e.target.value)} placeholder="Custom system prompt" /></div>
        <div className="param-row"><label>Top K</label><input className="ec-input" type="number" value={topK as any} onChange={e => setTopK(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label>Chunk Top K</label><input className="ec-input" type="number" value={chunkTopK as any} onChange={e => setChunkTopK(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label>Max Entity Tokens</label><input className="ec-input" type="number" value={maxEntityTokens as any} onChange={e => setMaxEntityTokens(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label>Max Relation Tokens</label><input className="ec-input" type="number" value={maxRelationTokens as any} onChange={e => setMaxRelationTokens(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label>Max Total Tokens</label><input className="ec-input" type="number" value={maxTotalTokens as any} onChange={e => setMaxTotalTokens(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label>History Turns</label><input className="ec-input" type="number" value={historyTurns as any} onChange={e => setHistoryTurns(e.target.value === '' ? '' : Number(e.target.value))} /></div>
        <div className="param-row"><label><input type="checkbox" checked={stream} onChange={e => setStream(e.target.checked)} /> Stream</label></div>
        <div className="param-row"><label><input type="checkbox" checked={enableRerank} onChange={e => setEnableRerank(e.target.checked)} /> Enable Rerank</label></div>
        <div className="param-row"><label><input type="checkbox" checked={onlyNeedContext} onChange={e => setOnlyNeedContext(e.target.checked)} /> Only Need Context</label></div>
        <div className="param-row"><label><input type="checkbox" checked={onlyNeedPrompt} onChange={e => setOnlyNeedPrompt(e.target.checked)} /> Only Need Prompt</label></div>
      </div>

      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: var(--ant-color-bg-container, #fff);
          color: var(--ant-color-text, #000);
          border: 1px solid var(--ant-color-border, #d9d9d9);
          border-radius: 6px;
          padding: 6px 8px;
          box-sizing: border-box;
        }
        [data-ec-scope="lightrag-ported"] .ec-btn {
          background: #ffffff !important;
          color: #111111 !important;
          border: 1px solid #d9d9d9 !important;
          border-radius: 6px;
          padding: 6px 12px;
          cursor: pointer;
        }
        [data-ec-scope="lightrag-ported"] .ec-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        [data-ec-scope="lightrag-ported"] .param-row { display: flex; align-items: center; gap: 8px; width: 100%; }
        [data-ec-scope="lightrag-ported"] .param-row > label { flex: 0 0 140px; font-size: 12px; color: var(--ant-color-text-secondary, #666); }
        /* Make rows below the first have a smaller label so inputs are wider */
        [data-ec-scope="lightrag-ported"] .param-row:not(:first-of-type) > label { flex-basis: 70px; }
        /* Make the first row (Mode) match others */
        [data-ec-scope="lightrag-ported"] .param-row:first-of-type > label { flex-basis: 70px; }
        [data-ec-scope="lightrag-ported"] .param-row > .ec-input,
        [data-ec-scope="lightrag-ported"] .param-row select.ec-input,
        [data-ec-scope="lightrag-ported"] .param-row input.ec-input {
          flex: 1 1 auto;
          min-width: 0;
          max-width: 100%;
        }
      `}</style>
    </div>
  );
};

export default RetrievalTab;
