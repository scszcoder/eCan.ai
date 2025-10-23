import React, { useState } from 'react';
import { get_ipc_api } from '@/services/ipc_api';

// Settings controls per requirements (UI only; no persistence yet)

const Select: React.FC<{ label: string; value: string; onChange: (v: string) => void; options: string[] }>
  = ({ label, value, onChange, options }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <div style={{ width: 180 }}>{label}</div>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        className="ec-input"
      >
        {options.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    </div>
  );

const TextInput: React.FC<{ label: string; value: string; onChange: (v: string) => void; type?: string }>
  = ({ label, value, onChange, type = 'text' }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      <div style={{ width: 180 }}>{label}</div>
      <input className="ec-input" type={type} value={value} onChange={e => onChange(e.target.value)} />
    </div>
  );

const SettingsTab: React.FC = () => {
  const [vectorDB, setVectorDB] = useState('Faiss');
  const [embeddingModel, setEmbeddingModel] = useState('openai');
  const [llmModel, setLlmModel] = useState('openai');
  const [rerankModel, setRerankModel] = useState('openai');

  const [maxTokenSize, setMaxTokenSize] = useState('9000');
  const [embeddingDim, setEmbeddingDim] = useState('3072');
  const [workingDir, setWorkingDir] = useState('');

  const openFolderDialog = async () => {
    try {
      // Reuse existing file dialog approach via IPC if available
      const api = get_ipc_api();
      // Placeholder: assuming an IPC API similar to skill-editor's open/save handlers
      // Replace with actual channel when defined
      const result: any = await api.fs?.selectDirectory?.({});
      if (result && result.path) setWorkingDir(result.path);
    } catch {
      // no-op
    }
  };

  return (
    <div style={{ padding: 16 }} data-ec-scope="lightrag-ported">
      <h3 style={{ marginBottom: 12 }}>Settings</h3>
      <Select label="VectorDB" value={vectorDB} onChange={setVectorDB} options={["Faiss", "Chroma", "MongoDB", "Postgres", "Redis", "Milvus"]} />
      <Select label="Embedding Models" value={embeddingModel} onChange={setEmbeddingModel} options={["openai", "gemini", "nvidia", "deepseek"]} />
      <Select label="LLM Model" value={llmModel} onChange={setLlmModel} options={["openai", "claude", "gemini"]} />
      <Select label="Rerank Models" value={rerankModel} onChange={setRerankModel} options={["openai", "claude", "gemini"]} />

      <TextInput label="Max Token Size" value={maxTokenSize} onChange={setMaxTokenSize} />
      <TextInput label="Embedding Dimension" value={embeddingDim} onChange={setEmbeddingDim} />

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <div style={{ width: 180 }}>Working Directory</div>
        <input className="ec-input" type="text" value={workingDir} onChange={e => setWorkingDir(e.target.value)} style={{ flex: 1 }} />
        <button onClick={openFolderDialog} title="Select folder">📂</button>
      </div>
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: var(--ant-color-bg-container, #fff);
          color: var(--ant-color-text, #000);
          border: 1px solid var(--ant-color-border, #d9d9d9);
          border-radius: 6px;
          padding: 4px 8px;
        }
      `}</style>
    </div>
  );
};

export default SettingsTab;
