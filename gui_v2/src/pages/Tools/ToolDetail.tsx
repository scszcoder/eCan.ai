import React, { useRef, useState, useEffect, useCallback } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Empty, Button, Tooltip, message } from 'antd';
import { SaveOutlined, FileMarkdownOutlined, CodeOutlined, EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons';
import Editor from '@monaco-editor/react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Tool } from './types';
import styled from '@emotion/styled';
import { useTranslation } from 'react-i18next';
import { useUserStore } from '../../stores/userStore';
import { IPCAPI } from '../../services/ipc/api';
import { useToolStore } from '../../stores/toolStore';

interface ToolDetailProps {
  tool: Tool | null;
  isAddingNew?: boolean;
  onSaved?: () => void;
  onCancelAdd?: () => void;
}

const DetailContent = styled.div`
  width: 100%;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
`;

const Toolbar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  gap: 8px;
`;

const ToolbarGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
`;

const EditorWrapper = styled.div`
  flex: 1;
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  overflow: hidden;
`;

const PreviewPanel = styled.div<{ $collapsed: boolean }>`
  flex-shrink: 0;
  height: ${props => props.$collapsed ? '36px' : '45%'};
  min-height: ${props => props.$collapsed ? '36px' : '120px'};
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: height 0.2s ease;
`;

const PreviewHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: rgba(30, 41, 59, 0.6);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  flex-shrink: 0;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: rgba(30, 41, 59, 0.8);
  }
`;

const PreviewBody = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
  background: rgba(15, 23, 42, 0.4);
  color: rgba(226, 232, 240, 0.9);
  font-size: 13px;
  line-height: 1.7;

  h1, h2, h3, h4, h5, h6 {
    color: rgba(248, 250, 252, 0.95);
    margin-top: 1em;
    margin-bottom: 0.5em;
  }
  h1 { font-size: 1.5em; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 0.3em; }
  h2 { font-size: 1.3em; }
  h3 { font-size: 1.1em; }
  code {
    background: rgba(51, 65, 85, 0.5);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
  }
  pre {
    background: rgba(15, 23, 42, 0.8);
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    code { background: none; padding: 0; }
  }
  table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.5em 0;
    th, td {
      border: 1px solid rgba(255,255,255,0.15);
      padding: 6px 10px;
      text-align: left;
    }
    th { background: rgba(30, 41, 59, 0.5); }
  }
  ul, ol { padding-left: 1.5em; }
  blockquote {
    border-left: 3px solid rgba(59, 130, 246, 0.5);
    padding-left: 12px;
    margin-left: 0;
    color: rgba(148, 163, 184, 0.9);
  }
`;

// Convert a Tool JSON object to a readable Markdown document
function toolToMarkdown(tool: any): string {
  const lines: string[] = [];
  lines.push(`# ${tool.name || 'Untitled Tool'}`);
  lines.push('');
  if (tool.description) {
    lines.push(`> ${tool.description}`);
    lines.push('');
  }

  // Basic info table
  lines.push('## Info');
  lines.push('');
  lines.push('| Field | Value |');
  lines.push('|-------|-------|');
  const infoFields = ['id', 'tool_type', 'version', 'status', 'level', 'path', 'owner', 'public', 'rentable', 'price', 'price_model', 'source'];
  for (const f of infoFields) {
    if (tool[f] !== undefined && tool[f] !== null && tool[f] !== '') {
      lines.push(`| **${f}** | \`${String(tool[f])}\` |`);
    }
  }
  lines.push('');

  // Input Schema
  if (tool.inputSchema) {
    lines.push('## Input Schema');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.inputSchema, null, 2));
    lines.push('```');
    lines.push('');

    // Render properties as a table if present
    const props = tool.inputSchema.properties;
    if (props && typeof props === 'object' && Object.keys(props).length > 0) {
      const required = tool.inputSchema.required || [];
      lines.push('### Input Properties');
      lines.push('');
      lines.push('| Property | Type | Required | Description |');
      lines.push('|----------|------|----------|-------------|');
      for (const [key, val] of Object.entries(props) as [string, any][]) {
        const type = val?.type || 'any';
        const req = required.includes(key) ? '\u2705' : '';
        const desc = val?.description || '';
        lines.push(`| **${key}** | \`${type}\` | ${req} | ${desc} |`);
      }
      lines.push('');
    }
  }

  // Output Schema
  if (tool.outputSchema) {
    lines.push('## Output Schema');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.outputSchema, null, 2));
    lines.push('```');
    lines.push('');
  }

  // Capabilities
  if (tool.capabilities && Array.isArray(tool.capabilities) && tool.capabilities.length > 0) {
    lines.push('## Capabilities');
    lines.push('');
    for (const c of tool.capabilities) {
      lines.push(`- ${typeof c === 'string' ? c : JSON.stringify(c)}`);
    }
    lines.push('');
  }

  // Limitations
  if (tool.limitations && Array.isArray(tool.limitations) && tool.limitations.length > 0) {
    lines.push('## Limitations');
    lines.push('');
    for (const l of tool.limitations) {
      lines.push(`- ${typeof l === 'string' ? l : JSON.stringify(l)}`);
    }
    lines.push('');
  }

  // Dependencies
  if (tool.dependencies && Array.isArray(tool.dependencies) && tool.dependencies.length > 0) {
    lines.push('## Dependencies');
    lines.push('');
    for (const d of tool.dependencies) {
      lines.push(`- ${typeof d === 'string' ? d : JSON.stringify(d)}`);
    }
    lines.push('');
  }

  // Config
  if (tool.config && typeof tool.config === 'object' && Object.keys(tool.config).length > 0) {
    lines.push('## Config');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.config, null, 2));
    lines.push('```');
    lines.push('');
  }

  // Settings
  if (tool.settings && typeof tool.settings === 'object' && Object.keys(tool.settings).length > 0) {
    lines.push('## Settings');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.settings, null, 2));
    lines.push('```');
    lines.push('');
  }

  // Annotations
  if (tool.annotations && typeof tool.annotations === 'object' && Object.keys(tool.annotations).length > 0) {
    lines.push('## Annotations');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.annotations, null, 2));
    lines.push('```');
    lines.push('');
  }

  // Meta
  if (tool.meta && typeof tool.meta === 'object' && Object.keys(tool.meta).length > 0) {
    lines.push('## Meta');
    lines.push('');
    lines.push('```json');
    lines.push(JSON.stringify(tool.meta, null, 2));
    lines.push('```');
    lines.push('');
  }

  return lines.join('\n');
}

const NEW_TOOL_TEMPLATE = {
  id: "",
  name: "",
  description: "",
  tool_type: "custom",
  version: "1.0",
  path: "",
  level: 0,
  config: {},
  capabilities: [],
  limitations: [],
  dependencies: [],
  public: false,
  rentable: false,
  price: 0,
  price_model: null,
  status: "active",
  settings: {},
  inputSchema: {
    type: "object",
    properties: {},
    required: []
  },
  meta: {}
};

type ViewFormat = 'json' | 'md';

const ToolDetail: React.FC<ToolDetailProps> = ({ tool, isAddingNew = false, onSaved, onCancelAdd }) => {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const forceRefresh = useToolStore((state) => state.forceRefresh);
  const [editorValue, setEditorValue] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [viewFormat, setViewFormat] = useState<ViewFormat>('json');
  const [mdSource, setMdSource] = useState<string>('');
  const [previewCollapsed, setPreviewCollapsed] = useState(false);

  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);

  // Update editor when tool changes or entering add mode
  useEffect(() => {
    if (isAddingNew) {
      const template = { ...NEW_TOOL_TEMPLATE };
      setEditorValue(JSON.stringify(template, null, 2));
      setMdSource(toolToMarkdown(template));
      setDirty(false);
    } else if (tool) {
      setEditorValue(JSON.stringify(tool, null, 2));
      setMdSource(toolToMarkdown(tool));
      setDirty(false);
    }
  }, [tool, isAddingNew]);

  // When switching to MD mode, regenerate markdown from current JSON
  const handleFormatSwitch = useCallback((fmt: ViewFormat) => {
    if (fmt === 'md' && viewFormat === 'json') {
      try {
        const parsed = JSON.parse(editorValue);
        setMdSource(toolToMarkdown(parsed));
      } catch {
        setMdSource(toolToMarkdown({ name: 'Parse Error', description: 'Could not parse JSON' }));
      }
    }
    setViewFormat(fmt);
  }, [viewFormat, editorValue]);

  // Track editor changes
  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setEditorValue(value);
      setDirty(true);
    }
  }, []);

  const handleMdEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setMdSource(value);
    }
  }, []);

  // Save handler
  const handleSave = useCallback(async () => {
    if (!username) {
      message.error('Please log in first');
      return;
    }

    let parsed: any;
    try {
      parsed = JSON.parse(editorValue);
    } catch (e) {
      message.error('Invalid JSON. Please fix syntax errors before saving.');
      return;
    }

    setSaving(true);
    try {
      const api = IPCAPI.getInstance();

      if (isAddingNew) {
        // Create new tool
        const resp = await api.newTools(username, [parsed]);
        if (resp.success) {
          message.success('Tool created successfully');
          setDirty(false);
          onSaved?.();
          await forceRefresh(username);
        } else {
          message.error((resp.error as any)?.message || 'Failed to create tool');
        }
      } else {
        // Update existing tool
        const toolId = parsed.id || tool?.id;
        if (!toolId) {
          message.error('Tool ID is missing');
          setSaving(false);
          return;
        }
        const resp = await api.saveTools(username, [{ ...parsed, id: toolId }]);
        if (resp.success) {
          message.success('Tool saved successfully');
          setDirty(false);
          onSaved?.();
          await forceRefresh(username);
        } else {
          message.error((resp.error as any)?.message || 'Failed to save tool');
        }
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [editorValue, username, tool, isAddingNew, onSaved, forceRefresh]);

  // 使用 useEffectOnActive 在ComponentActive时RestoreScrollPosition
  useEffectOnActive(
    () => {
      const container = scrollContainerRef.current;
      if (container && savedScrollPositionRef.current > 0) {
        requestAnimationFrame(() => {
          container.scrollTop = savedScrollPositionRef.current;
        });
      }

      return () => {
        const container = scrollContainerRef.current;
        if (container) {
          savedScrollPositionRef.current = container.scrollTop;
        }
      };
    },
    []
  );

  if (!tool && !isAddingNew) return <Empty description={t('pages.tools.selectTool')} />;

  return (
    <DetailContent ref={scrollContainerRef}>
      {/* Toolbar with format toggle */}
      <Toolbar>
        <ToolbarGroup>
          <Tooltip title="JSON view">
            <Button
              size="small"
              type={viewFormat === 'json' ? 'primary' : 'text'}
              icon={<CodeOutlined />}
              onClick={() => handleFormatSwitch('json')}
              style={{ fontSize: 12 }}
            >
              JSON
            </Button>
          </Tooltip>
          <Tooltip title="Markdown view">
            <Button
              size="small"
              type={viewFormat === 'md' ? 'primary' : 'text'}
              icon={<FileMarkdownOutlined />}
              onClick={() => handleFormatSwitch('md')}
              style={{ fontSize: 12 }}
            >
              MD
            </Button>
          </Tooltip>
        </ToolbarGroup>
        <ToolbarGroup>
          {/* Save/Cancel hidden while all tools are read-only */}
        </ToolbarGroup>
      </Toolbar>

      {viewFormat === 'json' ? (
        /* JSON mode - full Monaco editor */
        <EditorWrapper>
          <Editor
            value={editorValue}
            language="json"
            onChange={handleEditorChange}
            theme="vs-dark"
            height="100%"
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              automaticLayout: true,
              tabSize: 2,
              formatOnPaste: true,
              formatOnType: true,
            }}
          />
        </EditorWrapper>
      ) : (
        /* MD mode - split: source editor on top, collapsible preview at bottom */
        <>
          <EditorWrapper style={{ flex: previewCollapsed ? 1 : '0 1 55%' }}>
            <Editor
              value={mdSource}
              language="markdown"
              onChange={handleMdEditorChange}
              theme="vs-dark"
              height="100%"
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                automaticLayout: true,
                tabSize: 2,
              }}
            />
          </EditorWrapper>
          <PreviewPanel $collapsed={previewCollapsed}>
            <PreviewHeader onClick={() => setPreviewCollapsed(prev => !prev)}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'rgba(148, 163, 184, 0.9)' }}>
                Preview
              </span>
              <Tooltip title={previewCollapsed ? 'Expand preview' : 'Collapse preview'}>
                {previewCollapsed
                  ? <EyeOutlined style={{ fontSize: 14, color: 'rgba(148, 163, 184, 0.7)' }} />
                  : <EyeInvisibleOutlined style={{ fontSize: 14, color: 'rgba(148, 163, 184, 0.7)' }} />
                }
              </Tooltip>
            </PreviewHeader>
            {!previewCollapsed && (
              <PreviewBody>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {mdSource}
                </ReactMarkdown>
              </PreviewBody>
            )}
          </PreviewPanel>
        </>
      )}
    </DetailContent>
  );
};

export default ToolDetail;
