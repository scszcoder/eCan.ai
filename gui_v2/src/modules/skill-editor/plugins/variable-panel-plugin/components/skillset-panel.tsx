/**
 * Skillset Panel — define named subsets of agent skills.
 * Usage in prompts: {{skillset_name}}
 */
import { useEffect, useState } from 'react';
import { Button, Input, Modal, Select, Tag, Typography } from '@douyinfe/semi-ui';
import { IconPlus, IconEdit2, IconDelete } from '@douyinfe/semi-icons';
import { useSkillInfoStore, type SkillsetDef } from '../../../stores/skill-info-store';
import { useSkillStore } from '../../../../../stores/domain/skillStore';
import { useUserStore } from '../../../../../stores/userStore';

const { Text } = Typography;

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
  initial?: SkillsetDef;
  existingNames: string[];
  onConfirm: (def: SkillsetDef) => void;
  onCancel: () => void;
}

function EditDialog({ visible, initial, existingNames, onConfirm, onCancel }: EditDialogProps) {
  const [name, setName] = useState(initial?.name ?? '');
  const [desc, setDesc] = useState(initial?.description ?? '');
  const [skillIds, setSkillIds] = useState<string[]>(initial?.skillIds ?? []);
  const [nameErr, setNameErr] = useState('');

  const skills = useSkillStore((s) => s.items);
  const username = useUserStore((s) => s.username);
  const fetchSkills = useSkillStore((s) => s.fetchItems);

  useEffect(() => {
    if (visible) {
      setName(initial?.name ?? '');
      setDesc(initial?.description ?? '');
      setSkillIds(initial?.skillIds ?? []);
      setNameErr('');
      if (skills.length === 0 && username) fetchSkills(username);
    }
  }, [visible]);

  const validateName = (v: string) => {
    if (!v.trim()) return 'Name is required';
    if (!VALID_NAME_RE.test(v)) return 'Only letters, digits and underscores allowed';
    if (RESERVED_NAMES.has(v)) return `"${v}" is a reserved built-in variable name`;
    if (existingNames.includes(v) && v !== initial?.name) return `"${v}" is already used by another skillset`;
    return '';
  };

  const handleConfirm = () => {
    const err = validateName(name);
    if (err) { setNameErr(err); return; }
    onConfirm({ name, description: desc || undefined, skillIds });
  };

  const skillOptions = skills.map((s) => ({ value: String(s.id), label: s.name || String(s.id) }));

  return (
    <Modal
      title={initial ? 'Edit Skillset' : 'New Skillset'}
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
          placeholder="e.g. support_skills"
          validateStatus={nameErr ? 'error' : undefined}
        />
        {nameErr && <Text type="danger" size="small">{nameErr}</Text>}
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          Use <code style={{ background: '#f0f0f0', padding: '0 3px' }}>{'{{' + (name || 'name') + '}}'}</code> in prompts
        </Text>
      </div>
      <div style={{ marginBottom: 16 }}>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>Description (optional)</Text>
        <Input value={desc} onChange={setDesc} placeholder="What these skills are for" />
      </div>
      <div>
        <Text strong style={{ display: 'block', marginBottom: 4 }}>Skills ({skillIds.length} selected)</Text>
        <Select
          multiple
          filter
          value={skillIds}
          onChange={(v) => setSkillIds(v as string[])}
          optionList={skillOptions}
          style={{ width: '100%' }}
          placeholder="Select skills to include"
          maxTagCount={5}
        />
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          Selected skills' name + description will be injected (same format as {'{{skills_schema}}'}).
        </Text>
      </div>
    </Modal>
  );
}

export function SkillsetPanel() {
  const skillsets = useSkillInfoStore((s) => s.skillsets);
  const setSkillsets = useSkillInfoStore((s) => s.setSkillsets);

  const [dialogVisible, setDialogVisible] = useState(false);
  const [editing, setEditing] = useState<SkillsetDef | undefined>(undefined);

  const existingNames = skillsets.map((s) => s.name);

  const handleAdd = () => { setEditing(undefined); setDialogVisible(true); };
  const handleEdit = (ss: SkillsetDef) => { setEditing(ss); setDialogVisible(true); };
  const handleDelete = (name: string) => setSkillsets(skillsets.filter((s) => s.name !== name));

  const handleConfirm = (def: SkillsetDef) => {
    if (editing) {
      setSkillsets(skillsets.map((s) => s.name === editing.name ? def : s));
    } else {
      setSkillsets([...skillsets, def]);
    }
    setDialogVisible(false);
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Text strong>Skillsets</Text>
        <Button icon={<IconPlus />} size="small" onClick={handleAdd}>Add</Button>
      </div>
      <Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 12 }}>
        Define named subsets of skills. Use <code>{'{{name}}'}</code> in prompts to inject the selected skills' summaries.
      </Text>

      {skillsets.length === 0 ? (
        <Text type="tertiary" size="small">No skillsets defined yet.</Text>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {skillsets.map((ss) => (
            <div
              key={ss.name}
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
                  <Tag color="green" size="small">
                    <code>{'{{' + ss.name + '}}'}</code>
                  </Tag>
                  <Text size="small" type="tertiary">{ss.skillIds.length} skills</Text>
                </div>
                {ss.description && (
                  <Text size="small" type="secondary" style={{ display: 'block', marginTop: 2 }}>
                    {ss.description}
                  </Text>
                )}
              </div>
              <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                <Button icon={<IconEdit2 />} size="small" theme="borderless" onClick={() => handleEdit(ss)} />
                <Button icon={<IconDelete />} size="small" theme="borderless" type="danger" onClick={() => handleDelete(ss.name)} />
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
