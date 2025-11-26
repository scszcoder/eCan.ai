import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Input, Typography, Space, Button, Divider, Tooltip, message } from 'antd';
import { PlusOutlined, DeleteOutlined, EditOutlined, SaveOutlined, CopyOutlined } from '@ant-design/icons';
import type { Prompt } from './types';
import { useTranslation } from 'react-i18next';

interface PromptsDetailProps {
  prompt: Prompt | null;
  onChange: (next: Prompt) => void;
}

type SectionProps = {
  title: string;
  extra?: React.ReactNode;
  style?: React.CSSProperties;
  children?: React.ReactNode;
};

const Section: React.FC<SectionProps>
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
  autoSizeEnabled?: boolean;
  disabled?: boolean;
}> = ({ values, onAdd, onRemove, onUpdate, placeholder, autoSizeEnabled = true, disabled = false }) => {
  const { t } = useTranslation();
  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {values.map((v, idx) => (
        <div key={idx} style={{ display: 'flex', gap: 8, width: '100%', alignItems: 'flex-start' }}>
          <Input.TextArea
            key={`rl-ta-${idx}-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && !disabled ? { minRows: 2, maxRows: 6 } : undefined}
            rows={autoSizeEnabled && !disabled ? undefined : 2}
            value={typeof v === 'string' ? v : (v == null ? '' : String(v))}
            onChange={(e) => onUpdate(idx, e.target.value)}
            placeholder={placeholder}
            style={{ flex: 1, lineHeight: '20px', fontSize: 14 }}
            disabled={disabled}
          />
          <Button danger icon={<DeleteOutlined />} onClick={() => onRemove(idx)} />
        </div>
      ))}
      <Button icon={<PlusOutlined />} onClick={onAdd}>{t('common.add')}</Button>
    </Space>
  );
};

const PromptsDetail: React.FC<PromptsDetailProps> = ({ prompt, onChange }) => {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Prompt | null>(prompt);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [topHeight, setTopHeight] = useState<number>(360); // px
  const [dragging, setDragging] = useState(false);
  const [autoSizeEnabled, setAutoSizeEnabled] = useState(false);

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

  // Enable TextArea autoSize only after the container has a measurable layout
  useEffect(() => {
    const checkLayoutReady = () => {
      const el = containerRef.current;
      if (!el) return false;
      const { clientWidth, clientHeight } = el;
      return clientWidth > 0 && clientHeight > 0;
    };

    if (checkLayoutReady()) {
      setAutoSizeEnabled(true);
      return;
    }

    let rafId: number | null = null;
    const tick = () => {
      if (checkLayoutReady()) {
        setAutoSizeEnabled(true);
      } else {
        rafId = requestAnimationFrame(tick);
      }
    };
    rafId = requestAnimationFrame(tick);
    const timer = setTimeout(() => setAutoSizeEnabled(true), 200); // final fallback
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      clearTimeout(timer);
    };
  }, [prompt, draft]);

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

  // Avoid early return before hooks to keep hook order stable
  const hasDraft = !!(prompt && draft);
  const emptyPrompt: Prompt = {
    id: '',
    title: '',
    topic: '',
    usageCount: 0,
    roleToneContext: '',
    goals: [],
    guidelines: [],
    rules: [],
    instructions: [],
    sysInputs: [],
    humanInputs: [],
  };
  const active = draft ?? emptyPrompt;

  const update = (patch: Partial<Prompt>) =>
    setDraft((prev) => ({ ...((prev ?? active) as Prompt), ...patch }));

  // Derive example slug from topic/title, with fallback matching against known examples
  const exampleSlug = useMemo(() => {
    const raw = (active.topic || active.title || '').toLowerCase();
    let slug = '';
    if (raw) slug = raw.replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
    if (slug) return slug;

    // Fallback: try to map localized titles to known example keys
    const knownKeys = [
      'write_a_marketing_email',
      // Add more keys here if needed in future
    ];
    const current = (active.title || active.topic || '').trim();
    for (const key of knownKeys) {
      // Some examples are simple strings, others have nested title
      const simple = t(`pages.prompts.examples.${key}`, { defaultValue: '' }) as unknown as string;
      const nested = t(`pages.prompts.examples.${key}.title`, { defaultValue: '' }) as unknown as string;
      if (current && (current === simple || current === nested)) {
        return key;
      }
    }
    return '';
  }, [active.topic, active.title, t]);

  // Helpers to localize display-only values (do not mutate underlying data)
  const safeString = (v: any) => (typeof v === 'string' ? v : (v == null ? '' : String(v)));
  const lx = (path: string, fallback: string) => {
    const translated = t(path, { defaultValue: fallback }) as unknown as string;
    if (!translated || translated === path) {
      return safeString(fallback);
    }
    return safeString(translated);
  };
  const localizeList = (baseKey: string, list: any) => {
    try {
      const arr = Array.isArray(list) ? list : [];
      return arr.map((v, i) => lx(`${baseKey}.${i}`, safeString(v)));
    } catch {
      return Array.isArray(list) ? list.map((v: any) => safeString(v)) : [];
    }
  };

  const handleToggle = () => {
    if (editing && draft) {
      onChange(draft);
    }
    setEditing(!editing);
  };

  const previewText = useMemo(() => {
    const lines: string[] = [];

    // Resolve display values with localization when showing built-in examples (non-editing + exampleSlug)
    const viewTitle = editing || !exampleSlug
      ? active.title
      : lx(`pages.prompts.examples.${exampleSlug}.title`, active.title);

    const viewRoleTone = editing || !exampleSlug
      ? active.roleToneContext
      : lx(`pages.prompts.examples.${exampleSlug}.roleToneContext`, active.roleToneContext);

    const viewGoals = (editing || !exampleSlug)
      ? active.goals
      : localizeList(`pages.prompts.examples.${exampleSlug}.goals`, active.goals);

    const viewGuidelines = (editing || !exampleSlug)
      ? active.guidelines
      : localizeList(`pages.prompts.examples.${exampleSlug}.guidelines`, active.guidelines);

    const viewRules = (editing || !exampleSlug)
      ? active.rules
      : localizeList(`pages.prompts.examples.${exampleSlug}.rules`, active.rules);

    const viewInstructions = (editing || !exampleSlug)
      ? active.instructions
      : localizeList(`pages.prompts.examples.${exampleSlug}.instructions`, active.instructions);

    const viewSysInputs = (editing || !exampleSlug)
      ? active.sysInputs
      : localizeList(`pages.prompts.examples.${exampleSlug}.sysInputs`, active.sysInputs);

    const viewHumanInputs = (editing || !exampleSlug)
      ? active.humanInputs
      : localizeList(`pages.prompts.examples.${exampleSlug}.humanInputs`, active.humanInputs);

    if (viewTitle) lines.push(`# ${safeString(viewTitle)}`);

    if (viewRoleTone) {
      lines.push(t('pages.prompts.preview.systemRoleToneContext', { defaultValue: 'System: role/tone/context' }) + ':');
      lines.push(safeString(viewRoleTone).trim());
    }

    const pushList = (label: string, arr: string[]) => {
      const list = Array.isArray(arr) ? arr : [];
      if (list.length) {
        lines.push(label + ':');
        list.forEach((v) => { const s = safeString(v).trim(); if (s) lines.push(`- ${s}`); });
      }
    };

    pushList(t('pages.prompts.preview.goals', { defaultValue: 'Goals' }), viewGoals);
    pushList(t('pages.prompts.preview.guidelines', { defaultValue: 'Guidelines' }), viewGuidelines);
    pushList(t('pages.prompts.preview.rules', { defaultValue: 'Rules' }), viewRules);
    pushList(t('pages.prompts.preview.instructions', { defaultValue: 'Instructions' }), viewInstructions);
    pushList(t('pages.prompts.preview.systemInputs', { defaultValue: 'System inputs' }), viewSysInputs);
    pushList(t('pages.prompts.preview.humanInputs', { defaultValue: 'Human inputs' }), viewHumanInputs);

    return lines.join('\n');
  }, [active, editing, exampleSlug, t]);

  const copyPreview = async () => {
    try { await navigator.clipboard.writeText(previewText); message.success(t('pages.prompts.copied', { defaultValue: 'Copied' })); } catch {}
  };

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {!hasDraft ? (
        <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>
          {t('pages.prompts.selectPrompt', { defaultValue: 'Select a prompt to view details' })}
        </div>
      ) : (
      <div style={{ height: topHeight, minHeight: 150, overflow: 'auto', paddingBottom: 8 }}>
        {/* Top editable area */}
        <Section
          title={t('pages.prompts.fields.title', { defaultValue: 'Title' })}
          extra={
            <Button type={editing ? 'primary' : 'default'} icon={editing ? <SaveOutlined /> : <EditOutlined />} onClick={handleToggle}>
              {editing ? t('common.save') : t('common.edit')}
            </Button>
          }
        >
          <Input.TextArea
            key={`title-ta-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
            rows={autoSizeEnabled && editing ? undefined : 2}
            value={safeString(editing ? active.title : (exampleSlug ? lx(`pages.prompts.examples.${exampleSlug}.title`, active.title) : active.title))}
            onChange={(e) => update({ title: e.target.value })}
            placeholder={t('pages.prompts.placeholders.title', { defaultValue: 'Title' })}
            disabled={!editing}
            style={{ lineHeight: '20px', fontSize: 14 }}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.roleToneContext', { defaultValue: 'System prompt: role / tone / context' })}>
          <Input.TextArea
            key={`rtc-ta-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && editing ? { minRows: 3, maxRows: 8 } : undefined}
            rows={autoSizeEnabled && editing ? undefined : 3}
            value={safeString(editing ? active.roleToneContext : (exampleSlug ? lx(`pages.prompts.examples.${exampleSlug}.roleToneContext`, active.roleToneContext) : active.roleToneContext))}
            onChange={(e) => update({ roleToneContext: e.target.value })}
            placeholder={t('pages.prompts.placeholders.roleToneContext', { defaultValue: 'Describe the assistant role, tone, and context' })}
            disabled={!editing}
            style={{ lineHeight: '20px', fontSize: 14 }}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.goals', { defaultValue: 'System prompt: goals' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.goals : localizeList(`pages.prompts.examples.${exampleSlug}.goals`, active.goals)}
            onAdd={() => update({ goals: [...active.goals, ''] })}
            onRemove={(idx) => update({ goals: active.goals.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ goals: active.goals.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addGoal', { defaultValue: 'Add a goal' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.guidelines', { defaultValue: 'System prompt: guidelines' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.guidelines : localizeList(`pages.prompts.examples.${exampleSlug}.guidelines`, active.guidelines)}
            onAdd={() => update({ guidelines: [...active.guidelines, ''] })}
            onRemove={(idx) => update({ guidelines: active.guidelines.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ guidelines: active.guidelines.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addGuideline', { defaultValue: 'Add a guideline' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.rules', { defaultValue: 'System prompt: rules' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.rules : localizeList(`pages.prompts.examples.${exampleSlug}.rules`, active.rules)}
            onAdd={() => update({ rules: [...active.rules, ''] })}
            onRemove={(idx) => update({ rules: active.rules.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ rules: active.rules.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addRule', { defaultValue: 'Add a rule' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.instructions', { defaultValue: 'System prompt: instructions' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.instructions : localizeList(`pages.prompts.examples.${exampleSlug}.instructions`, active.instructions)}
            onAdd={() => update({ instructions: [...active.instructions, ''] })}
            onRemove={(idx) => update({ instructions: active.instructions.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ instructions: active.instructions.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addInstruction', { defaultValue: 'Add an instruction' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.systemInputs', { defaultValue: 'System prompt: inputs' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.sysInputs : localizeList(`pages.prompts.examples.${exampleSlug}.sysInputs`, active.sysInputs)}
            onAdd={() => update({ sysInputs: [...active.sysInputs, ''] })}
            onRemove={(idx) => update({ sysInputs: active.sysInputs.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ sysInputs: active.sysInputs.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addSystemInput', { defaultValue: 'Add a system input' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.humanInputs', { defaultValue: 'Human prompt: inputs' })}>
          <RepeatableList
            values={editing || !exampleSlug ? active.humanInputs : localizeList(`pages.prompts.examples.${exampleSlug}.humanInputs`, active.humanInputs)}
            onAdd={() => update({ humanInputs: [...active.humanInputs, ''] })}
            onRemove={(idx) => update({ humanInputs: active.humanInputs.filter((_, i) => i !== idx) })}
            onUpdate={(idx, val) => update({ humanInputs: active.humanInputs.map((g, i) => i === idx ? val : g) })}
            placeholder={t('pages.prompts.placeholders.addHumanInput', { defaultValue: 'Add a human input' })}
            autoSizeEnabled={autoSizeEnabled}
            disabled={!editing}
          />
        </Section>
      </div>
      )}

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
        title={t('pages.prompts.dragToResize', { defaultValue: 'Drag to resize' })}
      />

      {/* Bottom preview panel */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16, position: 'relative' }}>
        <div style={{ position: 'absolute', top: 16, right: 16 }}>
          <Tooltip title={t('pages.prompts.copyPreview', { defaultValue: 'Copy preview' })}>
            <Button icon={<CopyOutlined />} onClick={copyPreview} />
          </Tooltip>
        </div>
        <Typography.Text strong style={{ color: '#fff' }}>{t('pages.prompts.preview.title', { defaultValue: 'Preview' })}</Typography.Text>
        <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', color: 'rgba(255,255,255,0.85)' }}>{previewText}</pre>
      </div>
    </div>
  );
};

export default PromptsDetail;
