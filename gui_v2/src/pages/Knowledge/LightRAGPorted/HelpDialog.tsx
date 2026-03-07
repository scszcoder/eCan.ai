import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Modal, Spin, Alert } from 'antd';
import { useTranslation } from 'react-i18next';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTheme } from '@/contexts/ThemeContext';
import enDoc from './docs/KNOWLEDGE_BASE_GUIDE.md?raw';
import zhDoc from './docs/KNOWLEDGE_BASE_GUIDE.zh-CN.md?raw';

interface HelpDialogProps {
  visible: boolean;
  onClose: () => void;
}

const HelpDialog: React.FC<HelpDialogProps> = ({ visible, onClose }) => {
  const { t, i18n } = useTranslation();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string>('');
  const contentRef = useRef<HTMLDivElement>(null);
  const headingRefs = useRef<Map<string, HTMLElement>>(new Map());

  useEffect(() => {
    if (visible) {
      loadDocumentation();
    }
  }, [visible, i18n.language]);

  const loadDocumentation = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const lang = i18n.language;
      const text = (lang === 'zh-CN' || lang === 'zh') ? zhDoc : enDoc;
      setContent(text);
    } catch (err) {
      console.error('Error loading documentation:', err);
      setError(t('pages.knowledge.help.loadError'));
      setContent(getFallbackContent());
    } finally {
      setLoading(false);
    }
  };

  const tableOfContents = useMemo(() => {
    if (!content) return [];
    
    const lines = content.split('\n');
    const toc: Array<{ id: string; level: number; text: string }> = [];
    
    lines.forEach((line) => {
      const match = line.match(/^(#{1,3})\s+(.+)$/);
      if (match) {
        const level = match[1].length;
        const text = match[2].trim();
        const id = text
          .toLowerCase()
          .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
          .replace(/^-+|-+$/g, '');
        
        if (level <= 2) {
          toc.push({ id, level, text });
        }
      }
    });
    
    return toc;
  }, [content]);

  const scrollToSection = (id: string) => {
    const element = headingRefs.current.get(id);
    if (element && contentRef.current) {
      const container = contentRef.current;
      const offsetTop = element.offsetTop - container.offsetTop - 20;
      container.scrollTo({ top: offsetTop, behavior: 'smooth' });
      setActiveSection(id);
    }
  };

  useEffect(() => {
    const container = contentRef.current;
    if (!container) return;

    const handleScroll = () => {
      const scrollTop = container.scrollTop;
      let currentSection = '';

      headingRefs.current.forEach((element, id) => {
        const offsetTop = element.offsetTop - container.offsetTop;
        if (offsetTop <= scrollTop + 100) {
          currentSection = id;
        }
      });

      if (currentSection !== activeSection) {
        setActiveSection(currentSection);
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [activeSection]);

  const getFallbackContent = () => {
    const lang = i18n.language;
    if (lang === 'zh-CN' || lang === 'zh') {
      return `# 知识库帮助\n\n## 快速开始\n\n1. **创建工作空间**：在设置中创建或选择工作空间\n2. **配置模型**：设置 LLM、Embedding 和 Reranker 提供商\n3. **上传文档**：在文档标签页上传文件\n4. **查询知识库**：在检索标签页提问\n5. **查看图谱**：在图谱标签页探索知识图谱\n\n详细文档加载失败，请检查网络连接或联系管理员。`;
    } else {
      return `# Knowledge Base Help\n\n## Quick Start\n\n1. **Create Workspace**: Create or select a workspace in Settings\n2. **Configure Models**: Set up LLM, Embedding, and Reranker providers\n3. **Upload Documents**: Upload files in Documents tab\n4. **Query Knowledge**: Ask questions in Retrieval tab\n5. **View Graph**: Explore knowledge graph in Graph tab\n\nDetailed documentation failed to load. Please check your network connection or contact administrator.`;
    }
  };

  return (
    <Modal
      title={t('pages.knowledge.help.title')}
      open={visible}
      onCancel={onClose}
      footer={null}
      width="80%"
      style={{ top: 20 }}
      styles={{
        body: {
          maxHeight: 'calc(100vh - 200px)',
          overflowY: 'auto',
          padding: '24px',
          backgroundColor: isDark ? '#1f1f1f' : '#ffffff',
        }
      }}
      className={isDark ? 'dark-theme-modal' : ''}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '40px' }}>
          <Spin size="large" />
          <div style={{ marginTop: '16px', color: isDark ? '#fff' : '#666' }}>
            {t('pages.knowledge.help.loading')}
          </div>
        </div>
      )}
      
      {error && (
        <Alert
          message={t('common.error')}
          description={error}
          type="error"
          showIcon
          style={{ marginBottom: '16px' }}
        />
      )}
      
      {!loading && content && (
        <div style={{ display: 'flex', gap: '24px', height: '100%' }}>
          <div
            style={{
              width: '240px',
              flexShrink: 0,
              borderRight: `1px solid ${isDark ? '#333' : '#e0e0e0'}`,
              paddingRight: '16px',
              overflowY: 'auto',
              maxHeight: 'calc(100vh - 200px)',
            }}
          >
            <div style={{ 
              fontSize: '14px', 
              fontWeight: 600, 
              marginBottom: '12px',
              color: isDark ? '#fff' : '#333'
            }}>
              {t('pages.knowledge.help.tableOfContents', { defaultValue: '目录' })}
            </div>
            <div style={{ fontSize: '13px' }}>
              {tableOfContents.map((item) => (
                <div
                  key={item.id}
                  onClick={() => scrollToSection(item.id)}
                  style={{
                    padding: '6px 8px',
                    paddingLeft: `${(item.level - 1) * 16 + 8}px`,
                    cursor: 'pointer',
                    borderRadius: '4px',
                    marginBottom: '2px',
                    color: activeSection === item.id 
                      ? (isDark ? '#58a6ff' : '#0066cc')
                      : (isDark ? '#aaa' : '#666'),
                    backgroundColor: activeSection === item.id
                      ? (isDark ? 'rgba(88, 166, 255, 0.1)' : 'rgba(0, 102, 204, 0.05)')
                      : 'transparent',
                    fontWeight: activeSection === item.id ? 600 : 400,
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    if (activeSection !== item.id) {
                      e.currentTarget.style.backgroundColor = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (activeSection !== item.id) {
                      e.currentTarget.style.backgroundColor = 'transparent';
                    }
                  }}
                >
                  {item.text}
                </div>
              ))}
            </div>
          </div>

          <div 
            ref={contentRef}
            className="markdown-content"
            style={{
              flex: 1,
              color: isDark ? '#e0e0e0' : '#333',
              lineHeight: '1.8',
              overflowY: 'auto',
              maxHeight: 'calc(100vh - 200px)',
            }}
          >
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ node, ...props }) => {
                  const text = String(props.children);
                  const id = text
                    .toLowerCase()
                    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
                    .replace(/^-+|-+$/g, '');
                  return (
                    <h1 
                      ref={(el) => {
                        if (el) headingRefs.current.set(id, el);
                      }}
                      id={id}
                      style={{ 
                        color: isDark ? '#fff' : '#1a2b4b',
                        borderBottom: `2px solid ${isDark ? '#444' : '#e0e0e0'}`,
                        paddingBottom: '8px',
                        marginTop: '24px',
                        marginBottom: '16px',
                        scrollMarginTop: '20px'
                      }} 
                      {...props} 
                    />
                  );
                },
                h2: ({ node, ...props }) => {
                  const text = String(props.children);
                  const id = text
                    .toLowerCase()
                    .replace(/[^a-z0-9\u4e00-\u9fa5]+/g, '-')
                    .replace(/^-+|-+$/g, '');
                  return (
                    <h2 
                      ref={(el) => {
                        if (el) headingRefs.current.set(id, el);
                      }}
                      id={id}
                      style={{ 
                        color: isDark ? '#fff' : '#1a2b4b',
                        borderBottom: `1px solid ${isDark ? '#444' : '#e0e0e0'}`,
                        paddingBottom: '6px',
                        marginTop: '20px',
                        marginBottom: '12px',
                        scrollMarginTop: '20px'
                      }} 
                      {...props} 
                    />
                  );
                },
                h3: ({ node, ...props }) => (
                  <h3 style={{ 
                    color: isDark ? '#f0f0f0' : '#2c3e50',
                    marginTop: '16px',
                    marginBottom: '10px'
                  }} {...props} />
                ),
                h4: ({ node, ...props }) => (
                  <h4 style={{ 
                    color: isDark ? '#e0e0e0' : '#34495e',
                    marginTop: '14px',
                    marginBottom: '8px'
                  }} {...props} />
                ),
                code: ({ node, inline, ...props }: any) => (
                  inline ? (
                    <code style={{
                      backgroundColor: isDark ? '#2d2d2d' : '#f5f5f5',
                      color: isDark ? '#e06c75' : '#c7254e',
                      padding: '2px 6px',
                      borderRadius: '3px',
                      fontSize: '0.9em',
                      fontFamily: 'Monaco, Consolas, monospace'
                    }} {...props} />
                  ) : (
                    <code style={{
                      display: 'block',
                      backgroundColor: isDark ? '#2d2d2d' : '#f5f5f5',
                      color: isDark ? '#abb2bf' : '#333',
                      padding: '12px',
                      borderRadius: '4px',
                      fontSize: '0.9em',
                      fontFamily: 'Monaco, Consolas, monospace',
                      overflowX: 'auto',
                      marginTop: '8px',
                      marginBottom: '8px'
                    }} {...props} />
                  )
                ),
                pre: ({ node, ...props }) => (
                  <pre style={{
                    backgroundColor: isDark ? '#2d2d2d' : '#f5f5f5',
                    padding: '16px',
                    borderRadius: '4px',
                    overflowX: 'auto',
                    marginTop: '12px',
                    marginBottom: '12px'
                  }} {...props} />
                ),
                table: ({ node, ...props }) => (
                  <div style={{ overflowX: 'auto', marginTop: '12px', marginBottom: '12px' }}>
                    <table style={{
                      borderCollapse: 'collapse',
                      width: '100%',
                      border: `1px solid ${isDark ? '#444' : '#ddd'}`
                    }} {...props} />
                  </div>
                ),
                th: ({ node, ...props }) => (
                  <th style={{
                    backgroundColor: isDark ? '#2d2d2d' : '#f5f5f5',
                    color: isDark ? '#fff' : '#333',
                    padding: '10px',
                    border: `1px solid ${isDark ? '#444' : '#ddd'}`,
                    textAlign: 'left',
                    fontWeight: 'bold'
                  }} {...props} />
                ),
                td: ({ node, ...props }) => (
                  <td style={{
                    padding: '10px',
                    border: `1px solid ${isDark ? '#444' : '#ddd'}`,
                    color: isDark ? '#e0e0e0' : '#333'
                  }} {...props} />
                ),
                blockquote: ({ node, ...props }) => (
                  <blockquote style={{
                    borderLeft: `4px solid ${isDark ? '#555' : '#ddd'}`,
                    paddingLeft: '16px',
                    marginLeft: '0',
                    color: isDark ? '#aaa' : '#666',
                    fontStyle: 'italic'
                  }} {...props} />
                ),
                a: ({ node, ...props }) => (
                  <a style={{
                    color: isDark ? '#58a6ff' : '#0066cc',
                    textDecoration: 'none'
                  }} {...props} />
                ),
                ul: ({ node, ...props }) => (
                  <ul style={{
                    paddingLeft: '24px',
                    marginTop: '8px',
                    marginBottom: '8px'
                  }} {...props} />
                ),
                ol: ({ node, ...props }) => (
                  <ol style={{
                    paddingLeft: '24px',
                    marginTop: '8px',
                    marginBottom: '8px'
                  }} {...props} />
                ),
                li: ({ node, ...props }) => (
                  <li style={{
                    marginBottom: '4px',
                    color: isDark ? '#e0e0e0' : '#333'
                  }} {...props} />
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </Modal>
  );
};

export default HelpDialog;
