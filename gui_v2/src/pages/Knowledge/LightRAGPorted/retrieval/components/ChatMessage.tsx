import React, { useState, useMemo, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { theme, message as antMessage } from 'antd';
import { Loader2, ChevronDown, Copy, Check } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import { useTranslation } from 'react-i18next';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  isThinking?: boolean;
  thinkingTime?: number | null;
  loading?: boolean;
  confidence?: any; // Confidence score data
  rawContent?: string;
}

// Helper to parse COT content
const parseCOTContent = (content: string) => {
  const thinkStartTag = '<think>';
  const thinkEndTag = '</think>';

  // Simple check for thinking block
  const startIndex = content.indexOf(thinkStartTag);
  const endIndex = content.indexOf(thinkEndTag);

  let thinkingContent = '';
  let displayContent = content;
  let isThinkingProcess = false;

  if (startIndex !== -1) {
    if (endIndex !== -1 && endIndex > startIndex) {
      // Complete thinking block
      thinkingContent = content.substring(startIndex + thinkStartTag.length, endIndex).trim();
      displayContent = content.substring(endIndex + thinkEndTag.length).trim();
    } else {
      // Still thinking or incomplete block
      thinkingContent = content.substring(startIndex + thinkStartTag.length);
      displayContent = ''; // Hide main content while thinking if it's strictly inside the block
      isThinkingProcess = true;
    }
  }

  return {
    thinkingContent,
    displayContent,
    isThinkingProcess
  };
};

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, isThinking: isThinkingProp, thinkingTime, loading, confidence, rawContent }) => {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const [isRawExpanded, setIsRawExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const noAnswerReason = confidence?.decision?.no_answer_reason;
  const shouldAnswer = confidence?.decision?.should_answer;
  const retrieval = confidence?.signals?.retrieval;

  const { thinkingContent, displayContent, isThinkingProcess } = useMemo(() => {
    if (role === 'user') return { thinkingContent: '', displayContent: content, isThinkingProcess: false };
    return parseCOTContent(content);
  }, [content, role]);

  // Effective thinking state: passed prop OR detected from content
  const isThinking = isThinkingProp || isThinkingProcess;

  // Auto-expand thinking if it's the only content and we are streaming
  useEffect(() => {
    if (isThinking && !displayContent) {
      setIsThinkingExpanded(true);
    } else if (!isThinking && displayContent && thinkingContent) {
      // Collapse when done thinking if we have display content
      setIsThinkingExpanded(false); 
    }
  }, [isThinking, displayContent, thinkingContent]);


  const handleCopy = () => {
    navigator.clipboard.writeText(displayContent || content);
    setCopied(true);
    antMessage.success('Copied to clipboard');
    setTimeout(() => setCopied(false), 2000);
  };

  const containerStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    maxWidth: '85%',
    alignSelf: role === 'user' ? 'flex-end' : 'flex-start',
  };

  const bubbleStyle: React.CSSProperties = {
    padding: '12px 16px',
    borderRadius: 16,
    fontSize: 14,
    boxShadow: isDark ? '0 2px 8px rgba(0,0,0,0.2)' : '0 2px 8px rgba(0,0,0,0.05)',
    backgroundColor: role === 'user' ? token.colorPrimary : token.colorBgContainer,
    color: role === 'user' ? '#fff' : token.colorText,
    border: role === 'user' ? 'none' : `1px solid ${token.colorBorder}`,
    borderBottomRightRadius: role === 'user' ? 4 : 16,
    borderBottomLeftRadius: role === 'user' ? 16 : 4,
    position: 'relative',
  };

  const thinkingStyle: React.CSSProperties = {
    marginBottom: 12,
    paddingLeft: 12,
    borderLeft: `2px solid ${token.colorBorder}`,
  };

  const thinkingHeaderStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    fontSize: 12,
    color: token.colorTextSecondary,
    cursor: 'pointer',
    userSelect: 'none',
  };

  const thinkingBodyStyle: React.CSSProperties = {
    marginTop: 8,
    fontSize: 12,
    color: token.colorTextSecondary,
    whiteSpace: 'pre-wrap',
    fontFamily: 'monospace',
    backgroundColor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
    padding: 8,
    borderRadius: 6,
  };

  const codeStyle: React.CSSProperties = {
    backgroundColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)',
    borderRadius: 4,
    padding: '2px 4px',
    fontFamily: 'monospace',
    fontSize: '0.9em',
  };

  return (
    <div style={containerStyle}>
      <div 
        style={bubbleStyle}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
      >
        {/* Thinking Process Section */}
        {thinkingContent && (
          <div style={thinkingStyle}>
            <div 
              style={thinkingHeaderStyle}
              onClick={() => setIsThinkingExpanded(!isThinkingExpanded)}
            >
              {isThinking ? <Loader2 size={12} className="animate-spin" /> : null}
              <span style={{ fontWeight: 500 }}>
                {isThinking ? t('pages.knowledge.retrieval.thinking') : `Thought Process ${thinkingTime ? `(${thinkingTime}s)` : ''}`}
              </span>
              <ChevronDown size={12} style={{ transform: isThinkingExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
            </div>
            
            {isThinkingExpanded && (
              <div style={thinkingBodyStyle}>
                {thinkingContent}
              </div>
            )}
          </div>
        )}

        {/* Main Content */}
        <div style={{ position: 'relative' }}>
          {displayContent ? (
            <div className={role === 'user' ? 'markdown-user' : 'markdown-body'}>
              <ReactMarkdown
                components={{
                  code({ node, inline, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '');
                    return !inline && match ? (
                      <SyntaxHighlighter
                        style={isDark ? oneDark : oneLight}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ borderRadius: 8, fontSize: 12, margin: '8px 0' }}
                        {...props}
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code style={role === 'user' ? { ...codeStyle, backgroundColor: 'rgba(255,255,255,0.2)' } : codeStyle} {...props}>
                        {children}
                      </code>
                    );
                  },
                  a({ href, children, ...props }: any) {
                    // Handle #download: links - styled as download icon
                    // The actual download is handled by fileDownloadProtocol in RetrievalTab
                    if (href?.startsWith('#download:')) {
                      const filePath = decodeURIComponent(href.replace('#download:', ''));
                      return (
                        <a
                          href={href}
                          style={{
                            textDecoration: 'none',
                            cursor: 'pointer',
                            opacity: 0.8,
                          }}
                          title={t('pages.knowledge.retrieval.clickToDownload', { filePath })}
                        >
                          {children}
                        </a>
                      );
                    }
                    // Regular links
                    return (
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: token.colorPrimary }}
                        {...props}
                      >
                        {children}
                      </a>
                    );
                  }
                }}
              >
                {displayContent}
              </ReactMarkdown>
            </div>
          ) : (
            loading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: token.colorTextSecondary }}>
                <Loader2 size={14} className="animate-spin" />
                <span>{t('pages.knowledge.retrieval.searching')}</span>
              </div>
            ) : (
              !thinkingContent && <span style={{ fontStyle: 'italic', color: token.colorTextTertiary }}>{t('pages.knowledge.retrieval.emptyResponse')}</span>
            )
          )}

          {/* Copy Button (Assistant only) */}
          {role === 'assistant' && !isThinking && displayContent && (
            <button
              onClick={handleCopy}
              style={{
                position: 'absolute',
                bottom: -8,
                right: -8,
                padding: 4,
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                opacity: isHovered ? 1 : 0,
                transition: 'opacity 0.2s',
                color: token.colorTextSecondary,
                display: 'flex',
                alignItems: 'center',
              }}
              title="Copy response"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
        </div>
      </div>
      
      {/* Confidence Score Display (Assistant only) */}
      {role === 'assistant' && confidence && !isThinking && (
        <div style={{
          fontSize: 11,
          color: token.colorTextTertiary,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 4,
          paddingLeft: 4
        }}>
          <span style={{ fontWeight: 500 }}>{t('pages.knowledge.retrieval.confidenceLabel')}:</span>
          <span style={{
            padding: '2px 8px',
            borderRadius: 4,
            backgroundColor: 
              confidence.confidence_level === 'very_high' ? 'rgba(82, 196, 26, 0.15)' :
              confidence.confidence_level === 'high' ? 'rgba(82, 196, 26, 0.1)' :
              confidence.confidence_level === 'medium' ? 'rgba(250, 173, 20, 0.15)' :
              confidence.confidence_level === 'low' ? 'rgba(250, 140, 22, 0.15)' :
              'rgba(255, 77, 79, 0.15)',
            color:
              confidence.confidence_level === 'very_high' ? '#52c41a' :
              confidence.confidence_level === 'high' ? '#52c41a' :
              confidence.confidence_level === 'medium' ? '#faad14' :
              confidence.confidence_level === 'low' ? '#fa8c16' :
              '#ff4d4f',
            fontWeight: 600
          }}>
            {(confidence.overall_score * 100).toFixed(0)}%
          </span>
          <span style={{ opacity: 0.7 }}>
            {confidence.confidence_level === 'very_high' ? '⭐⭐⭐⭐⭐' :
             confidence.confidence_level === 'high' ? '⭐⭐⭐⭐' :
             confidence.confidence_level === 'medium' ? '⭐⭐⭐' :
             confidence.confidence_level === 'low' ? '⭐⭐' : '⭐'}
          </span>
          {confidence.metrics?.reference_count > 0 && (
            <span style={{ opacity: 0.6 }}>
              📚 {t('pages.knowledge.retrieval.refsShort', { count: confidence.metrics.reference_count })}
            </span>
          )}
        </div>
      )}

      {role === 'assistant' && shouldAnswer === false && !isThinking && (
        <div
          style={{
            fontSize: 12,
            color: token.colorWarning,
            paddingLeft: 4,
            marginTop: 4,
            lineHeight: 1.4,
          }}
        >
          {t('pages.knowledge.retrieval.noAnswerHint', {
            reason: String(noAnswerReason || 'unknown'),
            top1: retrieval?.top1 ?? 'N/A',
            supporting_refs: retrieval?.supporting_refs ?? 0,
          })}
        </div>
      )}

      {role === 'assistant' && rawContent && shouldAnswer === false && !isThinking && (
        <div style={{ paddingLeft: 4, marginTop: 6 }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: token.colorTextSecondary,
              cursor: 'pointer',
              userSelect: 'none',
            }}
            onClick={() => setIsRawExpanded(!isRawExpanded)}
          >
            <span style={{ fontWeight: 500 }}>{t('pages.knowledge.retrieval.rawAnswer')}</span>
            <ChevronDown
              size={12}
              style={{
                transform: isRawExpanded ? 'rotate(180deg)' : 'none',
                transition: 'transform 0.2s',
              }}
            />
          </div>
          {isRawExpanded && (
            <div
              style={{
                marginTop: 8,
                fontSize: 12,
                color: token.colorTextSecondary,
                whiteSpace: 'pre-wrap',
                backgroundColor: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
                padding: 8,
                borderRadius: 6,
              }}
            >
              {rawContent}
            </div>
          )}
        </div>
      )}
      {/* Add global styles for markdown if needed, though we try to keep it inline/component based */}
      <style>{`
        .markdown-body p { margin-bottom: 8px; }
        .markdown-body p:last-child { margin-bottom: 0; }
        .markdown-user p { margin-bottom: 8px; }
        .markdown-user p:last-child { margin-bottom: 0; }
      `}</style>
    </div>
  );
};

export default ChatMessage;
