import React, { useState, useMemo, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight, oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { theme, message as antMessage } from 'antd';
import { Loader2, ChevronDown, Copy, Check } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  isThinking?: boolean;
  thinkingTime?: number | null;
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

const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, isThinking: isThinkingProp, thinkingTime }) => {
  const { token } = theme.useToken();
  const { theme: currentTheme } = useTheme();
  const isDark = currentTheme === 'dark' || (currentTheme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

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
                {isThinking ? 'Thinking...' : `Thought Process ${thinkingTime ? `(${thinkingTime}s)` : ''}`}
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
                  }
                }}
              >
                {displayContent}
              </ReactMarkdown>
            </div>
          ) : (
            !thinkingContent && <span style={{ fontStyle: 'italic', color: token.colorTextTertiary }}>Empty response</span>
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
