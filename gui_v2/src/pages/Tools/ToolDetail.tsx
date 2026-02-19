import React, { useRef, useState, useEffect, useCallback } from 'react';
import { useEffectOnActive } from 'keepalive-for-react';
import { Empty, Button, message } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import Editor from '@monaco-editor/react';
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

const EditorWrapper = styled.div`
  flex: 1;
  min-height: 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  overflow: hidden;
`;

const BottomBar = styled.div`
  display: flex;
  justify-content: flex-end;
  align-items: center;
  padding: 12px 0 0 0;
  gap: 8px;
  flex-shrink: 0;
`;

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

const ToolDetail: React.FC<ToolDetailProps> = ({ tool, isAddingNew = false, onSaved, onCancelAdd }) => {
  const { t } = useTranslation();
  const username = useUserStore((state) => state.username);
  const forceRefresh = useToolStore((state) => state.forceRefresh);
  const [editorValue, setEditorValue] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  
  // ScrollPositionSave
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const savedScrollPositionRef = useRef<number>(0);
  
  // Update editor when tool changes or entering add mode
  useEffect(() => {
    if (isAddingNew) {
      const template = { ...NEW_TOOL_TEMPLATE };
      setEditorValue(JSON.stringify(template, null, 2));
      setDirty(false);
    } else if (tool) {
      setEditorValue(JSON.stringify(tool, null, 2));
      setDirty(false);
    }
  }, [tool, isAddingNew]);
  
  // Track editor changes
  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setEditorValue(value);
      setDirty(true);
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
      <BottomBar>
        {isAddingNew && (
          <Button onClick={onCancelAdd}>
            Cancel
          </Button>
        )}
        <Button
          type="primary"
          icon={<SaveOutlined />}
          onClick={handleSave}
          loading={saving}
          disabled={!dirty && !isAddingNew}
        >
          {isAddingNew ? 'Create Tool' : 'Save'}
        </Button>
      </BottomBar>
    </DetailContent>
  );
};

export default ToolDetail;