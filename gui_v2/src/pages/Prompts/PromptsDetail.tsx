import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Input, Typography, Space, Button, Divider, Tooltip, Select, message, Card } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  CopyOutlined,
  ArrowUpOutlined,
  ArrowDownOutlined,
  AppstoreAddOutlined,
  UndoOutlined,
  RedoOutlined,
} from '@ant-design/icons';
import type { Prompt, PromptSection, PromptSectionType } from './types';
import { useTranslation } from 'react-i18next';
import styles from './PromptsDetail.module.css';

interface PromptsDetailProps {
  prompt: Prompt | null;
  onChange: (next: Prompt) => void;
}

const { TextArea } = Input;

const SectionContainer: React.FC<{
  title: string;
  extra?: React.ReactNode;
  children?: React.ReactNode;
}> = ({ title, extra, children }) => (
  <Card
    size="small"
    bordered={false}
    style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
    bodyStyle={{ padding: 16 }}
    title={<Typography.Text strong style={{ color: '#fff' }}>{title}</Typography.Text>}
    extra={extra}
  >
    {children}
  </Card>
);

const SECTION_LABELS: Record<PromptSectionType, string> = {
  role: 'Role / Character',
  tone: 'Tone',
  background: 'Background',
  goals: 'Goals',
  guidelines: 'Guidelines',
  rules: 'Rules',
  instructions: 'Instructions',
  examples: 'Examples',
  variables: 'Variables',
  additional: 'Additional Text',
  custom: 'Custom Section',
};

const SECTION_PLACEHOLDERS: Partial<Record<PromptSectionType, string>> = {
  role: 'Describe the assistant persona, responsibilities, seniority…',
  tone: 'Specify desired tone/mood…',
  background: 'Provide contextual background for the assistant…',
  goals: 'Add a goal…',
  guidelines: 'Add a guideline…',
  rules: 'Add a rule or constraint…',
  examples: 'Add an example instruction/output…',
  instructions: 'Add a numbered instruction…',
  variables: 'Add a variable placeholder, e.g. {{customer_name}}…',
  additional: 'Add additional text or context…',
  custom: 'Add custom content…',
};

const AVAILABLE_SECTION_TYPES: { value: PromptSectionType; label: string }[] = (
  Object.entries(SECTION_LABELS) as Array<[PromptSectionType, string]>
).map(([value, label]) => ({ value, label }));

const DEFAULT_PROMPT: Prompt = {
  id: '',
  title: '',
  topic: '',
  usageCount: 0,
  sections: [],
  userSections: [],
  humanInputs: [],
  source: 'my_prompts',
  readOnly: false,
};

const HISTORY_LIMIT = 250;

const PromptsDetail: React.FC<PromptsDetailProps> = ({ prompt, onChange }) => {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Prompt | null>(prompt);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [topHeight, setTopHeight] = useState<number>(360); // px
  const [dragging, setDragging] = useState(false);
  const [autoSizeEnabled, setAutoSizeEnabled] = useState(false);
  const undoStackRef = useRef<Prompt[]>([]);
  const redoStackRef = useRef<Prompt[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const clonePrompt = useCallback((value: Prompt): Prompt => JSON.parse(JSON.stringify(value)), []);

  const pushUndoStack = useCallback((snapshot: Prompt) => {
    const stack = undoStackRef.current;
    stack.push(clonePrompt(snapshot));
    if (stack.length > HISTORY_LIMIT) {
      stack.shift();
    }
    redoStackRef.current = [];
    setCanUndo(stack.length > 0);
    setCanRedo(false);
  }, [clonePrompt]);

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

  useEffect(() => {
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }, [editing, prompt?.id]);

  // Avoid early return before hooks to keep hook order stable
  const hasDraft = !!(prompt && draft);
  const active = draft ?? DEFAULT_PROMPT;

  const update = useCallback((mutator: (prev: Prompt) => Prompt) => {
    setDraft((prev) => {
      const current = prev ?? DEFAULT_PROMPT;
      const next = mutator(clonePrompt(current));
      if (editing && !current.readOnly) {
        pushUndoStack(current);
      }
      return next;
    });
  }, [editing, pushUndoStack, clonePrompt]);

  const updateFields = (patch: Partial<Prompt>) =>
    update((prev) => ({ ...prev, ...patch }));

  const isEditable = editing && !active.readOnly;
  const isReadOnly = !isEditable;

  const sortedSections = useMemo(() => active.sections ?? [], [active.sections]);

  const handleSectionChange = (sectionId: string, items: string[]) => {
    update((prev) => ({
      ...prev,
      sections: prev.sections.map((sec) =>
        sec.id === sectionId ? { ...sec, items: items.length ? items : [''] } : sec
      ),
    }));
  };

  const handleSectionRemove = (sectionId: string) => {
    update((prev) => ({
      ...prev,
      sections: prev.sections.filter((sec) => sec.id !== sectionId),
    }));
  };

  const handleSectionMove = (sectionId: string, direction: -1 | 1) => {
    update((prev) => {
      const sections = [...prev.sections];
      const index = sections.findIndex((sec) => sec.id === sectionId);
      if (index === -1) return prev;
      const newIndex = index + direction;
      if (newIndex < 0 || newIndex >= sections.length) return prev;
      [sections[index], sections[newIndex]] = [sections[newIndex], sections[index]];
      return { ...prev, sections };
    });
  };

  const handleSectionAdd = (type: PromptSectionType) => {
    const newSection: PromptSection = {
      id: `${type}-${Date.now()}`,
      type,
      items: [''],
      customLabel: type === 'custom' ? (customSectionName.trim() || 'Custom Section') : undefined,
    };
    update((prev) => ({
      ...prev,
      sections: [...prev.sections, newSection],
    }));
    if (type === 'custom') {
      setCustomSectionName('');
    }
  };

  const handleSectionItemAdd = (sectionId: string) => {
    update((prev) => ({
      ...prev,
      sections: prev.sections.map((sec) =>
        sec.id === sectionId ? { ...sec, items: [...sec.items, ''] } : sec
      ),
    }));
  };

  const handleSectionItemRemove = (sectionId: string, index: number) => {
    update((prev) => ({
      ...prev,
      sections: prev.sections
        .map((sec) =>
          sec.id === sectionId
            ? { ...sec, items: sec.items.filter((_, idx) => idx !== index) }
            : sec
        )
        .filter((sec) => sec.items.length > 0),
    }));
  };

  const handleSectionItemUpdate = (sectionId: string, index: number, value: string) => {
    update((prev) => ({
      ...prev,
      sections: prev.sections.map((sec) =>
        sec.id === sectionId
          ? {
              ...sec,
              items: sec.items.map((item, idx) => (idx === index ? value : item)),
            }
          : sec
      ),
    }));
  };

  const handleHumanInputMove = (index: number, direction: -1 | 1) => {
    update((prev) => {
      const inputs = [...prev.humanInputs];
      const newIndex = index + direction;
      if (newIndex < 0 || newIndex >= inputs.length) return prev;
      [inputs[index], inputs[newIndex]] = [inputs[newIndex], inputs[index]];
      return { ...prev, humanInputs: inputs };
    });
  };

  const handleRemoveAllSections = () => {
    update((prev) => ({
      ...prev,
      sections: [],
    }));
  };

  const handleUserSectionChange = (sectionId: string, items: string[]) => {
    update((prev) => ({
      ...prev,
      userSections: prev.userSections.map((sec) =>
        sec.id === sectionId ? { ...sec, items: items.length ? items : [''] } : sec
      ),
    }));
  };

  const handleUserSectionRemove = (sectionId: string) => {
    update((prev) => ({
      ...prev,
      userSections: prev.userSections.filter((sec) => sec.id !== sectionId),
    }));
  };

  const handleUserSectionMove = (sectionId: string, direction: -1 | 1) => {
    update((prev) => {
      const sections = [...prev.userSections];
      const index = sections.findIndex((sec) => sec.id === sectionId);
      if (index === -1) return prev;
      const newIndex = index + direction;
      if (newIndex < 0 || newIndex >= sections.length) return prev;
      [sections[index], sections[newIndex]] = [sections[newIndex], sections[index]];
      return { ...prev, userSections: sections };
    });
  };

  const handleUserSectionAdd = (type: PromptSectionType) => {
    const newSection: PromptSection = {
      id: `user-${type}-${Date.now()}`,
      type,
      items: [''],
      customLabel: type === 'custom' ? (customUserSectionName.trim() || 'Custom Section') : undefined,
    };
    update((prev) => ({
      ...prev,
      userSections: [...prev.userSections, newSection],
    }));
    if (type === 'custom') {
      setCustomUserSectionName('');
    }
  };

  const handleUserSectionItemAdd = (sectionId: string) => {
    update((prev) => ({
      ...prev,
      userSections: prev.userSections.map((sec) =>
        sec.id === sectionId ? { ...sec, items: [...sec.items, ''] } : sec
      ),
    }));
  };

  const handleUserSectionItemRemove = (sectionId: string, index: number) => {
    update((prev) => ({
      ...prev,
      userSections: prev.userSections
        .map((sec) =>
          sec.id === sectionId
            ? { ...sec, items: sec.items.filter((_, idx) => idx !== index) }
            : sec
        )
        .filter((sec) => sec.items.length > 0),
    }));
  };

  const handleUserSectionItemUpdate = (sectionId: string, index: number, value: string) => {
    update((prev) => ({
      ...prev,
      userSections: prev.userSections.map((sec) =>
        sec.id === sectionId
          ? {
              ...sec,
              items: sec.items.map((item, idx) => (idx === index ? value : item)),
            }
          : sec
      ),
    }));
  };

  const handleRemoveAllUserSections = () => {
    update((prev) => ({
      ...prev,
      userSections: [],
    }));
  };

  const [sectionToAdd, setSectionToAdd] = useState<PromptSectionType>('role');
  const [userSectionToAdd, setUserSectionToAdd] = useState<PromptSectionType>('goals');
  const [customSectionName, setCustomSectionName] = useState<string>('');
  const [customUserSectionName, setCustomUserSectionName] = useState<string>('');

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
    if (active.readOnly) {
      message.info(t('pages.prompts.readOnly', { defaultValue: 'This prompt is read-only.' }));
      return;
    }
    if (editing && draft) {
      onChange(draft);
    }
    setEditing((prev) => !prev);
  };

  const handleUndo = useCallback(() => {
    if (!editing || !undoStackRef.current.length) return;
    setDraft((prev) => {
      const current = prev ?? DEFAULT_PROMPT;
      const stack = undoStackRef.current;
      const previous = stack.pop();
      if (!previous) return current;
      redoStackRef.current.push(clonePrompt(current));
      setCanUndo(stack.length > 0);
      setCanRedo(true);
      return previous;
    });
  }, [editing, clonePrompt]);

  const handleRedo = useCallback(() => {
    if (!editing || !redoStackRef.current.length) return;
    setDraft((prev) => {
      const current = prev ?? DEFAULT_PROMPT;
      const stack = redoStackRef.current;
      const nextState = stack.pop();
      if (!nextState) return current;
      undoStackRef.current.push(clonePrompt(current));
      setCanRedo(stack.length > 0);
      setCanUndo(true);
      return nextState;
    });
  }, [editing, clonePrompt]);

  const previewText = useMemo(() => {
    const lines: string[] = [];

    // Resolve display values with localization when showing built-in examples (non-editing + exampleSlug)
    const viewTitle = editing || !exampleSlug
      ? active.title
      : lx(`pages.prompts.examples.${exampleSlug}.title`, active.title);

    if (viewTitle) lines.push(`# ${safeString(viewTitle)}`);
    lines.push(''); // blank line

    // Helper to render sections in tagged Markdown format
    const renderSectionsTagged = (sections: PromptSection[]) => {
      const sectionsToRender = (editing || !exampleSlug)
        ? sections
        : sections.map((section) => {
            const localizedItems = localizeList(
              `pages.prompts.examples.${exampleSlug}.${section.type}`,
              section.items,
            );
            return { ...section, items: localizedItems };
          });

      sectionsToRender.forEach((section) => {
        if (!section.items.length) return;
        // Use customLabel if available, otherwise use standard label
        const label = section.customLabel || SECTION_LABELS[section.type] || section.type;
        // Convert label to valid XML tag name (lowercase, replace spaces/special chars with underscore)
        const tagName = label.toLowerCase().replace(/[^a-z0-9_]/g, '_');
        
        lines.push(`<${tagName}>`);
        section.items.forEach((item) => {
          const trimmed = safeString(item).trim();
          if (!trimmed) return;
          lines.push(`- ${trimmed}`);
        });
        lines.push(`</${tagName}>`);
        lines.push(''); // blank line between sections
      });
    };

    // Render system prompt sections
    if (sortedSections.length > 0) {
      lines.push('<system_prompt>');
      renderSectionsTagged(sortedSections);
      lines.push('</system_prompt>');
      lines.push('');
    }

    // Render user prompt sections
    const userSections = active.userSections || [];
    if (userSections.length > 0) {
      lines.push('<user_prompt>');
      renderSectionsTagged(userSections);
      lines.push('</user_prompt>');
    }

    return lines.join('\n');
  }, [active, editing, exampleSlug, sortedSections, t]);

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
        <>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid rgba(148,163,184,0.18)',
          background: 'rgba(15,23,42,0.75)',
          zIndex: 2,
        }}>
          <Typography.Title level={4} style={{ margin: 0, color: '#fff' }}>
            {active.title || t('pages.prompts.details', { defaultValue: 'Prompt Details' })}
          </Typography.Title>
          <Space size={8}>
            <Tooltip title={t('common.undo', { defaultValue: 'Undo' })}>
              <Button
                type="text"
                size="small"
                icon={<UndoOutlined />}
                onClick={handleUndo}
                disabled={!editing || !canUndo}
                className={styles.smallButton}
              />
            </Tooltip>
            <Tooltip title={t('common.redo', { defaultValue: 'Redo' })}>
              <Button
                type="text"
                size="small"
                icon={<RedoOutlined />}
                onClick={handleRedo}
                disabled={!editing || !canRedo}
                className={styles.smallButton}
              />
            </Tooltip>
            <Button
              type={editing ? 'primary' : 'default'}
              size="small"
              icon={editing ? <SaveOutlined /> : <EditOutlined />}
              onClick={handleToggle}
              className={styles.smallButtonWithText}
            >
              {editing ? t('common.save') : t('common.edit')}
            </Button>
          </Space>
        </div>
      <div style={{ height: topHeight, minHeight: 150, overflow: 'auto', paddingBottom: 8 }}>
        {/* Top editable area */}
        <SectionContainer
          title={t('pages.prompts.fields.title', { defaultValue: 'Title' })}
        >
          <TextArea
            key={`title-ta-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
            rows={autoSizeEnabled && editing ? undefined : 2}
            value={safeString(editing ? active.title : (exampleSlug ? lx(`pages.prompts.examples.${exampleSlug}.title`, active.title) : active.title))}
            onChange={(e) => updateFields({ title: e.target.value })}
            placeholder={t('pages.prompts.placeholders.title', { defaultValue: 'Title' })}
            disabled={isReadOnly}
            style={{ lineHeight: '20px', fontSize: 14 }}
          />
          <Divider style={{ margin: '16px 0' }} />
          <TextArea
            key={`topic-ta-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 4 } : undefined}
            rows={autoSizeEnabled && editing ? undefined : 2}
            value={safeString(active.topic)}
            onChange={(e) => updateFields({ topic: e.target.value })}
            placeholder={t('pages.prompts.placeholders.topic', { defaultValue: 'Topic / short description' })}
            disabled={isReadOnly}
            style={{ lineHeight: '20px', fontSize: 14 }}
          />
        </SectionContainer>

        <Divider style={{ margin: '16px 0' }} />

        <SectionContainer
          title={t('pages.prompts.sections.systemPrompt', { defaultValue: 'System Prompt Sections' })}
          extra={
            <Space>
              <Select
                size="small"
                value={sectionToAdd}
                onChange={(value: PromptSectionType) => setSectionToAdd(value)}
                options={AVAILABLE_SECTION_TYPES.map(({ value, label }) => ({
                  value,
                  label: t(`pages.prompts.sectionLabels.${value}`, { defaultValue: label }),
                }))}
                style={{ minWidth: 180 }}
                disabled={!isEditable}
              />
              {sectionToAdd === 'custom' && (
                <Input
                  size="small"
                  value={customSectionName}
                  onChange={(e) => setCustomSectionName(e.target.value)}
                  placeholder="Custom section name"
                  style={{ width: 150 }}
                  disabled={!isEditable}
                />
              )}
              <Tooltip title={t('pages.prompts.addSection', { defaultValue: 'Add section' })}>
                <Button
                  type="primary"
                  size="small"
                  icon={<AppstoreAddOutlined />}
                  onClick={() => handleSectionAdd(sectionToAdd)}
                  disabled={!isEditable}
                  className={styles.smallButton}
                />
              </Tooltip>
              <Tooltip title={t('pages.prompts.removeAllSections', { defaultValue: 'Remove all sections' })}>
                <Button
                  danger
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={handleRemoveAllSections}
                  disabled={!isEditable || sortedSections.length === 0}
                  className={styles.tinyIconButton}
                />
              </Tooltip>
            </Space>
          }
        >
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {sortedSections.length === 0 && (
              <Typography.Text type="secondary">
                {t('pages.prompts.emptySections', { defaultValue: 'No sections yet. Add one using the selector above.' })}
              </Typography.Text>
            )}
            {sortedSections.map((section, index) => {
              const label = section.customLabel || t(`pages.prompts.sectionLabels.${section.type}`, {
                defaultValue: SECTION_LABELS[section.type] || section.type,
              });
              return (
                <Card
                  key={section.id}
                  size="small"
                  bordered
                  style={{ background: 'rgba(15,23,42,0.65)', borderColor: 'rgba(148,163,184,0.2)' }}
                  title={<Typography.Text strong style={{ color: '#fff' }}>{label}</Typography.Text>}
                  extra={
                    <Space size={4}>
                      <Tooltip title={t('pages.prompts.moveUp', { defaultValue: 'Move up' })}>
                        <Button
                          type="text"
                          size="small"
                          className={styles.arrowButton}
                          icon={<ArrowUpOutlined style={{ fontSize: 10 }} />}
                          disabled={index === 0 || !isEditable}
                          onClick={() => handleSectionMove(section.id, -1)}
                        />
                      </Tooltip>
                      <Tooltip title={t('pages.prompts.moveDown', { defaultValue: 'Move down' })}>
                        <Button
                          type="text"
                          size="small"
                          className={styles.arrowButton}
                          icon={<ArrowDownOutlined style={{ fontSize: 10 }} />}
                          disabled={index === sortedSections.length - 1 || !isEditable}
                          onClick={() => handleSectionMove(section.id, 1)}
                        />
                      </Tooltip>
                      <Tooltip title={t('common.remove', { defaultValue: 'Remove' })}>
                        <Button
                          danger
                          type="text"
                          size="small"
                          className={styles.tinyIconButton}
                          icon={<DeleteOutlined style={{ color: '#000' }} />}
                          disabled={!isEditable}
                          onClick={() => handleSectionRemove(section.id)}
                        />
                      </Tooltip>
                    </Space>
                  }
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    {section.items.map((item, idx) => (
                      <div key={`${section.id}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Typography.Text style={{ color: 'rgba(148,163,184,0.9)', minWidth: 28 }}>
                          {idx + 1})
                        </Typography.Text>
                        <TextArea
                          autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
                          rows={autoSizeEnabled && editing ? undefined : 2}
                          value={item}
                          placeholder={t(`pages.prompts.sectionPlaceholders.${section.type}`, {
                            defaultValue: SECTION_PLACEHOLDERS[section.type] || t('pages.prompts.sectionPlaceholders.default', { defaultValue: 'Enter text…' }),
                          })}
                          onChange={(e) => handleSectionItemUpdate(section.id, idx, e.target.value)}
                          disabled={isReadOnly}
                          style={{ lineHeight: '20px', fontSize: 14 }}
                        />
                        <Button
                          danger
                          type="text"
                          size="small"
                          icon={<DeleteOutlined style={{ color: '#000' }} />}
                          disabled={!isEditable}
                          onClick={() => handleSectionItemRemove(section.id, idx)}
                          className={styles.tinyIconButton}
                          style={{ marginTop: 4 }}
                        />
                      </div>
                    ))}
                    <Button
                      type="dashed"
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={() => handleSectionItemAdd(section.id)}
                      disabled={!isEditable}
                      className={styles.smallButtonWithText}
                    >
                      {t('pages.prompts.addItem', { defaultValue: 'Add item' })}
                    </Button>
                  </Space>
                </Card>
              );
            })}
          </Space>
        </SectionContainer>

        <Divider style={{ margin: '16px 0' }} />

        <SectionContainer
          title={t('pages.prompts.sections.userPrompt', { defaultValue: 'User Prompt Sections' })}
          extra={
            <Space>
              <Select
                size="small"
                value={userSectionToAdd}
                onChange={(value: PromptSectionType) => setUserSectionToAdd(value)}
                options={AVAILABLE_SECTION_TYPES.map(({ value, label }) => ({
                  value,
                  label: t(`pages.prompts.sectionLabels.${value}`, { defaultValue: label }),
                }))}
                style={{ minWidth: 180 }}
                disabled={!isEditable}
              />
              {userSectionToAdd === 'custom' && (
                <Input
                  size="small"
                  value={customUserSectionName}
                  onChange={(e) => setCustomUserSectionName(e.target.value)}
                  placeholder="Custom section name"
                  style={{ width: 150 }}
                  disabled={!isEditable}
                />
              )}
              <Tooltip title={t('pages.prompts.addSection', { defaultValue: 'Add section' })}>
                <Button
                  type="primary"
                  size="small"
                  icon={<AppstoreAddOutlined />}
                  onClick={() => handleUserSectionAdd(userSectionToAdd)}
                  disabled={!isEditable}
                  className={styles.smallButton}
                />
              </Tooltip>
              <Tooltip title={t('pages.prompts.removeAllSections', { defaultValue: 'Remove all sections' })}>
                <Button
                  danger
                  type="text"
                  size="small"
                  icon={<DeleteOutlined />}
                  onClick={handleRemoveAllUserSections}
                  disabled={!isEditable || (active.userSections?.length ?? 0) === 0}
                  className={styles.tinyIconButton}
                />
              </Tooltip>
            </Space>
          }
        >
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            {(!active.userSections || active.userSections.length === 0) && (
              <Typography.Text type="secondary">
                {t('pages.prompts.emptySections', { defaultValue: 'No sections yet. Add one using the selector above.' })}
              </Typography.Text>
            )}
            {(active.userSections ?? []).map((section, index) => {
              const label = section.customLabel || t(`pages.prompts.sectionLabels.${section.type}`, {
                defaultValue: SECTION_LABELS[section.type] || section.type,
              });
              return (
                <Card
                  key={section.id}
                  size="small"
                  bordered
                  style={{ background: 'rgba(15,23,42,0.65)', borderColor: 'rgba(148,163,184,0.2)' }}
                  title={<Typography.Text strong style={{ color: '#fff' }}>{label}</Typography.Text>}
                  extra={
                    <Space size={4}>
                      <Tooltip title={t('pages.prompts.moveUp', { defaultValue: 'Move up' })}>
                        <Button
                          type="text"
                          size="small"
                          className={styles.arrowButton}
                          icon={<ArrowUpOutlined style={{ fontSize: 10 }} />}
                          disabled={index === 0 || !isEditable}
                          onClick={() => handleUserSectionMove(section.id, -1)}
                        />
                      </Tooltip>
                      <Tooltip title={t('pages.prompts.moveDown', { defaultValue: 'Move down' })}>
                        <Button
                          type="text"
                          size="small"
                          className={styles.arrowButton}
                          icon={<ArrowDownOutlined style={{ fontSize: 10 }} />}
                          disabled={index === (active.userSections?.length ?? 0) - 1 || !isEditable}
                          onClick={() => handleUserSectionMove(section.id, 1)}
                        />
                      </Tooltip>
                      <Tooltip title={t('common.remove', { defaultValue: 'Remove' })}>
                        <Button
                          danger
                          type="text"
                          size="small"
                          className={styles.tinyIconButton}
                          icon={<DeleteOutlined style={{ color: '#000' }} />}
                          disabled={!isEditable}
                          onClick={() => handleUserSectionRemove(section.id)}
                        />
                      </Tooltip>
                    </Space>
                  }
                >
                  <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    {section.items.map((item, idx) => (
                      <div key={`${section.id}-${idx}`} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                        <Typography.Text style={{ color: 'rgba(148,163,184,0.9)', minWidth: 28 }}>
                          {idx + 1})
                        </Typography.Text>
                        <TextArea
                          autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
                          rows={autoSizeEnabled && editing ? undefined : 2}
                          value={item}
                          placeholder={SECTION_PLACEHOLDERS[section.type] || t('pages.prompts.placeholders.addItem', { defaultValue: 'Add an item' })}
                          disabled={isReadOnly}
                          onChange={(e) => handleUserSectionItemUpdate(section.id, idx, e.target.value)}
                        />
                        <Button
                          danger
                          type="text"
                          size="small"
                          icon={<DeleteOutlined style={{ color: '#000' }} />}
                          disabled={!isEditable}
                          onClick={() => handleUserSectionItemRemove(section.id, idx)}
                          className={styles.tinyIconButton}
                          style={{ marginTop: 4 }}
                        />
                      </div>
                    ))}
                    <Button
                      type="dashed"
                      size="small"
                      icon={<PlusOutlined />}
                      onClick={() => handleUserSectionItemAdd(section.id)}
                      disabled={!isEditable}
                      className={styles.smallButtonWithText}
                    >
                      {t('common.add')}
                    </Button>
                  </Space>
                </Card>
              );
            })}
          </Space>
        </SectionContainer>
      </div>
        </>
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
            <Button size="small" icon={<CopyOutlined />} onClick={copyPreview} className={styles.smallButton} />
          </Tooltip>
        </div>
        <Typography.Text strong style={{ color: '#fff' }}>{t('pages.prompts.preview.title', { defaultValue: 'Preview' })}</Typography.Text>
        <pre style={{ marginTop: 8, whiteSpace: 'pre-wrap', color: 'rgba(255,255,255,0.85)' }}>{previewText}</pre>
      </div>
    </div>
  );
};

export default PromptsDetail;
