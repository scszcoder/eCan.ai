import { useState, useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Modal, Input, Button, Typography } from '@douyinfe/semi-ui';
import { IconCodeStroked } from '@douyinfe/semi-icons';
import { IconInfoColored } from './colored-icons';
import { useCodeEditor } from '../code-editor';
import { useSkillInfoStore } from '../../stores/skill-info-store';

const { Text } = Typography;

export const Info = () => {
  const { document: workflowDocument } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const [visible, setVisible] = useState(false);
  const [editCodeVisible, setEditCodeVisible] = useState(false);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);

  // 直接用 skill-info-store 里的Data
  const skillId = skillInfo?.skillId || '';
  const skillName = skillInfo?.skillName || '';
  const version = skillInfo?.version || '';
  const lastModified = skillInfo?.lastModified || '';
  const jsonPreview = skillInfo ? JSON.stringify(skillInfo.workFlow, null, 2) : '';

  // CodeEdit器逻辑
  const handleCodeSave = useCallback((content: string) => {
    try {
      const data = JSON.parse(content);
      workflowDocument.clear();
      workflowDocument.fromJSON(data);
      setSkillInfo({ ...(skillInfo as any), workFlow: data, lastModified: new Date().toISOString() });
      setEditCodeVisible(false);
      return true;
    } catch (e) {
      return false;
    }
  }, [workflowDocument, setSkillInfo, skillInfo]);

  const { openEditor, editor } = useCodeEditor({
    initialContent: jsonPreview,
    language: 'json',
    onSave: handleCodeSave,
  });

  // skillName EditSave（只Update skill-info-store）
  const handleSkillNameChange = (v: string) => {
    if (skillInfo) {
      setSkillInfo({ ...skillInfo, skillName: v, lastModified: new Date().toISOString() });
    }
  };

  // OpenCodeEdit器
  const handleEditCode = () => {
    openEditor(jsonPreview);
    setEditCodeVisible(true);
  };

  return (
    <>
      <Tooltip content="Info">
        <IconButton
          type="tertiary"
          theme="borderless"
          icon={<IconInfoColored size={18} />}
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
            onChange={e => handleSkillNameChange(e)}
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