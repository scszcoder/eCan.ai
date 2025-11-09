import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Input, Typography, Space, Button, Divider, Tooltip, message } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, SaveOutlined, CopyOutlined } from '@ant-design/icons';
import type { Prompt } from './types';

interface PromptsDetailProps {
  prompt: Prompt | null;
  onChange: (next: Prompt) => void;
}

const Section: React.FC<{ title: string; extra?: React.ReactNode; style?: React.CSSProperties }>
  = ({ title, extra, style, children }) => (
  <div style={{ padding: 16, ...style }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
      <Typography.Text strong style={{ color: '#fff' }}>{title}</Typography.Text>
      {extra}
    </div>
    {children}
  </div>
);

const RepeatableList: React.FC<{
  values: string[];
  onAdd: () => void;
  onRemove: (idx: number) => void;
  onUpdate: (idx: number, val: string) => void;
  placeholder?: string;
}> = ({ values, onAdd, onRemove, onUpdate, placeholder }) => (
  <Space direction="vertical" style={{ width: '100%' }}>
    {values.map((v, idx) => (
      <div key={idx} style={{ display: 'flex', gap: 8, width: '100%', alignItems: 'flex-start' }}>
        <Input.TextArea
          autoSize={{ minRows: 2, maxRows: 6 }}
          value={v}
          onChange={(e) => onUpdate(idx, e.target.value)}
          placeholder={placeholder}
          style={{ flex: 1 }}
        />
        <Button danger icon={<DeleteOutlined />} onClick={() => onRemove(idx)} />
      </div>
    ))}
    <Button icon={<PlusOutlined />} onClick={onAdd}>Add</Button>
  </Space>
);

const PromptsDetail: React.FC<PromptsDetailProps> = ({ prompt, onChange }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Prompt | null>(prompt);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [topHeight, setTopHeight] = useState<number>(360); // px
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    setDraft(prompt);
    setEditing(false);
  }, [prompt?.id]);

  // Initialize topHeight as 60% of container height on mount
  useEffect(() => {
    const el = containerRef.current;
    if (el) {
      const h = el.clientHeight || 0;
      if (h > 0) setTopHeight(Math.max(200, Math.min(h - 150, Math.round(h * 0.6))));
    }
  }, []);

  // Drag handlers
  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!dragging || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      let next = e.clientY - rect.top; // distance from top of container
      const minTop = 200; // px
      const maxTop = rect.height - 150; // leave at least 150px for preview
      next = Math.max(minTop, Math.min(maxTop, next));
      setTopHeight(next);
      e.preventDefault();
    };
    const onUp = () => setDragging(false);
    if (dragging) {
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
    }
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragging]);

  if (!prompt || !draft) {
    return <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>Select a prompt to view details</div>;
  }

  const update = (patch: Partial<Prompt>) => setDraft({ ...draft, ...patch });

  const handleToggle = () => {
    if (editing && draft) {
      onChange(draft);
    }
    setEditing(!editing);
  };

  const previewText = useMemo(() => {
    const lines: string[] = [];
    if (draft.title) lines.push(`# ${draft.title}`);
    if (draft.roleToneContext) {
      lines.push('System: role/tone/context:');
      lines.push(draft.roleToneContext.trim());
    }
    const pushList = (label: string, arr: string[]) => {
      if (arr && arr.length) {
        lines.push(label + ':');
        arr.forEach((v, i) => { if (v?.trim()) lines.push(`- ${v.trim()}`); });
      }
    };
    pushList('Goals', draft.goals);
    pushList('Guidelines', draft.guidelines);
    pushList('Rules', draft.rules);
    pushList('Instructions', draft.instructions);
    pushList('System inputs', draft.sysInputs);
    pushList('Human inputs', draft.humanInputs);
    return lines.join('\n');
  }, [draft]);

  const copyPreview = async () => {
    try { await navigator.clipboard.writeText(previewText); message.success('Copied'); } catch {}
  };

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ height: topHeight, minHeight: 150, overflow: 'auto', paddingBottom: 8 }}>
        {/* Top editable area */}
        <Section
          title="Title"
          extra={
            <Button type={editing ? 'primary' : 'default'} icon={editing ? <SaveOutlined /> : <EditOutlined />} onClick={handleToggle}>
              {editing ? 'Save' : 'Edit'}
            </Button>
          }
        >
          <Input.TextArea
            autoSize={{ minRows: 2, maxRows: 6 }}
            value={draft.title}
            onChange={(e) => update({ title: e.target.value })}
            placeholder="Title"
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: role / tone / context">
          <Input.TextArea
            autoSize={{ minRows: 3, maxRows: 8 }}
            value={draft.roleToneContext}
            onChange={(e) => update({ roleToneContext: e.target.value })}
            placeholder="Describe the assistant role, tone, and context"
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: goals">
          <RepeatableList
            values={draft.goals}
            onAdd={() => update({ goals: [...draft.goals, ''] })}
            onRemove={(idx) => update({ goals: draft.goals.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ goals: draft.goals.map((g, i) => i === idx ? val : g) })}
            placeholder="Add a goal"
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: guidelines">
          <RepeatableList
            values={draft.guidelines}
            onAdd={() => update({ guidelines: [...draft.guidelines, ''] })}
            onRemove={(idx) => update({ guidelines: draft.guidelines.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ guidelines: draft.guidelines.map((g, i) => i === idx ? val : g) })}
            placeholder="Add a guideline"
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: rules">
          <RepeatableList
            values={draft.rules}
            onAdd={() => update({ rules: [...draft.rules, ''] })}
            onRemove={(idx) => update({ rules: draft.rules.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ rules: draft.rules.map((g, i) => i === idx ? val : g) })}
            placeholder="Add a rule"
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: instructions">
          <RepeatableList
            values={draft.instructions}
            onAdd={() => update({ instructions: [...draft.instructions, ''] })}
            onRemove={(idx) => update({ instructions: draft.instructions.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ instructions: draft.instructions.map((g, i) => i === idx ? val : g) })}
            placeholder="Add an instruction"
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="System prompt: inputs">
          <RepeatableList
            values={draft.sysInputs}
            onAdd={() => update({ sysInputs: [...draft.sysInputs, ''] })}
            onRemove={(idx) => update({ sysInputs: draft.sysInputs.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ sysInputs: draft.sysInputs.map((g, i) => i === idx ? val : g) })}
            placeholder="Add a system input"
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title="Human prompt: inputs">
          <RepeatableList
            values={draft.humanInputs}
            onAdd={() => update({ humanInputs: [...draft.humanInputs, ''] })}
            onRemove={(idx) => update({ humanInputs: draft.humanInputs.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ humanInputs: draft.humanInputs.map((g, i) => i === idx ? val : g) })}
            placeholder="Add a human input"
          />
        </Section>
      </div>

      {/* Drag handle divider */}
      <div
        onMouseDown={() => setDragging(true)}
        style={{
          height: 6,
          cursor: 'row-resize',
          background: 'linear-gradient(90deg, rgba(255,255,255,0.08), rgba(255,255,255,0.18), rgba(255,255,255,0.08))',
          borderTop: '1px solid rgba(255,255,255,0.08)',
          borderBottom: '1px solid rgba(0,0,0,0.2)'
        }}
        title="Drag to resize"
      />

      {/* Bottom preview panel */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16, position: 'relative' }}>
        <div style={{ position: 'absolute', top: 16, right: 16 }}>
          <Tooltip title="Copy preview">
            <Button icon={<CopyOutlined />} onClick={copyPreview} />
          </Tooltip>
        </div>
        <Typography.Text strong style={{ color: '#fff' }}>Preview</Typography.Text>
        <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', color: 'rgba(255,255,255,0.85)' }}>{previewText}</pre>
      </div>
    </div>
  );
};

export default PromptsDetail;
