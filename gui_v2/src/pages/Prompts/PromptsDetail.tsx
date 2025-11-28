import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Input, Typography, Space, Button, Divider, Tooltip, message, Select } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  CopyOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  MinusCircleOutlined,
} from '@ant-design/icons';
import type { Prompt, SystemSection, SystemSectionType } from './types';
import { useTranslation } from 'react-i18next';

interface PromptsDetailProps {
  prompt: Prompt | null;
  onChange: (next: Prompt) => void;
}

const SECTION_LABELS: Record<SystemSectionType, string> = {
  roleCharacter: 'pages.prompts.sections.roleCharacter',
  tone: 'pages.prompts.sections.tone',
  background: 'pages.prompts.sections.background',
  goals: 'pages.prompts.sections.goals',
  guidelines: 'pages.prompts.sections.guidelines',
  rules: 'pages.prompts.sections.rules',
  examples: 'pages.prompts.sections.examples',
  instructions: 'pages.prompts.sections.instructions',
  variables: 'pages.prompts.sections.variables',
};

const SECTION_PLACEHOLDERS: Partial<Record<SystemSectionType, string>> = {
  roleCharacter: 'Describe the assistant role or persona',
  tone: 'Describe the tone or speaking style',
  background: 'Provide context or background information',
  goals: 'Add a goal',
  guidelines: 'Add a guideline',
  rules: 'Add a rule',
  instructions: 'Add an instruction',
  examples: 'Add an example',
  variables: 'Add a variable or input',
};

const SECTION_TYPE_OPTIONS: { labelKey: string; value: SystemSectionType }[] = [
  { labelKey: SECTION_LABELS.roleCharacter, value: 'roleCharacter' },
  { labelKey: SECTION_LABELS.tone, value: 'tone' },
  { labelKey: SECTION_LABELS.background, value: 'background' },
  { labelKey: SECTION_LABELS.goals, value: 'goals' },
  { labelKey: SECTION_LABELS.guidelines, value: 'guidelines' },
  { labelKey: SECTION_LABELS.rules, value: 'rules' },
  { labelKey: SECTION_LABELS.examples, value: 'examples' },
  { labelKey: SECTION_LABELS.instructions, value: 'instructions' },
  { labelKey: SECTION_LABELS.variables, value: 'variables' },
];

const SECTION_ORDER_PRIORITY: Record<SystemSectionType, number> = {
  roleCharacter: 0,
  tone: 1,
  background: 2,
  goals: 3,
  guidelines: 4,
  rules: 5,
  examples: 6,
  instructions: 7,
  variables: 8,
};

const tinyIconButtonBaseStyle: React.CSSProperties = {
  width: 18,
  height: 18,
  minWidth: 18,
  minHeight: 18,
  borderRadius: 4,
  border: '1px solid rgba(255,255,255,0.25)',
  background: 'rgba(255,255,255,0.05)',
  color: '#fff',
  padding: 0,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  transition: 'background 0.2s ease',
};

type TinyIconButtonProps = {
  icon: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  ariaLabel?: string;
};

const TinyIconButton: React.FC<TinyIconButtonProps> = ({ icon, onClick, disabled = false, ariaLabel }) => (
  <button
    type="button"
    onClick={disabled ? undefined : onClick}
    aria-label={ariaLabel}
    disabled={disabled}
    style={{
      ...tinyIconButtonBaseStyle,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.35 : 1,
    }}
  >
    {icon}
  </button>
);

const createSection = (type: SystemSectionType, items: string[] = [''], readOnly = false): SystemSection => ({
  id: `${type}_${Math.random().toString(36).slice(2, 10)}`,
  type,
  items,
  readOnly,
});

const trimItems = (items: string[]): string[] => items.map((item) => item.trim()).filter((item) => item.length > 0);

const sanitizeSections = (sections: SystemSection[]): SystemSection[] =>
  sections
    .map((section) => ({
      ...section,
      items: trimItems(section.items.length ? section.items : ['']),
    }))
    .filter((section) => section.items.length > 0 || section.readOnly);

const hydratePrompt = (source: Prompt | null): Prompt | null => {
  if (!source) return null;
  const clone: Prompt = {
    ...source,
    systemSections: (source.systemSections || []).map((section) => ({
      ...section,
      items: [...(section.items || [''])],
    })),
    examples: source.examples ? [...source.examples] : [],
    goals: [...(source.goals || [])],
    guidelines: [...(source.guidelines || [])],
    rules: [...(source.rules || [])],
    instructions: [...(source.instructions || [])],
    sysInputs: [...(source.sysInputs || [])],
    humanInputs: [...(source.humanInputs || [])],
  };

  if (!clone.systemSections || clone.systemSections.length === 0) {
    const sections: SystemSection[] = [];

    const roleContent = trimItems([source.roleToneContext || '']);
    sections.push(createSection('roleCharacter', roleContent.length ? roleContent : ['']));
    sections.push(createSection('tone', ['']));
    sections.push(createSection('background', ['']));

    const legacyMap: Array<{ key: keyof Prompt; type: SystemSectionType }> = [
      { key: 'goals', type: 'goals' },
      { key: 'guidelines', type: 'guidelines' },
      { key: 'rules', type: 'rules' },
      { key: 'instructions', type: 'instructions' },
    ];
    legacyMap.forEach(({ key, type }) => {
      const values = trimItems((source[key] as string[]) || []);
      if (values.length) {
        sections.push(createSection(type, values));
      }
    });

    const exampleItems = trimItems(source.examples || []);
    sections.push(createSection('examples', exampleItems.length ? exampleItems : ['']));

    const variableItems = trimItems(source.sysInputs || []);
    if (variableItems.length) {
      sections.push(createSection('variables', variableItems));
    }

    clone.systemSections = sections;
  }

  clone.systemSections = clone.systemSections
    .map((section) => ({
      ...section,
      items: section.items && section.items.length ? [...section.items] : [''],
    }))
    .sort((a, b) => SECTION_ORDER_PRIORITY[a.type] - SECTION_ORDER_PRIORITY[b.type]);

  if (!clone.examples) {
    clone.examples = [];
  }

  return clone;
};

const buildPromptForSave = (draft: Prompt): Prompt => {
  const sanitizedSections = sanitizeSections(draft.systemSections || []);

  const next: Prompt = {
    ...draft,
    systemSections: sanitizedSections,
  };

  const collect = (type: SystemSectionType): string[] =>
    sanitizedSections
      .filter((section) => section.type === type)
      .flatMap((section) => section.items)
      .map((item) => item.trim())
      .filter(Boolean);

  const roleParts: string[] = [];
  collect('roleCharacter').forEach((item) => roleParts.push(item));
  collect('tone').forEach((item) => roleParts.push(item));
  collect('background').forEach((item) => roleParts.push(item));

  next.roleToneContext = roleParts.join('\n\n');
  next.goals = collect('goals');
  next.guidelines = collect('guidelines');
  next.rules = collect('rules');
  next.instructions = collect('instructions');
  next.examples = collect('examples');
  next.sysInputs = collect('variables');

  if (!next.examples?.length) {
    next.examples = [];
  }

  return next;
};

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
          {!disabled && <Button danger icon={<DeleteOutlined />} onClick={() => onRemove(idx)} />}
        </div>
      ))}
      {!disabled && <Button icon={<PlusOutlined />} onClick={onAdd}>{t('common.add')}</Button>}
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
  const [newSectionType, setNewSectionType] = useState<SystemSectionType>('roleCharacter');

  useEffect(() => {
    setDraft(hydratePrompt(prompt));
    setEditing(false);
  }, [prompt?.id, prompt]);

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
    systemSections: [createSection('roleCharacter'), createSection('tone'), createSection('background'), createSection('examples')],
    examples: [],
  };
  const active = draft ?? emptyPrompt;

  const update = (patch: Partial<Prompt>) =>
    setDraft((prev) => ({ ...((prev ?? active) as Prompt), ...patch }));

  const updateSections = (updater: (sections: SystemSection[]) => SystemSection[]) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const nextSections = updater([...(prev.systemSections || [])]);
      return {
        ...prev,
        systemSections: nextSections,
      };
    });
  };

  const handleToggle = () => {
    if (!editing) {
      if (active.readOnly) {
        message.info(t('pages.prompts.readOnlyPrompt', { defaultValue: 'This prompt is read-only. Create a copy to edit.' }));
        return;
      }
      setEditing(true);
      return;
    }

    if (draft) {
      const prepared = buildPromptForSave(draft);
      setDraft(prepared);
      onChange(prepared);
    }
    setEditing(false);
  };

  const previewText = useMemo(() => {
    const lines: string[] = [];

    const sanitizedSections = sanitizeSections(active.systemSections || []);

    if (active.title) {
      lines.push(`# ${active.title}`);
    }

    sanitizedSections.forEach((section) => {
      const labelKey = SECTION_LABELS[section.type];
      const label = t(labelKey, { defaultValue: labelKey.split('.').pop()?.replace(/([A-Z])/g, ' $1') });
      lines.push(`${label}:`);
      section.items.forEach((item, idx) => {
        const content = item.trim();
        if (!content) return;
        const prefix = section.items.length > 1 ? `${idx + 1}. ` : '';
        lines.push(`${prefix}${content}`);
      });
    });

    if ((active.humanInputs || []).length) {
      lines.push(t('pages.prompts.preview.humanInputs', { defaultValue: 'Human inputs' }) + ':');
      active.humanInputs.forEach((item) => {
        const trimmed = typeof item === 'string' ? item.trim() : '';
        if (trimmed) lines.push(`- ${trimmed}`);
      });
    }

    return lines.join('\n');
  }, [active.systemSections, active.title, active.humanInputs, t]);

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
            value={typeof active.title === 'string' ? active.title : ''}
            onChange={(e) => update({ title: e.target.value })}
            placeholder={t('pages.prompts.placeholders.title', { defaultValue: 'Title' })}
            disabled={!editing}
            style={{ lineHeight: '20px', fontSize: 14 }}
          />
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section
          title={t('pages.prompts.sections.systemPrompt', { defaultValue: 'System prompt sections' })}
          extra={(
            <Space>
              <Select<SystemSectionType>
                size="small"
                value={newSectionType}
                onChange={(value) => setNewSectionType(value)}
                options={SECTION_TYPE_OPTIONS.map((option) => ({
                  label: t(option.labelKey, { defaultValue: option.labelKey.split('.').pop()?.replace(/([A-Z])/g, ' $1') }),
                  value: option.value,
                }))}
                disabled={!editing}
                style={{ minWidth: 200 }}
              />
              <Button
                icon={<PlusOutlined />}
                disabled={!editing}
                onClick={() => {
                  const typeToAdd = newSectionType;
                  setDraft((prev) => {
                    if (!prev) return prev;
                    const nextSections = [...(prev.systemSections || []), createSection(typeToAdd)];
                    return {
                      ...prev,
                      systemSections: nextSections,
                    };
                  });
                }}
              />
            </Space>
          )}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            {(active.systemSections || []).map((section, idx, arr) => {
              const disabled = !editing || section.readOnly || active.readOnly;
              const placeholder = SECTION_PLACEHOLDERS[section.type] || '';
              const labelKey = SECTION_LABELS[section.type];
              const title = t(labelKey, { defaultValue: labelKey.split('.').pop()?.replace(/([A-Z])/g, ' $1') });
              return (
                <Section
                  key={section.id}
                  title={`${title}`}
                  extra={(
                    <Space size={4}>
                      <Tooltip title={t('common.moveUp', { defaultValue: 'Move up' })}>
                        <TinyIconButton
                          icon={<ArrowUpOutlined style={{ fontSize: 10 }} />}
                          disabled={disabled || idx === 0}
                          ariaLabel={t('common.moveUp', { defaultValue: 'Move up' })}
                          onClick={() => {
                            if (disabled || idx === 0) return;
                            updateSections((sections) => {
                              const next = [...sections];
                              [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                              return next;
                            });
                          }}
                        />
                      </Tooltip>
                      <Tooltip title={t('common.moveDown', { defaultValue: 'Move down' })}>
                        <TinyIconButton
                          icon={<ArrowDownOutlined style={{ fontSize: 10 }} />}
                          disabled={disabled || idx === arr.length - 1}
                          ariaLabel={t('common.moveDown', { defaultValue: 'Move down' })}
                          onClick={() => {
                            if (disabled || idx === arr.length - 1) return;
                            updateSections((sections) => {
                              const next = [...sections];
                              [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
                              return next;
                            });
                          }}
                        />
                      </Tooltip>
                      {!disabled && (
                        <Tooltip title={t('common.remove', { defaultValue: 'Remove' })}>
                          <Button
                            icon={<DeleteOutlined />}
                            size="small"
                            danger
                            onClick={() => {
                              updateSections((sections) => sections.filter((s) => s.id !== section.id));
                            }}
                          />
                        </Tooltip>
                      )}
                    </Space>
                  )}
                >
                  <Space direction="vertical" style={{ width: '100%' }}>
                    {section.items.map((item, itemIdx) => (
                      <div key={`${section.id}-item-${itemIdx}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Typography.Text style={{ width: 28, color: 'rgba(255,255,255,0.65)', paddingTop: 4 }}>{`${itemIdx + 1})`}</Typography.Text>
                        <Input.TextArea
                          autoSize={autoSizeEnabled && !disabled ? { minRows: 2, maxRows: 6 } : undefined}
                          rows={autoSizeEnabled && !disabled ? undefined : 2}
                          value={item}
                          onChange={(e) => {
                            const value = e.target.value;
                            updateSections((sections) =>
                              sections.map((s) =>
                                s.id === section.id
                                  ? { ...s, items: s.items.map((existing, idxInner) => (idxInner === itemIdx ? value : existing)) }
                                  : s,
                              ),
                            );
                          }}
                          placeholder={placeholder ? t(`pages.prompts.placeholders.${section.type}`, { defaultValue: placeholder }) : undefined}
                          disabled={disabled}
                          style={{ flex: 1, lineHeight: '20px', fontSize: 14 }}
                        />
                        {!disabled && (
                          <Button
                            icon={<MinusCircleOutlined />}
                            danger
                            onClick={() => {
                              updateSections((sections) =>
                                sections
                                  .map((s) =>
                                    s.id === section.id
                                      ? { ...s, items: s.items.filter((_, idxInner) => idxInner !== itemIdx) }
                                      : s,
                                  )
                                  .filter((s) => s.items.length > 0),
                              );
                            }}
                          />
                        )}
                      </div>
                    ))}
                    {!disabled && (
                      <Button
                        icon={<PlusOutlined />}
                        onClick={() => {
                          updateSections((sections) =>
                            sections.map((s) =>
                              s.id === section.id
                                ? { ...s, items: [...s.items, ''] }
                                : s,
                            ),
                          );
                        }}
                      >
                        {t('common.add')}
                      </Button>
                    )}
                  </Space>
                </Section>
              );
            })}
          </Space>
        </Section>
        <Divider style={{ margin: '0 0 8px' }} />

        <Section title={t('pages.prompts.sections.humanInputs', { defaultValue: 'Human prompt: inputs' })}>
          <RepeatableList
            values={active.humanInputs}
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
