import React, { useState, useEffect } from 'react';
import { theme, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { FolderOpenOutlined, SaveOutlined, DatabaseOutlined, ApiOutlined, SettingOutlined } from '@ant-design/icons';
import { useTheme } from '@/contexts/ThemeContext';

const SettingsTab: React.FC = () => {
  const [vectorDB, setVectorDB] = useState('Faiss');
  const [embeddingModel, setEmbeddingModel] = useState('openai');
  const [llmModel, setLlmModel] = useState('openai');
  const [rerankModel, setRerankModel] = useState('openai');
  const [maxTokenSize, setMaxTokenSize] = useState('9000');
  const [embeddingDim, setEmbeddingDim] = useState('3072');
  const [workingDir, setWorkingDir] = useState('');
  const [loading, setLoading] = useState(false);
  
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const response = await get_ipc_api().lightragApi.getSettings();
      if (response.success && response.data) {
        const res = response.data as any;
        if (res && !res.error) {
            if (res.vectorDB) setVectorDB(res.vectorDB);
            if (res.embeddingModel) setEmbeddingModel(res.embeddingModel);
            if (res.llmModel) setLlmModel(res.llmModel);
            if (res.rerankModel) setRerankModel(res.rerankModel);
            if (res.maxTokenSize) setMaxTokenSize(res.maxTokenSize);
            if (res.embeddingDim) setEmbeddingDim(res.embeddingDim);
            if (res.workingDir) setWorkingDir(res.workingDir);
        }
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
  };

  const openFolderDialog = async () => {
    try {
      // 5 minutes timeout for user interaction
      const response = await get_ipc_api().executeRequest<any>('fs.selectDirectory', {}, 300000);
      if (response.success && response.data) {
          const result = response.data;
          if (result && result.path) setWorkingDir(result.path);
      }
    } catch (e) {
      console.error('Failed to select directory:', e);
    }
  };

  const handleSave = async () => {
    try {
      setLoading(true);
      const settings = {
        vectorDB,
        embeddingModel,
        llmModel,
        rerankModel,
        maxTokenSize,
        embeddingDim,
        workingDir
      };
      
      const response = await get_ipc_api().lightragApi.saveSettings(settings);
      if (response.success) {
          message.success(t('pages.knowledge.settings.saveSuccess', 'Settings saved successfully'));
      } else {
          throw new Error(response.error?.message || 'Unknown error');
      }
    } catch (e: any) {
      message.error(t('pages.knowledge.settings.saveError', 'Failed to save settings') + ': ' + (e.message || String(e)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ 
      height: '100%', 
      overflow: 'auto'
    }}>
      <div style={{ 
        padding: '32px', 
        minHeight: '100%',
        display: 'flex', 
        flexDirection: 'column', 
        gap: 24,
        background: token.colorBgLayout
      }} data-ec-scope="lightrag-ported">
      {/* Header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '16px 0',
        marginBottom: 8
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ 
            width: 36, 
            height: 36, 
            borderRadius: 8, 
            background: `linear-gradient(135deg, ${token.colorPrimary} 0%, ${token.colorPrimaryHover} 100%)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <SettingOutlined style={{ fontSize: 18, color: '#ffffff' }} />
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: token.colorText, lineHeight: 1.2 }}>
              {t('pages.knowledge.settings.title')}
            </h3>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: token.colorTextSecondary }}>
              {t('pages.knowledge.settings.subtitle')}
            </p>
          </div>
        </div>
        <button className="ec-btn ec-btn-primary" onClick={handleSave} disabled={loading}>
          <SaveOutlined /> {loading ? 'Saving...' : t('pages.knowledge.settings.saveSettings')}
        </button>
      </div>

      {/* Database Configuration */}
      <div style={{
        background: token.colorBgContainer,
        borderRadius: 16,
        border: `1px solid ${token.colorBorder}`,
        overflow: 'hidden',
        boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${token.colorBorderSecondary}`, background: isDark ? token.colorBgElevated : token.colorBgLayout }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>
            <DatabaseOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.settings.databaseConfig')}
          </h4>
        </div>
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="setting-row">
            <label>{t('pages.knowledge.settings.vectorDatabase')}</label>
            <select className="ec-input ec-select" value={vectorDB} onChange={e => setVectorDB(e.target.value)}>
              <option value="Faiss">Faiss</option>
              <option value="Chroma">Chroma</option>
              <option value="MongoDB">MongoDB</option>
              <option value="Postgres">Postgres</option>
              <option value="Redis">Redis</option>
              <option value="Milvus">Milvus</option>
            </select>
          </div>

          <div className="setting-row">
            <label>{t('pages.knowledge.settings.workingDirectory')}</label>
            <div style={{ display: 'flex', gap: 8, width: '100%' }}>
              <input 
                className="ec-input" 
                type="text" 
                value={workingDir} 
                onChange={e => setWorkingDir(e.target.value)} 
                placeholder={t('pages.knowledge.settings.workingDirectoryPlaceholder')}
                style={{ flex: 1 }}
              />
              <button className="ec-btn" onClick={openFolderDialog} title={t('pages.knowledge.settings.selectFolder')}>
                <FolderOpenOutlined />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Model Configuration */}
      <div style={{
        background: token.colorBgContainer,
        borderRadius: 16,
        border: `1px solid ${token.colorBorder}`,
        overflow: 'hidden',
        boxShadow: isDark ? '0 4px 16px rgba(0, 0, 0, 0.15)' : '0 4px 16px rgba(0, 0, 0, 0.06)'
      }}>
        <div style={{ padding: '20px 24px', borderBottom: `1px solid ${token.colorBorderSecondary}`, background: isDark ? token.colorBgElevated : token.colorBgLayout }}>
          <h4 style={{ margin: 0, fontSize: 15, fontWeight: 600, color: token.colorText }}>
            <ApiOutlined style={{ marginRight: 8 }} />
            {t('pages.knowledge.settings.modelConfig')}
          </h4>
        </div>
        <div style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 20 }}>
            <div className="setting-row">
              <label>{t('pages.knowledge.settings.embeddingModel')}</label>
              <select className="ec-input ec-select" value={embeddingModel} onChange={e => setEmbeddingModel(e.target.value)}>
                <option value="openai">OpenAI</option>
                <option value="gemini">Gemini</option>
                <option value="nvidia">NVIDIA</option>
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>

            <div className="setting-row">
              <label>{t('pages.knowledge.settings.llmModel')}</label>
              <select className="ec-input ec-select" value={llmModel} onChange={e => setLlmModel(e.target.value)}>
                <option value="openai">OpenAI</option>
                <option value="claude">Claude</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>

            <div className="setting-row">
              <label>{t('pages.knowledge.settings.rerankModel')}</label>
              <select className="ec-input ec-select" value={rerankModel} onChange={e => setRerankModel(e.target.value)}>
                <option value="openai">OpenAI</option>
                <option value="claude">Claude</option>
                <option value="gemini">Gemini</option>
              </select>
            </div>

            <div className="setting-row">
              <label>{t('pages.knowledge.settings.embeddingDimension')}</label>
              <input 
                className="ec-input" 
                type="number" 
                value={embeddingDim} 
                onChange={e => setEmbeddingDim(e.target.value)}
                placeholder={t('pages.knowledge.settings.embeddingDimensionPlaceholder')}
              />
            </div>

            <div className="setting-row">
              <label>{t('pages.knowledge.settings.maxTokenSize')}</label>
              <input 
                className="ec-input" 
                type="number" 
                value={maxTokenSize} 
                onChange={e => setMaxTokenSize(e.target.value)}
                placeholder={t('pages.knowledge.settings.maxTokenSizePlaceholder')}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Scoped styles */}
      <style>{`
        [data-ec-scope="lightrag-ported"] .ec-input {
          background: ${token.colorBgContainer};
          color: ${token.colorText};
          border: 1px solid ${token.colorBorder};
          border-radius: 10px;
          padding: 10px 14px;
          font-size: 14px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          width: 100%;
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
          padding: 10px 18px;
          cursor: pointer;
          font-size: 14px;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
          font-weight: 500;
          white-space: nowrap;
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
        [data-ec-scope="lightrag-ported"] .setting-row {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        [data-ec-scope="lightrag-ported"] .setting-row > label {
          font-size: 13px;
          font-weight: 600;
          color: ${token.colorTextSecondary};
        }
        [data-ec-scope="lightrag-ported"] .setting-row > .ec-input,
        [data-ec-scope="lightrag-ported"] .setting-row > select.ec-input,
        [data-ec-scope="lightrag-ported"] .setting-row > div {
          width: 100%;
        }
        [data-ec-scope="lightrag-ported"] .ec-select {
          cursor: pointer;
        }
      `}</style>
      </div>
    </div>
  );
};

export default SettingsTab;
