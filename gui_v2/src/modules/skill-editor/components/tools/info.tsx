import { useState, useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Modal, Input, Button, Typography } from '@douyinfe/semi-ui';
import { IconInfoCircle, IconCodeStroked } from '@douyinfe/semi-icons';
import { useCodeEditor } from '../code-editor';

const { Text } = Typography;

export const Info = () => {
  const { document: workflowDocument } = useClientContext();
  // skillId/skillName/version/lastModified 挂载在 meta 字段
  const meta = (workflowDocument as any).meta || {};
  const [visible, setVisible] = useState(false);
  const [editCodeVisible, setEditCodeVisible] = useState(false);
  const [skillName, setSkillName] = useState<string>(() => meta.skillName || '');
  const skillId = meta.skillId || '';
  const version = meta.version || '';
  const lastModified = meta.lastModified || '';
  const [jsonPreview, setJsonPreview] = useState<string>(() => JSON.stringify(workflowDocument.toJSON(), null, 2));

  // 代码编辑器逻辑
  const handleCodeSave = useCallback((content: string) => {
    try {
      const data = JSON.parse(content);
      workflowDocument.clear();
      workflowDocument.fromJSON(data);
      setJsonPreview(JSON.stringify(data, null, 2));
      setEditCodeVisible(false);
      return true;
    } catch (e) {
      return false;
    }
  }, [workflowDocument]);

  const { openEditor, editor } = useCodeEditor({
    initialContent: jsonPreview,
    language: 'json',
    onSave: handleCodeSave,
  });

  // skillName 编辑保存
  const handleSkillNameChange = (v: string) => {
    setSkillName(v);
    if (!(workflowDocument as any).meta) (workflowDocument as any).meta = {};
    (workflowDocument as any).meta.skillName = v;
  };

  // 打开代码编辑器
  const handleEditCode = () => {
    openEditor(jsonPreview);
    setEditCodeVisible(true);
  };

  return (
    <>
      <Tooltip content={skillName || 'Edit Skill'}>
        <IconButton
          type="tertiary"
          theme="borderless"
          icon={<IconInfoCircle />}
          onClick={() => setVisible(true)}
        />
      </Tooltip>
      <Modal
        title="Edit Skill Info"
        visible={visible}
        onCancel={() => setVisible(false)}
        footer={null}
        width={700}
      >
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center' }}>
          <Text type="secondary" style={{ minWidth: 100, textAlign: 'right', display: 'inline-block' }}>Skill ID:</Text>
          <Text copyable style={{ marginLeft: 16 }}>{skillId}</Text>
        </div>
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center' }}>
          <Text type="secondary" style={{ minWidth: 100, textAlign: 'right', display: 'inline-block' }}>Skill Name:</Text>
          <Input
            value={skillName}
            onChange={handleSkillNameChange}
            style={{ width: 300, marginLeft: 16 }}
            placeholder="Enter skill name"
          />
        </div>
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center' }}>
          <Text type="secondary" style={{ minWidth: 100, textAlign: 'right', display: 'inline-block' }}>Version:</Text>
          <Text style={{ marginLeft: 16 }}>{version}</Text>
        </div>
        <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center' }}>
          <Text type="secondary" style={{ minWidth: 100, textAlign: 'right', display: 'inline-block' }}>Last Modified:</Text>
          <Text style={{ marginLeft: 16 }}>{lastModified}</Text>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
          <Text type="secondary" style={{ flex: 1 }}>Code Preview:</Text>
          <Button icon={<IconCodeStroked />} size="small" onClick={handleEditCode} style={{ marginLeft: 8 }}>
            Edit Code
          </Button>
        </div>
        <pre
          className="code-block"
          style={{
            maxHeight: 320,
            minHeight: 200,
            background: 'var(--bg-tertiary)',
            color: 'var(--text-primary)',
            fontSize: 14,
            border: '1px solid var(--border-color)',
            boxShadow: 'var(--shadow-sm)',
            marginBottom: '20px',
            overflow: 'auto',
          }}
        >
          {jsonPreview}
        </pre>
      </Modal>
      {editCodeVisible && editor}
    </>
  );
}; 