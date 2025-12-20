import React, { useState, useRef, useEffect } from 'react';
import { Card, Button, Tooltip, message } from 'antd';
import {
  MessageOutlined,
  ToolOutlined,
  DatabaseOutlined,
  ApiOutlined,
  CodeOutlined,
  FileOutlined,
  InfoCircleOutlined,
  CopyOutlined,
  LikeOutlined,
  DislikeOutlined,
  ReloadOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import styled from '@emotion/styled';
import type { ContextItem, ContextItemType } from '../types/context';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const ItemCard = styled(Card)`
  background: #222;
  border: 1px solid #333;
  border-radius: 6px;
  width: 100%;
  box-sizing: border-box;
  min-height: 120px;
  
  .ant-card-head {
    padding: 8px 12px;
    min-height: auto;
    border-bottom: 1px solid #333;
    background: transparent;
  }
  
  .ant-card-head-title {
    padding: 0;
    overflow: visible;
  }
  
  .ant-card-body {
    padding: 16px;
    min-height: 80px;
    word-wrap: break-word;
    overflow-wrap: break-word;
  }
`;

const ItemHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
`;

const TypeIcon = styled.div<{ color: string }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: ${(props) => props.color}22;
  color: ${(props) => props.color};
  flex-shrink: 0;
`;

const HeaderInfo = styled.div`
  flex: 1;
  min-width: 0;
  overflow: hidden;
`;

const GeneratorName = styled.div`
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const Timestamp = styled.div`
  font-size: 11px;
  color: #888;
`;

const ActionButtons = styled.div`
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  flex-wrap: wrap;
`;

const IconButton = styled(Button)`
  padding: 4px 8px;
  height: auto;
  min-width: 28px;
  
  &:hover {
    background: #333;
  }
`;

const ContentContainer = styled.div<{ collapsible: boolean; collapsed: boolean }>`
  position: relative;
  max-height: ${(props) => (props.collapsible && props.collapsed ? '120px' : 'none')};
  overflow: hidden;
  transition: max-height 0.3s;
  width: 100%;
  box-sizing: border-box;
`;

const ContentText = styled.div`
  font-size: 13px;
  color: #ddd;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
`;

const Description = styled.div`
  font-size: 12px;
  color: #aaa;
  margin-bottom: 8px;
  font-style: italic;
  word-wrap: break-word;
  overflow-wrap: break-word;
`;

const CodeContainer = styled.div`
  position: relative;
  margin-top: 8px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid #333;
  max-width: 100%;
  box-sizing: border-box;
`;

const CopyButton = styled(Button)`
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 1;
  padding: 4px 8px;
  height: auto;
  font-size: 12px;
`;

const JSONContainer = styled.pre`
  background: #1a1a1a;
  border: 1px solid #333;
  border-radius: 6px;
  padding: 12px;
  margin-top: 8px;
  overflow-x: auto;
  font-size: 12px;
  color: #ddd;
  line-height: 1.5;
  max-width: 100%;
  box-sizing: border-box;
  word-wrap: break-word;
  white-space: pre-wrap;
`;

const CollapseButton = styled(Button)`
  margin-top: 8px;
  width: 100%;
`;

interface ContextItemCardProps {
  item: ContextItem;
}

const TYPE_CONFIG: Record<
  ContextItemType,
  { icon: React.ReactNode; color: string; label: string }
> = {
  text: { icon: <MessageOutlined />, color: '#52c41a', label: 'Message' },
  tool_call: { icon: <ToolOutlined />, color: '#1890ff', label: 'Tool Call' },
  db_access: { icon: <DatabaseOutlined />, color: '#722ed1', label: 'Database' },
  api_call: { icon: <ApiOutlined />, color: '#13c2c2', label: 'API Call' },
  code_execution: { icon: <CodeOutlined />, color: '#fa8c16', label: 'Code' },
  file_operation: { icon: <FileOutlined />, color: '#eb2f96', label: 'File' },
  system_event: { icon: <InfoCircleOutlined />, color: '#faad14', label: 'System' },
};

export const ContextItemCard: React.FC<ContextItemCardProps> = ({ item }) => {
  const [collapsed, setCollapsed] = useState(true);
  const [isCollapsible, setIsCollapsible] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  const config = TYPE_CONFIG[item.type];

  useEffect(() => {
    // Check if content is more than 6 lines (approximately 120px with line-height 1.6)
    if (contentRef.current) {
      const lineHeight = 20; // approximate line height
      const maxLines = 6;
      setIsCollapsible(contentRef.current.scrollHeight > lineHeight * maxLines);
    }
  }, [item]);

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success('Copied to clipboard');
    } catch (error) {
      message.error('Failed to copy');
    }
  };

  const handleUpvote = () => {
    message.success('Upvoted');
    // TODO: Send to backend
  };

  const handleDownvote = () => {
    message.warning('Downvoted');
    // TODO: Send to backend
  };

  const handleRefresh = () => {
    message.info('Regenerating...');
    // TODO: Send to backend
  };

  const formatTimestamp = (timestamp: string) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const renderContent = () => {
    const { content } = item;

    return (
      <>
        {content.description && <Description>{content.description}</Description>}
        
        {content.message && (
          <ContentContainer
            ref={contentRef}
            collapsible={isCollapsible}
            collapsed={collapsed}
          >
            <ContentText>{content.message}</ContentText>
          </ContentContainer>
        )}

        {content.toolName && (
          <ContentText>
            <strong>Tool:</strong> {content.toolName}
            {content.toolParams && (
              <JSONContainer>
                {JSON.stringify(content.toolParams, null, 2)}
              </JSONContainer>
            )}
            {content.toolResult && (
              <>
                <div style={{ marginTop: 8, marginBottom: 4, fontWeight: 500 }}>
                  Result:
                </div>
                <JSONContainer>
                  {typeof content.toolResult === 'string'
                    ? content.toolResult
                    : JSON.stringify(content.toolResult, null, 2)}
                </JSONContainer>
              </>
            )}
          </ContentText>
        )}

        {content.code && (
          <CodeContainer>
            <CopyButton
              type="text"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(content.code!)}
            >
              Copy
            </CopyButton>
            <SyntaxHighlighter
              language={content.codeLanguage || 'javascript'}
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                padding: '12px',
                fontSize: '12px',
                background: '#1a1a1a',
                maxWidth: '100%',
                overflowX: 'auto',
              }}
              wrapLongLines={false}
            >
              {content.code}
            </SyntaxHighlighter>
          </CodeContainer>
        )}

        {content.json && (
          <CodeContainer>
            <CopyButton
              type="text"
              icon={<CopyOutlined />}
              onClick={() => handleCopy(JSON.stringify(content.json, null, 2))}
            >
              Copy
            </CopyButton>
            <JSONContainer>{JSON.stringify(content.json, null, 2)}</JSONContainer>
          </CodeContainer>
        )}

        {content.error && (
          <ContentText style={{ color: '#ff4d4f' }}>
            <strong>Error:</strong> {content.error}
          </ContentText>
        )}

        {isCollapsible && (
          <CollapseButton
            type="text"
            size="small"
            icon={collapsed ? <DownOutlined /> : <UpOutlined />}
            onClick={() => setCollapsed(!collapsed)}
          >
            {collapsed ? 'Show more' : 'Show less'}
          </CollapseButton>
        )}
      </>
    );
  };

  return (
    <ItemCard
      title={
        <ItemHeader>
          <TypeIcon color={config.color}>{config.icon}</TypeIcon>
          <HeaderInfo>
            <GeneratorName>
              {item.generatorName} · {config.label}
            </GeneratorName>
            <Timestamp>{formatTimestamp(item.timestamp)}</Timestamp>
          </HeaderInfo>
          {item.generator === 'agent' && (
            <ActionButtons>
              <Tooltip title="Copy">
                <IconButton
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  onClick={() =>
                    handleCopy(
                      item.content.message ||
                        item.content.description ||
                        JSON.stringify(item.content)
                    )
                  }
                />
              </Tooltip>
              <Tooltip title="Upvote">
                <IconButton
                  type="text"
                  size="small"
                  icon={<LikeOutlined />}
                  onClick={handleUpvote}
                />
              </Tooltip>
              <Tooltip title="Downvote">
                <IconButton
                  type="text"
                  size="small"
                  icon={<DislikeOutlined />}
                  onClick={handleDownvote}
                />
              </Tooltip>
              <Tooltip title="Regenerate">
                <IconButton
                  type="text"
                  size="small"
                  icon={<ReloadOutlined />}
                  onClick={handleRefresh}
                />
              </Tooltip>
            </ActionButtons>
          )}
        </ItemHeader>
      }
    >
      {renderContent()}
    </ItemCard>
  );
};
