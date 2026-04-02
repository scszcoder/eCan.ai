/**
 * Toolset Panel — define named subsets of MCP tools.
 * Usage in prompts: {{toolset_name}}
 */
import { useEffect, useState } from 'react';
import { Button, Input, Modal, Select, Tag, Typography } from '@douyinfe/semi-ui';
import { IconPlus, IconEdit2, IconDelete } from '@douyinfe/semi-icons';
import { useSkillInfoStore, type ToolsetDef } from '../../../stores/skill-info-store';
import { useToolStore } from '../../../../../stores/toolStore';
import { useUserStore } from '../../../../../stores/userStore';

const { Text } = Typography;

// Names that cannot be used as toolset/skillset variable names.
const RESERVED_NAMES = new Set([
  'skills_schema', 'tools_schema', 'current_time', 'current_time_local',
  'agent_name', 'agent_id', 'chat_id', 'task_id', 'human_input',
  'step_count', 'max_steps',
  'previous_node_output', 'latest_output', 'previous_node_id',
  'upstream_outputs', 'upstream_node_ids', 'search_keyword',
]);

const VALID_NAME_RE = /^\w+$/;

interface EditDialogProps {
  visible: boolean;
  initial?: ToolsetDef;
  existingNames: string[];
  onConfirm: (def: ToolsetDef) => void;
  onCancel: () => void;
}

function EditDialog({ visible, initial, existingNames, onConfirm, onCancel }: EditDialogProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [desc, setDesc] = useState(initial?.description ?? '');
  const [toolNames, setToolNames] = useState<string[]>(initial?.toolNames ?? []);
  const [nameErr, setNameErr] = useState('');

  const tools = useToolStore((s) => s.tools);
  const username = useUserStore((s) => s.username);
  const fetchTools = useToolStore((s) => s.fetchTools);

  useEffect(() => {
    if (visible) {
      setName(initial?.name ?? '');
      setDesc(initial?.description ?? '');
      setToolNames(initial?.toolNames ?? []);
      setNameErr('');
      if (tools.length === 0 && username) fetchTools(username);
    }
  }, [visible]);

  const validateName = (v: string) => {
    if (!v.trim()) return 'Name is required';
    if (!VALID_NAME_RE.test(v)) return 'Only letters, digits and underscores allowed';
    if (RESERVED_NAMES.has(v)) return `"${v}" is a reserved built-in variable name`;
    if (existingNames.includes(v) && v !== initial?.name) return `"${v}" is already used by another toolset`;
    return '';
  };

  const handleConfirm = () => {
    const err = validateName(name);
    if (err) { setNameErr(err); return; }
    onConfirm({ name, description: desc || undefined, toolNames });
  };

  const toolOptions = tools.map((t) => ({ value: t.name, label: t.name }));

  return (
    <Modal
      title={initial ? 'Edit Toolset' : 'New Toolset'}
      visible={visible}
      onOk={handleConfirm}
      onCancel={onCancel}
      width={480}
    >
      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>Variable name *</Text>
        <Input
          value={name}
          onChange={(v) => { setName(v); setNameErr(validateName(v)); }}
          placeholder="e.g. browser_tools"
          validateStatus={nameErr ? 'error' : undefined}
        />
        {nameErr && <Text type="danger" size="small">{nameErr}</Text>}
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          Use <code style={{ background: '#f0f0f0', padding: '0 3px' }}>{'{{' + (name || 'name') + '}}'}</code> in prompts
        </Text>
      </div>
      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>Description (optional)</Text>
        <Input value={desc} onChange={setDesc} placeholder="What these tools are for" />
      </div>
      <div>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>Tools ({toolNames.length} selected)</Text>
        <Select
          multiple
          filter
          value={toolNames}
          onChange={(v) => setToolNames(v as string[])}
          optionList={toolOptions}
          style={{ width: '100%' }}
          placeholder="Select tools to include"
          maxTagCount={5}
        />
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          Only the selected tools' schemas will be injected into the prompt.
        </Text>
      </div>
    </Modal>
  );
}

export function ToolsetPanel() {
  const toolsets = useSkillInfoStore((s) => s.toolsets);
  const setToolsets = useSkillInfoStore((s) => s.setToolsets);

  const [dialogVisible, setDialogVisible] = useState(false);
  const [editing, setEditing] = useState<ToolsetDef | undefined>(undefined);

  const existingNames = toolsets.map((t) => t.name);

  const handleAdd = () => { setEditing(undefined); setDialogVisible(true); };
  const handleEdit = (ts: ToolsetDef) => { setEditing(ts); setDialogVisible(true); };
  const handleDelete = (name: string) => setToolsets(toolsets.filter((t) => t.name !== name));

  const handleConfirm = (def: ToolsetDef) => {
    if (editing) {
      setToolsets(toolsets.map((t) => t.name === editing.name ? def : t));
    } else {
      setToolsets([...toolsets, def]);
    }
    setDialogVisible(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text strong>Toolsets</Text>
        <Button icon={<IconPlus />} size="small" onClick={handleAdd}>Add</Button>
      </div>
      <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 12 }}>
        Define named subsets of tools. Use <code>{'{{name}}'}</code> in prompts to inject the selected tools' schemas.
      </Text>

      {toolsets.length === 0 ? (
        <Text type="tertiary" size="small">No toolsets defined yet.</Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {toolsets.map((ts) => (
            <div
              key={ts.name}
              style={{
                border: '1px solid #e8e8e8',
                borderRadius: 6,
                padding: '8px 12px',
                display: 'flex',
                alignItems: 'flex-start',
                justifyContent: 'space-between',
                gap: 8,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <Tag color="blue" size="small">
                    <code>{'{{' + ts.name + '}}'}</code>
                  </Tag>
                  <Text size="small" type="tertiary">{ts.toolNames.length} tools</Text>
                </div>
                {ts.description && (
                  <Text size="small" type="secondary" style={{ display: 'block', marginTop: 2 }}>
                    {ts.description}
                  </Text>
                )}
              </div>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                <Button icon={<IconEdit2 />} size="small" theme="borderless" onClick={() => handleEdit(ts)} />
                <Button icon={<IconDelete />} size="small" theme="borderless" type="danger" onClick={() => handleDelete(ts.name)} />
              </div>
            </div>
          ))}
        </div>
      )}

      <EditDialog
        visible={dialogVisible}
        initial={editing}
        existingNames={existingNames}
        onConfirm={handleConfirm}
        onCancel={() => setDialogVisible(false)}
      />
    </div>
  );
}
