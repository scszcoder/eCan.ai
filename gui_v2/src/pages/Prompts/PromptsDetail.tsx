import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { isWebPlatform } from '../../config/platform';
import { Input, Typography, Space, Button, Divider, Tooltip, Select, message, Card, Collapse, Checkbox } from 'antd';
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
  FileMarkdownOutlined,
  CodeOutlined,
  SearchOutlined,
  CloseOutlined,
  CodeSandboxOutlined,
} from '@ant-design/icons';
import type { Prompt, PromptSection, PromptSectionType, PromptFormat } from './types';
import { useTranslation } from 'react-i18next';
import styles from './PromptsDetail.module.css';
import { useToolStore } from '../../stores/toolStore';
import TextareaAutoComplete from './components/TextareaAutoComplete';
import { useUserStore } from '../../stores/userStore';

interface PromptsDetailProps {
  prompt: Prompt | null;
  onChange: (next: Prompt) => void;
  initialEditMode?: boolean;
  onEditModeConsumed?: () => void;
}

const { TextArea } = Input;

const SectionContainer: React.FC<{
  title: string;
  extra?: React.ReactNode;
  children?: React.ReactNode;
}> = ({ title, extra, children }) => (
  <Card
    size="small"
    variant="borderless"
    style={{ background: 'rgba(15,23,42,0.55)', border: '1px solid rgba(148,163,184,0.14)' }}
    styles={{ body: { padding: 16 } }}
    title={<Typography.Text strong style={{ color: '#fff' }}>{title}</Typography.Text>}
    extra={extra}
  >
    {children}
  </Card>
);

// Section labels are now loaded from translations - see getSectionLabel function below

// Section placeholders are now loaded from translations - see getSectionPlaceholder function below

// Available section types - labels will be loaded from translations
const SECTION_TYPE_KEYS: PromptSectionType[] = [
  'role', 'tone', 'background', 'goals', 'guidelines', 'rules',
  'instructions', 'examples', 'variables', 'additional', 'exceptions',
  'extra_attentions', 'tools_to_use', 'custom'
];

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

const PromptsDetail: React.FC<PromptsDetailProps> = ({ prompt, onChange, initialEditMode, onEditModeConsumed }) => {
  const { t } = useTranslation();
  const username = useUserStore((s) => s.username);
  const { tools, fetchTools } = useToolStore();
  const [editing, setEditing] = useState(false);
  const [editFormat, setEditFormat] = useState<PromptFormat>('json');

  // Translation helpers for section labels and placeholders
  const getSectionLabel = useCallback((type: PromptSectionType): string => {
    return t(`pages.prompts.sections.${type}`) || type;
  }, [t]);

  const getSectionPlaceholder = useCallback((type: PromptSectionType): string => {
    return t(`pages.prompts.placeholders.${type}`) || '';
  }, [t]);

  // Build available section types with translated labels
  const availableSectionTypes = useMemo(() => 
    SECTION_TYPE_KEYS.map(type => ({ value: type, label: getSectionLabel(type) })),
    [getSectionLabel]
  );

  // Handle initialEditMode from URL navigation
  useEffect(() => {
    if (initialEditMode && prompt && !prompt.readOnly) {
      setEditing(true);
      onEditModeConsumed?.();
    }
  }, [initialEditMode, prompt, onEditModeConsumed]);
  const [draft, setDraft] = useState<Prompt | null>(prompt);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [autoSizeEnabled, setAutoSizeEnabled] = useState(false);
  const [previewHeight, setPreviewHeight] = useState<number>(() => Math.floor(window.innerHeight * 0.7));
  const [isDraggingPreview, setIsDraggingPreview] = useState(false);
  const undoStackRef = useRef<Prompt[]>([]);
  const redoStackRef = useRef<Prompt[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  // Search state
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchIndex, setSearchIndex] = useState(0);
  const searchInputRef = useRef<any>(null);

  // System variables available for insertion into prompt text
  const SYSTEM_VARIABLES = useMemo(() => [
    { value: 'skills_schema', label: 'skills_schema' },
    { value: 'tools_schema', label: 'tools_schema' },
    { value: 'current_time', label: 'current_time' },
    { value: 'current_time_local', label: 'current_time_local' },
    { value: 'agent_name', label: 'agent_name' },
    { value: 'agent_id', label: 'agent_id' },
    { value: 'chat_id', label: 'chat_id' },
    { value: 'task_id', label: 'task_id' },
    { value: 'human_input', label: 'human_input' },
    { value: 'step_count', label: 'step_count' },
    { value: 'max_steps', label: 'max_steps' },
    { value: 'user_defined', label: t('pages.prompts.userDefined', { defaultValue: '+ User Defined' }) },
  ], [t]);

  // Track last focused textarea + cursor position for variable insertion
  // We store the raw DOM textarea element (from e.target, which is always the real <textarea>)
  const lastTextareaRef = useRef<HTMLTextAreaElement | null>(null);
  const lastCursorPosRef = useRef<number>(0);
  const lastSelectionEndRef = useRef<number>(0);

  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSaveRef = useRef(false);
  const hasPendingChangesRef = useRef(false);
  const latestDraftRef = useRef<Prompt | null>(prompt);
  const editingRef = useRef(editing);
  const promptReadOnlyRef = useRef<boolean>(!!(prompt?.readOnly));

  const clonePrompt = useCallback((value: Prompt): Prompt => JSON.parse(JSON.stringify(value)), []);

  // Handle TAB key to insert tab character instead of moving focus
  const handleTabKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.currentTarget;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const value = target.value;
      // Insert tab character at cursor position
      const newValue = value.substring(0, start) + '\t' + value.substring(end);
      // Update the textarea value via native setter to trigger React's onChange
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
      if (nativeInputValueSetter) {
        nativeInputValueSetter.call(target, newValue);
        // Dispatch input event to trigger React's onChange
        const inputEvent = new Event('input', { bubbles: true });
        target.dispatchEvent(inputEvent);
        // Restore cursor position after the inserted tab
        requestAnimationFrame(() => {
          target.selectionStart = target.selectionEnd = start + 1;
        });
      }
    }
  }, []);

  useEffect(() => {
    if (username) {
      fetchTools(username).catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username]); // Remove fetchTools to avoid infinite loop

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

  const cancelAutosave = useCallback(() => {
    if (autosaveTimerRef.current != null) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
  }, []);

  const commitSave = useCallback((payload: Prompt) => {
    pendingSaveRef.current = true;
    const result = onChange(payload);
    return Promise.resolve(result).finally(() => {
      pendingSaveRef.current = false;
      hasPendingChangesRef.current = false;
    });
  }, [onChange]);

  const flushAutosave = useCallback(() => {
    cancelAutosave();
    if (!editingRef.current || promptReadOnlyRef.current) return;
    if (!hasPendingChangesRef.current) return;
    const currentDraft = latestDraftRef.current;
    if (!currentDraft) return;
    
    // Apply same mode-specific save logic as manual save
    const savePayload = clonePrompt(currentDraft);
    savePayload.format = editFormat;
    
    if (editFormat === 'md') {
      // In markdown mode: save mdContent, clear sections
      savePayload.mdContent = currentDraft.mdContent || '';
      if (savePayload.mdContent.trim()) {
        savePayload.sections = [];
        savePayload.userSections = [];
      }
    } else {
      // In JSON mode: save sections, clear mdContent
      if (savePayload.sections && savePayload.sections.length > 0) {
        savePayload.mdContent = '';
      }
    }
    
    commitSave(savePayload).catch(() => {});
  }, [cancelAutosave, clonePrompt, commitSave, editFormat]);

  const scheduleAutosave = useCallback(() => {
    // Disable autosave for web app, only allow for desktop/Electron
    if (isWebPlatform()) return;
    if (!editingRef.current || promptReadOnlyRef.current) return;
    if (pendingSaveRef.current) return;
    cancelAutosave();
    autosaveTimerRef.current = setTimeout(() => {
      autosaveTimerRef.current = null;
      if (hasPendingChangesRef.current) {
        flushAutosave();
      }
    }, 2000);
  }, [cancelAutosave, flushAutosave]);

  useEffect(() => {
    setDraft(prompt);
    setEditing(false);
    setEditFormat(prompt?.format || (prompt?.mdContent ? 'md' : 'json'));
    hasPendingChangesRef.current = false;
    pendingSaveRef.current = false;
    latestDraftRef.current = prompt;
    cancelAutosave();
  }, [prompt?.id, cancelAutosave]);

  // Cleanup: Only flush autosave when component unmounts (not on every prompt?.id change)
  useEffect(() => {
    return () => {
      // Only flush if we're actually editing and have pending changes
      if (editingRef.current && hasPendingChangesRef.current && !promptReadOnlyRef.current) {
        flushAutosave();
      }
    };
  }, []); // Empty deps - only run on mount/unmount

  useEffect(() => {
    latestDraftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    editingRef.current = editing;
    if (!editing) {
      cancelAutosave();
    }
  }, [editing, cancelAutosave]);

  useEffect(() => {
    promptReadOnlyRef.current = !!(draft?.readOnly);
  }, [draft]);

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

  // Preview drag handlers with optimized performance
  useEffect(() => {
    if (!isDraggingPreview) return;

    let rafId: number | null = null;
    let lastY: number | null = null;

    const onMove = (e: MouseEvent) => {
      lastY = e.clientY;
      e.preventDefault();
      
      if (rafId === null) {
        rafId = requestAnimationFrame(() => {
          if (lastY !== null) {
            const newHeight = window.innerHeight - lastY;
            setPreviewHeight(Math.max(100, Math.min(window.innerHeight - 50, newHeight)));
          }
          rafId = null;
        });
      }
    };

    const onUp = () => {
      setIsDraggingPreview(false);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
        rafId = null;
      }
    };

    window.addEventListener('mousemove', onMove, { passive: false });
    window.addEventListener('mouseup', onUp);

    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
    };
  }, [isDraggingPreview]);

  useEffect(() => {
    undoStackRef.current = [];
    redoStackRef.current = [];
    setCanUndo(false);
    setCanRedo(false);
  }, [editing, prompt?.id]);

  // Ctrl+F opens custom search bar
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 50);
      }
      if (e.key === 'Escape' && searchOpen) {
        setSearchOpen(false);
        setSearchTerm('');
        setSearchIndex(0);
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [searchOpen]);

  // Synchronously build match list from current DOM. Called on every navigation.
  const buildSearchMatches = useCallback((term: string) => {
    if (!term) return [];
    const container = containerRef.current;
    if (!container) return [];
    // Only search within the scroll container (skip search input itself)
    const scrollContainer = container.querySelector('[class*="scrollContainer"]');
    const searchRoot = scrollContainer || container;
    const textareas = searchRoot.querySelectorAll('textarea');
    const lowerTerm = term.toLowerCase();
    const results: { ta: HTMLTextAreaElement; start: number }[] = [];
    textareas.forEach(ta => {
      const val = ta.value.toLowerCase();
      let pos = 0;
      while (true) {
        const idx = val.indexOf(lowerTerm, pos);
        if (idx === -1) break;
        results.push({ ta, start: idx });
        pos = idx + 1;
      }
    });
    return results;
  }, []);

  // Match count for UI display — updated whenever searchTerm or content changes
  const [searchMatchCount, setSearchMatchCount] = useState(0);
  useEffect(() => {
    setSearchMatchCount(buildSearchMatches(searchTerm).length);
  }, [searchTerm, draft, editing, buildSearchMatches]);

  // Navigate to a specific match: focus textarea, select match text, scroll into view
  const navigateToMatch = useCallback((term: string, targetIdx: number) => {
    const matches = buildSearchMatches(term);
    if (matches.length === 0) return;
    const idx = ((targetIdx % matches.length) + matches.length) % matches.length;
    const match = matches[idx];
    if (!match) return;
    const { ta, start } = match;
    const end = start + term.length;

    // 1) Scroll the outer container so the textarea element is visible
    ta.scrollIntoView({ block: 'center', behavior: 'smooth' });

    // 2) Focus and select the matched text
    ta.focus();
    ta.setSelectionRange(start, end);

    // 3) Scroll WITHIN the textarea to make the selected text visible.
    //    We create a temporary mirror div to measure the pixel offset of the match.
    const mirror = document.createElement('div');
    const cs = window.getComputedStyle(ta);
    mirror.style.cssText = [
      `position:absolute`, `visibility:hidden`, `white-space:pre-wrap`, `word-wrap:break-word`,
      `width:${ta.clientWidth}px`,
      `font:${cs.font}`, `font-size:${cs.fontSize}`, `line-height:${cs.lineHeight}`,
      `padding:${cs.padding}`, `border:${cs.border}`, `letter-spacing:${cs.letterSpacing}`,
    ].join(';');
    // Insert text up to the match start, then measure height
    mirror.textContent = ta.value.substring(0, start);
    document.body.appendChild(mirror);
    const matchTop = mirror.scrollHeight;
    document.body.removeChild(mirror);

    // Center the match vertically within the textarea's viewport
    const taVisibleHeight = ta.clientHeight;
    ta.scrollTop = Math.max(0, matchTop - taVisibleHeight / 2);

    // 4) Re-apply selection after scroll (some browsers reset it)
    ta.setSelectionRange(start, end);
  }, [buildSearchMatches]);

  // Track which textarea the user last interacted with, and their cursor position.
  // We use a global listener on the container so we always get the real <textarea> DOM node
  // via e.target (not the Ant Design wrapper).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const saveCursor = (e: Event) => {
      const target = e.target;
      if (!(target instanceof HTMLTextAreaElement)) return;
      if (!container.contains(target)) return;
      lastTextareaRef.current = target;
      // Defer reading selection so browser has settled it
      setTimeout(() => {
        if (lastTextareaRef.current === target) {
          lastCursorPosRef.current = target.selectionStart ?? 0;
          lastSelectionEndRef.current = target.selectionEnd ?? lastCursorPosRef.current;
        }
      }, 0);
    };

    // mouseup = after click/drag selection; keyup = after typing/arrow keys
    container.addEventListener('mouseup', saveCursor, true);
    container.addEventListener('keyup', saveCursor, true);
    return () => {
      container.removeEventListener('mouseup', saveCursor, true);
      container.removeEventListener('keyup', saveCursor, true);
    };
  }, []);

  // Insert variable at the last known cursor position using native value setter
  const handleInsertVariable = useCallback((varName: string) => {
    const tag = `{{${varName}}}`;
    const ta = lastTextareaRef.current;
    if (!ta) {
      navigator.clipboard.writeText(tag).then(() => {
        message.info(t('pages.prompts.varCopied', { defaultValue: `Copied ${tag} to clipboard` }));
      }).catch(() => {});
      return;
    }
    const start = lastCursorPosRef.current;
    const end = lastSelectionEndRef.current;
    const before = ta.value.substring(0, start);
    const after = ta.value.substring(end);
    const newValue = before + tag + after;
    const newPos = start + tag.length;

    // Save scroll positions BEFORE any changes
    const savedTaScrollTop = ta.scrollTop;
    const scrollContainer = ta.closest('[class*="scrollContainer"]') as HTMLElement | null;
    const savedContainerScroll = scrollContainer?.scrollTop ?? 0;

    // Use native setter to trigger React's controlled input onChange
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (nativeSetter) {
      nativeSetter.call(ta, newValue);
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // Refocus and set cursor position after React re-renders
    requestAnimationFrame(() => {
      // Restore outer scroll position first (React re-render may have reset it)
      if (scrollContainer) scrollContainer.scrollTop = savedContainerScroll;

      // Focus without letting browser auto-scroll
      ta.focus({ preventScroll: true });
      ta.setSelectionRange(newPos, newPos);
      lastCursorPosRef.current = newPos;
      lastSelectionEndRef.current = newPos;

      // Restore the textarea's internal scroll to where it was
      ta.scrollTop = savedTaScrollTop;

      // Ensure outer container scroll is still correct after focus
      if (scrollContainer) scrollContainer.scrollTop = savedContainerScroll;
    });
  }, [t]);

  // Avoid early return before hooks to keep hook order stable
  const hasDraft = !!(prompt && draft);
  const active = draft ?? DEFAULT_PROMPT;

  const update = useCallback((mutator: (prev: Prompt) => Prompt) => {
    setDraft((prev) => {
      const current = prev ?? DEFAULT_PROMPT;
      const next = mutator(clonePrompt(current));
      if (editingRef.current && !current.readOnly) {
        pushUndoStack(current);
        hasPendingChangesRef.current = true;
        scheduleAutosave();
      }
      return next;
    });
  }, [clonePrompt, pushUndoStack, scheduleAutosave]);

  const updateFields = (patch: Partial<Prompt>) =>
    update((prev) => ({ ...prev, ...patch }));

  const isEditable = editing && !active.readOnly;
  const isReadOnly = !isEditable;

  const sortedSections = useMemo(() => active.sections ?? [], [active.sections]);

  const parseToolsToUseItem = useCallback((raw: string): string[] => {
    const s = safeString(raw).trim();
    if (!s) return [];
    try {
      const parsed = JSON.parse(s);
      if (Array.isArray(parsed)) {
        return parsed.map((v) => safeString(v)).filter(Boolean);
      }
    } catch {}
    return s.split(',').map((v) => v.trim()).filter(Boolean);
  }, []);

  const formatToolsToUseItem = useCallback((toolIds: string[]): string => {
    try {
      return JSON.stringify(toolIds);
    } catch {
      return toolIds.join(',');
    }
  }, []);

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success(t('pages.prompts.copied', { defaultValue: 'Copied' }));
    } catch {}
  };

  const renderSelectedToolSchemas = (selectedIds: string[]) => {
    const selectedTools = (tools ?? []).filter((tool) => selectedIds.includes(tool.id || tool.name));
    if (!selectedTools.length) {
      return (
        <Typography.Text type="secondary">
          {t('pages.prompts.toolsToUse.noSchemas', { defaultValue: 'No tools selected.' })}
        </Typography.Text>
      );
    }

    return (
      <Collapse
        size="small"
        bordered
        style={{ marginTop: 12, background: 'rgba(15,23,42,0.25)', borderColor: 'rgba(148,163,184,0.2)' }}
        items={selectedTools.map((tool) => {
          const toolId = tool.id || tool.name;
          const schemaObj = {
            id: toolId,
            name: tool.name,
            description: tool.description,
            inputSchema: (tool as any).inputSchema,
            outputSchema: (tool as any).outputSchema,
          };
          const schemaText = (() => {
            try {
              return JSON.stringify(schemaObj, null, 2);
            } catch {
              return String(schemaObj);
            }
          })();

          return {
            key: toolId,
            label: (
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, width: '100%' }}>
                <span style={{ color: 'rgba(255,255,255,0.9)' }}>{tool.name}</span>
                <Button
                  type="text"
                  size="small"
                  icon={<CopyOutlined />}
                  className={styles.smallButton}
                  onClick={(e) => {
                    e.stopPropagation();
                    copyText(schemaText);
                  }}
                />
              </div>
            ),
            children: (
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: 'rgba(255,255,255,0.8)' }}>{schemaText}</pre>
            ),
          };
        })}
      />
    );
  };

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
      cancelAutosave();
      const savePayload = clonePrompt(draft);
      // Persist format choice
      savePayload.format = editFormat;
      
      // Only save content from the active mode
      if (editFormat === 'md') {
        // In markdown mode: save mdContent, clear sections
        savePayload.mdContent = draft.mdContent || '';
        // Clear JSON mode content unless mdContent is empty
        if (savePayload.mdContent.trim()) {
          savePayload.sections = [];
          savePayload.userSections = [];
        }
      } else {
        // In JSON mode: save sections, clear mdContent
        // Clear markdown content unless sections are empty
        if (savePayload.sections && savePayload.sections.length > 0) {
          savePayload.mdContent = '';
        }
      }
      
      latestDraftRef.current = savePayload;
      commitSave(savePayload).catch(() => {});
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
    // If the prompt has rawContent (non-JSON-parsable), show it directly
    if (active.rawContent) {
      return active.rawContent;
    }

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

      const parseToolsToUseItem = (raw: string): string[] => {
        const s = safeString(raw).trim();
        if (!s) return [];
        try {
          const parsed = JSON.parse(s);
          if (Array.isArray(parsed)) {
            return parsed.map((v) => safeString(v)).filter(Boolean);
          }
        } catch {}
        return s.split(',').map((v) => v.trim()).filter(Boolean);
      };

      const renderToolsToUse = (items: string[]) => {
        const seen = new Set<string>();
        const orderedIds: string[] = [];
        items.forEach((raw) => {
          parseToolsToUseItem(raw).forEach((id) => {
            if (seen.has(id)) return;
            seen.add(id);
            orderedIds.push(id);
          });
        });

        orderedIds.forEach((toolId) => {
          const tool = (tools ?? []).find((t) => (t.id || t.name) === toolId);
          if (!tool) return;
          const schemaObj = {
            id: tool.id || tool.name,
            name: tool.name,
            description: tool.description,
            inputSchema: (tool as any).inputSchema,
            outputSchema: (tool as any).outputSchema,
          };
          const schemaLines = JSON.stringify(schemaObj, null, 2).split('\n');
          if (!schemaLines.length) return;
          lines.push(`- ${schemaLines[0]}`);
          schemaLines.slice(1).forEach((l) => lines.push(`  ${l}`));
        });
      };

      sectionsToRender.forEach((section) => {
        if (!section.items.length) return;
        // Use customLabel if available, otherwise use standard label
        const label = section.customLabel || getSectionLabel(section.type);
        // Convert label to valid XML tag name (lowercase, replace spaces/special chars with underscore)
        const tagName = label.toLowerCase().replace(/[^a-z0-9_]/g, '_');
        
        lines.push(`<${tagName}>`);
        if (section.type === 'tools_to_use') {
          renderToolsToUse(section.items);
        } else {
          section.items.forEach((item) => {
            const trimmed = safeString(item).trim();
            if (!trimmed) return;
            lines.push(`- ${trimmed}`);
          });
        }
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

  const handleFormatSwitch = useCallback((newFormat: PromptFormat) => {
    if (newFormat === editFormat) return;

    if (editing && draft) {
      if (newFormat === 'md') {
        // Switching JSON → MD: convert current previewText into mdContent
        const mdText = draft.mdContent || previewText || '';
        pushUndoStack(clonePrompt(draft));
        setDraft((prev) => prev ? { ...prev, format: 'md', mdContent: mdText } : prev);
        hasPendingChangesRef.current = true;
        scheduleAutosave();
      } else {
        // Switching MD → JSON: keep mdContent as-is but switch view to JSON sections
        pushUndoStack(clonePrompt(draft));
        setDraft((prev) => prev ? { ...prev, format: 'json' } : prev);
        hasPendingChangesRef.current = true;
        scheduleAutosave();
      }
    }
    setEditFormat(newFormat);
  }, [editing, draft, editFormat, previewText, pushUndoStack, clonePrompt, scheduleAutosave]);

  // Simple Markdown → HTML renderer for preview panel (MD mode)
  const renderMdPreviewHtml = useMemo(() => {
    if (editFormat !== 'md') return '';
    const src = active.mdContent || '';
    if (!src.trim()) return '<p style="color:rgba(148,163,184,0.6);font-style:italic;">No content yet.</p>';
    // Convert markdown to basic HTML
    let html = src
      // Escape HTML entities
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Headers
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      // Bold and italic
      .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      // Inline code
      .replace(/`([^`]+)`/g, '<code style="background:rgba(148,163,184,0.15);padding:1px 4px;border-radius:3px;font-size:0.9em;">$1</code>')
      // Horizontal rule
      .replace(/^---$/gm, '<hr style="border:none;border-top:1px solid rgba(148,163,184,0.2);margin:12px 0;"/>')
      // Unordered list items
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      // Paragraphs (double newline)
      .replace(/\n\n/g, '</p><p>')
      // Single newlines within paragraphs
      .replace(/\n/g, '<br/>');
    // Wrap consecutive <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>(?:<br\/>)?)+/g, (match) => {
      return '<ul>' + match.replace(/<br\/>/g, '') + '</ul>';
    });
    return '<p>' + html + '</p>';
  }, [editFormat, active.mdContent]);

  const copyPreview = async () => {
    const textToCopy = editFormat === 'md' ? (active.mdContent || '') : previewText;
    try { await navigator.clipboard.writeText(textToCopy); message.success(t('pages.prompts.copied', { defaultValue: 'Copied' })); } catch {}
  };

  return (
    <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0f172a' }}>
      {!hasDraft ? (
        <div style={{ padding: 16, color: 'rgba(255,255,255,0.65)' }}>
          {t('pages.prompts.selectPrompt', { defaultValue: 'Select a prompt to view details' })}
        </div>
      ) : (
        <>
        <TextareaAutoComplete containerRef={containerRef} promptName={active.title || undefined} />
        <div className={styles.header}>
          <Typography.Title level={4} className={styles.headerTitle}>
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
            <Tooltip title={editFormat === 'json'
              ? t('pages.prompts.switchToMd', { defaultValue: 'Switch to Markdown mode' })
              : t('pages.prompts.switchToJson', { defaultValue: 'Switch to JSON mode' })
            }>
              <Button
                size="small"
                icon={editFormat === 'json' ? <FileMarkdownOutlined /> : <CodeOutlined />}
                onClick={() => handleFormatSwitch(editFormat === 'json' ? 'md' : 'json')}
                className={styles.smallButtonWithText}
                style={{
                  borderColor: editFormat === 'md' ? '#3b82f6' : undefined,
                  color: editFormat === 'md' ? '#3b82f6' : undefined,
                }}
              >
                {editFormat === 'json' ? 'MD' : 'JSON'}
              </Button>
            </Tooltip>
            {editing && (
              <Select
                size="small"
                placeholder={t('pages.prompts.insertVar', { defaultValue: '{{ var }}' })}
                value={null}
                options={SYSTEM_VARIABLES}
                onChange={(value: string) => { if (value) handleInsertVariable(value); }}
                style={{ minWidth: 120 }}
                popupMatchSelectWidth={false}
                suffixIcon={<CodeSandboxOutlined style={{ fontSize: 12 }} />}
              />
            )}
            {editing && (
              <Button
                size="small"
                icon={<UndoOutlined />}
                onClick={() => {
                  setDraft(clonePrompt(prompt!));
                  setEditing(false);
                  setEditFormat(prompt?.format || 'json');
                  cancelAutosave();
                }}
                className={styles.smallButtonWithText}
              >
                {t('common.cancel')}
              </Button>
            )}
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
      {/* Search bar */}
      {searchOpen && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 12px',
          background: 'rgba(30, 41, 59, 0.95)',
          borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
          position: 'sticky', top: 0, zIndex: 60,
        }}>
          <SearchOutlined style={{ color: '#94a3b8', fontSize: 14 }} />
          <Input
            ref={searchInputRef}
            size="small"
            placeholder={t('common.search', { defaultValue: 'Search...' })}
            value={searchTerm}
            onChange={(e) => {
              setSearchTerm(e.target.value);
              setSearchIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                // Navigate to current match, then advance index for next press
                navigateToMatch(searchTerm, searchIndex);
                setSearchIndex(prev => prev + (e.shiftKey ? -1 : 1));
              }
              if (e.key === 'Escape') { setSearchOpen(false); setSearchTerm(''); setSearchIndex(0); }
            }}
            style={{ width: 220, background: 'rgba(15,23,42,0.7)', borderColor: 'rgba(148,163,184,0.3)', color: '#e2e8f0' }}
            allowClear
          />
          {searchTerm && (
            <Typography.Text style={{ color: '#94a3b8', fontSize: 12, whiteSpace: 'nowrap', minWidth: 36, textAlign: 'center' }}>
              {searchMatchCount > 0
                ? `${(((searchIndex % searchMatchCount) + searchMatchCount) % searchMatchCount) + 1}/${searchMatchCount}`
                : '0/0'}
            </Typography.Text>
          )}
          <Button type="text" size="small" icon={<ArrowUpOutlined style={{ fontSize: 12 }} />}
            onClick={() => { const i = searchIndex - 1; navigateToMatch(searchTerm, i); setSearchIndex(i); }}
            disabled={searchMatchCount === 0}
            style={{ color: '#94a3b8', height: 24, width: 24, padding: 0, minWidth: 24 }} />
          <Button type="text" size="small" icon={<ArrowDownOutlined style={{ fontSize: 12 }} />}
            onClick={() => { const i = searchIndex + 1; navigateToMatch(searchTerm, i); setSearchIndex(i); }}
            disabled={searchMatchCount === 0}
            style={{ color: '#94a3b8', height: 24, width: 24, padding: 0, minWidth: 24 }} />
          <Button type="text" size="small" icon={<CloseOutlined style={{ fontSize: 12 }} />}
            onClick={() => { setSearchOpen(false); setSearchTerm(''); setSearchIndex(0); }}
            style={{ color: '#94a3b8', height: 24, width: 24, padding: 0, minWidth: 24 }} />
        </div>
      )}
      <div className={styles.scrollContainer} style={{ flex: 1, minHeight: 0, paddingBottom: '60px' }}>
        {/* Raw content display for non-JSON-parsable prompts */}
        {active.rawContent ? (
          <SectionContainer title={t('pages.prompts.rawContent', { defaultValue: 'Prompt Content (plain text)' })}>
            <pre style={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              color: 'rgba(255,255,255,0.85)',
              fontSize: 13,
              lineHeight: 1.6,
              margin: 0,
              padding: 12,
              background: 'rgba(0,0,0,0.2)',
              borderRadius: 6,
              maxHeight: '70vh',
              overflow: 'auto',
            }}>
              {active.rawContent}
            </pre>
          </SectionContainer>
        ) : (
        <>
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
            onKeyDown={handleTabKeyDown}
            placeholder={t('pages.prompts.placeholders.title', { defaultValue: 'Enter prompt title...' })}
            disabled={isReadOnly}
            className={styles.titleInput}
          />
          <Divider className={styles.divider} />
          <TextArea
            key={`topic-ta-${autoSizeEnabled ? 'auto' : 'fixed'}`}
            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 4 } : undefined}
            rows={autoSizeEnabled && editing ? undefined : 2}
            value={safeString(active.topic)}
            onChange={(e) => updateFields({ topic: e.target.value })}
            onKeyDown={handleTabKeyDown}
            placeholder={t('pages.prompts.placeholders.topic', { defaultValue: 'Enter topic or short description...' })}
            disabled={isReadOnly}
            className={styles.topicInput}
          />
        </SectionContainer>

        <Divider style={{ margin: '16px 0' }} />

        {/* MD mode: show markdown source editor */}
        {editFormat === 'md' && editing ? (
          <SectionContainer
            title={t('pages.prompts.mdEditor', { defaultValue: 'Markdown Source' })}
            extra={
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                <FileMarkdownOutlined style={{ marginRight: 4 }} />
                {t('pages.prompts.mdEditorHint', { defaultValue: 'Edit raw markdown source' })}
              </Typography.Text>
            }
          >
            <TextArea
              value={active.mdContent || ''}
              onChange={(e) => update((prev) => ({ ...prev, mdContent: e.target.value }))}
              onKeyDown={handleTabKeyDown}
              placeholder={t('pages.prompts.placeholders.mdContent', { defaultValue: 'Write your prompt in Markdown...\n\n# Role\nYou are a helpful assistant.\n\n# Instructions\n- Step 1: ...\n- Step 2: ...' })}
              autoSize={{ minRows: 15, maxRows: 50 }}
              className={styles.mdEditor}
            />
          </SectionContainer>
        ) : editFormat === 'md' && !editing ? (
          <SectionContainer
            title={t('pages.prompts.mdEditor', { defaultValue: 'Markdown Source' })}
          >
            <pre className={styles.mdEditorReadonly}>
              {active.mdContent || t('pages.prompts.noMdContent', { defaultValue: 'No markdown content.' })}
            </pre>
          </SectionContainer>
        ) : (
        <>
        <SectionContainer
          title={t('pages.prompts.sections.systemPrompt', { defaultValue: 'System Prompt Sections' })}
          extra={
            <Space>
              <Select
                size="small"
                value={sectionToAdd}
                onChange={(value: PromptSectionType) => setSectionToAdd(value)}
                options={availableSectionTypes}
                style={{ minWidth: 180 }}
                disabled={!isEditable}
              />
              {sectionToAdd === 'custom' && (
                <Input
                  size="small"
                  value={customSectionName}
                  onChange={(e) => setCustomSectionName(e.target.value)}
                  placeholder={t('pages.prompts.placeholders.customSectionName', { defaultValue: 'Custom section name' })}
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
                  type="text"
                  size="small"
                  icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
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
              <div className={styles.emptyState}>
                {t('pages.prompts.emptySections', { defaultValue: 'No sections yet. Add one using the selector above.' })}
              </div>
            )}
            {sortedSections.map((section, index) => {
              const label = section.customLabel || getSectionLabel(section.type);
              return (
                <Card
                  key={section.id}
                  size="small"
                  variant="outlined"
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
                          type="text"
                          size="small"
                          className={styles.tinyIconButton}
                          icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                          disabled={!isEditable}
                          onClick={() => handleSectionRemove(section.id)}
                        />
                      </Tooltip>
                    </Space>
                  }
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%' }}>
                    {section.type === 'tools_to_use' ? (
                      <Collapse
                        size="small"
                        bordered
                        style={{ background: 'rgba(15,23,42,0.35)', borderColor: 'rgba(148,163,184,0.2)' }}
                        items={section.items.map((item, idx) => {
                          const selectedIds = parseToolsToUseItem(item);
                          const selectedTools = (tools ?? []).filter((t) => selectedIds.includes(t.id || t.name));
                          const header = selectedTools.length
                            ? `(${selectedTools.length}) ${selectedTools.map((t) => t.name).join(', ')}`
                            : t('pages.prompts.toolsToUse.emptyRow', { defaultValue: 'Select tools…' });

                          return {
                            key: `${section.id}-${idx}`,
                            label: (
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%' }}>
                                <span>{idx + 1}) {header}</span>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                                  disabled={!isEditable}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleSectionItemRemove(section.id, idx);
                                  }}
                                  className={styles.tinyIconButton}
                                />
                              </div>
                            ),
                            children: (
                              <div style={{ paddingTop: 8 }}>
                                {!isEditable && (
                                  <Typography.Text type="secondary">
                                    {t('pages.prompts.toolsToUse.editHint', { defaultValue: 'Click Edit to select tools.' })}
                                  </Typography.Text>
                                )}
                                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                  {(tools ?? []).map((tool) => {
                                    const toolId = tool.id || tool.name;
                                    const isChecked = selectedIds.includes(toolId);
                                    return (
                                      <Checkbox
                                        key={toolId}
                                        checked={isChecked}
                                        disabled={!isEditable}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          const newIds = e.target.checked
                                            ? [...selectedIds, toolId]
                                            : selectedIds.filter((id) => id !== toolId);
                                          handleSectionItemUpdate(section.id, idx, formatToolsToUseItem(newIds));
                                        }}
                                        style={{ color: 'rgba(255,255,255,0.85)' }}
                                      >
                                        {tool.name}
                                        {tool.description ? (
                                          <span style={{ marginLeft: 8, color: 'rgba(148,163,184,0.8)' }}>{tool.description}</span>
                                        ) : null}
                                      </Checkbox>
                                    );
                                  })}
                                </Space>
                                {renderSelectedToolSchemas(selectedIds)}
                              </div>
                            ),
                          };
                        })}
                      />
                    ) : (
                      section.items.map((item, idx) => (
                        <div key={`${section.id}-${idx}`} style={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
                          <Typography.Text style={{ 
                            color: '#94a3b8', 
                            minWidth: 32,
                            fontSize: '13px',
                            fontWeight: 500,
                            paddingTop: '6px',
                            lineHeight: '1.5'
                          }}>
                            {idx + 1})
                          </Typography.Text>
                          <TextArea
                            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
                            rows={autoSizeEnabled && editing ? undefined : 2}
                            value={item}
                            placeholder={getSectionPlaceholder(section.type) || t('pages.prompts.placeholders.addItem', { defaultValue: 'Enter text…' })}
                            onChange={(e) => handleSectionItemUpdate(section.id, idx, e.target.value)}
                            onKeyDown={handleTabKeyDown}
                            disabled={isReadOnly}
                            className={styles.itemTextarea}
                          />
                          <Button
                            type="text"
                            size="small"
                            icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                            disabled={!isEditable}
                            onClick={() => handleSectionItemRemove(section.id, idx)}
                            className={styles.tinyIconButton}
                            style={{ marginTop: 8 }}
                          />
                        </div>
                      ))
                    )}
                    <div style={{ marginTop: '12px' }}>
                      <Button
                        type="dashed"
                        size="small"
                        icon={<PlusOutlined />}
                        onClick={() => handleSectionItemAdd(section.id)}
                        disabled={!isEditable}
                        block
                        style={{
                          borderColor: 'rgba(148, 163, 184, 0.3)',
                          color: '#94a3b8',
                          fontSize: '13px',
                          textAlign: 'left'
                        }}
                      >
                        {t('pages.prompts.addItem', { defaultValue: 'Add item' })}
                      </Button>
                    </div>
                  </div>
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
                options={availableSectionTypes}
                style={{ minWidth: 180 }}
                disabled={!isEditable}
              />
              {userSectionToAdd === 'custom' && (
                <Input
                  size="small"
                  value={customUserSectionName}
                  onChange={(e) => setCustomUserSectionName(e.target.value)}
                  placeholder={t('pages.prompts.placeholders.customSectionName', { defaultValue: 'Custom section name' })}
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
              <Tooltip title={t('pages.prompts.removeAllSections', { defaultValue: 'Remove all' })}>
                <Button
                  type="text"
                  size="small"
                  icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
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
              const label = section.customLabel || getSectionLabel(section.type);
              return (
                <Card
                  key={section.id}
                  size="small"
                  variant="outlined"
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
                          type="text"
                          size="small"
                          className={styles.tinyIconButton}
                          icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                          disabled={!isEditable}
                          onClick={() => handleUserSectionRemove(section.id)}
                        />
                      </Tooltip>
                    </Space>
                  }
                >
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', width: '100%' }}>
                    {section.type === 'tools_to_use' ? (
                      <Collapse
                        size="small"
                        bordered
                        style={{ background: 'rgba(15,23,42,0.35)', borderColor: 'rgba(148,163,184,0.2)' }}
                        items={section.items.map((item, idx) => {
                          const selectedIds = parseToolsToUseItem(item);
                          const selectedTools = (tools ?? []).filter((t) => selectedIds.includes(t.id || t.name));
                          const header = selectedTools.length
                            ? `(${selectedTools.length}) ${selectedTools.map((t) => t.name).join(', ')}`
                            : t('pages.prompts.toolsToUse.emptyRow', { defaultValue: 'Select tools…' });

                          return {
                            key: `${section.id}-${idx}`,
                            label: (
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, width: '100%' }}>
                                <span>{idx + 1}) {header}</span>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                                  disabled={!isEditable}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleUserSectionItemRemove(section.id, idx);
                                  }}
                                  className={styles.tinyIconButton}
                                />
                              </div>
                            ),
                            children: (
                              <div style={{ paddingTop: 8 }}>
                                {!isEditable && (
                                  <Typography.Text type="secondary">
                                    {t('pages.prompts.toolsToUse.editHint', { defaultValue: 'Click Edit to select tools.' })}
                                  </Typography.Text>
                                )}
                                <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                  {(tools ?? []).map((tool) => {
                                    const toolId = tool.id || tool.name;
                                    const isChecked = selectedIds.includes(toolId);
                                    return (
                                      <Checkbox
                                        key={toolId}
                                        checked={isChecked}
                                        disabled={!isEditable}
                                        onChange={(e) => {
                                          e.stopPropagation();
                                          const newIds = e.target.checked
                                            ? [...selectedIds, toolId]
                                            : selectedIds.filter((id) => id !== toolId);
                                          handleUserSectionItemUpdate(section.id, idx, formatToolsToUseItem(newIds));
                                        }}
                                        style={{ color: 'rgba(255,255,255,0.85)' }}
                                      >
                                        {tool.name}
                                        {tool.description ? (
                                          <span style={{ marginLeft: 8, color: 'rgba(148,163,184,0.8)' }}>{tool.description}</span>
                                        ) : null}
                                      </Checkbox>
                                    );
                                  })}
                                </Space>
                                {renderSelectedToolSchemas(selectedIds)}
                              </div>
                            ),
                          };
                        })}
                      />
                    ) : (
                      section.items.map((item, idx) => (
                        <div key={`${section.id}-${idx}`} style={{ display: 'flex', gap: 2, alignItems: 'flex-start' }}>
                          <Typography.Text style={{ 
                            color: '#94a3b8', 
                            minWidth: 32,
                            fontSize: '13px',
                            fontWeight: 500,
                            paddingTop: '6px',
                            lineHeight: '1.5'
                          }}>
                            {idx + 1})
                          </Typography.Text>
                          <TextArea
                            autoSize={autoSizeEnabled && editing ? { minRows: 2, maxRows: 6 } : undefined}
                            rows={autoSizeEnabled && editing ? undefined : 2}
                            value={item}
                            placeholder={getSectionPlaceholder(section.type) || t('pages.prompts.placeholders.addItem', { defaultValue: 'Add an item' })}
                            disabled={isReadOnly}
                            onChange={(e) => handleUserSectionItemUpdate(section.id, idx, e.target.value)}
                            onKeyDown={handleTabKeyDown}
                            className={styles.itemTextarea}
                          />
                          <Button
                            type="text"
                            size="small"
                            icon={<DeleteOutlined style={{ color: '#ef4444', fontSize: '14px' }} />}
                            disabled={!isEditable}
                            onClick={() => handleUserSectionItemRemove(section.id, idx)}
                            className={styles.tinyIconButton}
                            style={{ marginTop: 8 }}
                          />
                        </div>
                      ))
                    )}
                    <div style={{ marginTop: '12px' }}>
                      <Button
                        type="dashed"
                        size="small"
                        icon={<PlusOutlined />}
                        onClick={() => handleUserSectionItemAdd(section.id)}
                        disabled={!isEditable}
                        block
                        style={{
                          borderColor: 'rgba(148, 163, 184, 0.3)',
                          color: '#94a3b8',
                          fontSize: '13px',
                          textAlign: 'left'
                        }}
                      >
                        {t('common.add')}
                      </Button>
                    </div>
                  </div>
                </Card>
              );
            })}
          </Space>
        </SectionContainer>
        </>
        )}
        </>
        )}
      </div>
        </>
      )}

      {/* Preview Collapse Panel - Sticky at bottom */}
      <div style={{ 
        position: 'sticky',
        bottom: 0,
        borderTop: '1px solid rgba(148, 163, 184, 0.2)',
        background: 'rgba(15, 23, 42, 0.95)',
        backdropFilter: 'blur(10px)',
        zIndex: 50
      }}>
        {/* Drag handle - above the title */}
        <div
          onMouseDown={() => setIsDraggingPreview(true)}
          style={{
            height: 12,
            cursor: 'row-resize',
            background: isDraggingPreview 
              ? 'linear-gradient(90deg, rgba(59,130,246,0.3), rgba(59,130,246,0.6), rgba(59,130,246,0.3))'
              : 'linear-gradient(90deg, rgba(148,163,184,0.2), rgba(148,163,184,0.4), rgba(148,163,184,0.2))',
            borderTop: '1px solid rgba(148,163,184,0.3)',
            borderBottom: '1px solid rgba(148,163,184,0.1)',
            transition: 'background 0.2s ease',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
          title={t('pages.prompts.dragToResize', { defaultValue: 'Drag to resize' })}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'linear-gradient(90deg, rgba(148,163,184,0.3), rgba(148,163,184,0.6), rgba(148,163,184,0.3))';
          }}
          onMouseLeave={(e) => {
            if (!isDraggingPreview) {
              e.currentTarget.style.background = 'linear-gradient(90deg, rgba(148,163,184,0.2), rgba(148,163,184,0.4), rgba(148,163,184,0.2))';
            }
          }}
        >
          <div style={{
            width: '40px',
            height: '3px',
            background: 'rgba(148,163,184,0.5)',
            borderRadius: '2px'
          }} />
        </div>
        <div style={{ position: 'relative' }}>
          <Collapse
            ghost
            expandIconPosition="end"
            style={{
              background: 'transparent',
              border: 'none'
            }}
            expandIcon={({ isActive }) => (
              <div style={{ transform: isActive ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>
                ▼
              </div>
            )}
            items={[{
              key: 'preview',
              label: (
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  justifyContent: 'center',
                  padding: '8px 0',
                  width: '100%'
                }}>
                  <Typography.Text strong style={{ color: '#e2e8f0', fontSize: '14px' }}>
                    {t('pages.prompts.preview.title', { defaultValue: 'Preview' })}
                  </Typography.Text>
                </div>
              ),
              children: (
                <div style={{ 
                  maxHeight: '400px',
                  height: previewHeight,
                  overflow: 'auto',
                  padding: '16px',
                  position: 'absolute',
                  bottom: '100%',
                  left: 0,
                  right: 0,
                  background: 'rgba(15, 23, 42, 0.98)',
                  borderTop: '1px solid rgba(148, 163, 184, 0.2)',
                  boxShadow: '0 -4px 12px rgba(0, 0, 0, 0.3)'
                }}>
                  {editFormat === 'md' ? (
                    <div className={styles.previewContent} style={{ position: 'relative' }}>
                      <Tooltip title={t('pages.prompts.copyPreview', { defaultValue: 'Copy preview' })}>
                        <Button 
                          size="small" 
                          icon={<CopyOutlined />} 
                          onClick={copyPreview} 
                          className={styles.smallButton}
                          style={{
                            position: 'absolute',
                            top: '8px',
                            right: '8px',
                            zIndex: 10
                          }}
                        />
                      </Tooltip>
                      <div
                        className={styles.mdPreview}
                        dangerouslySetInnerHTML={{ __html: renderMdPreviewHtml }}
                      />
                    </div>
                  ) : (
                    <pre className={styles.previewContent} style={{ position: 'relative' }}>
                      <Tooltip title={t('pages.prompts.copyPreview', { defaultValue: 'Copy preview' })}>
                        <Button 
                          size="small" 
                          icon={<CopyOutlined />} 
                          onClick={copyPreview} 
                          className={styles.smallButton}
                          style={{
                            position: 'absolute',
                            top: '8px',
                            right: '8px',
                            zIndex: 10
                          }}
                        />
                      </Tooltip>
                      {previewText}
                    </pre>
                  )}
                </div>
              )
            }]}
          />
        </div>
      </div>
    </div>
  );
};

export default PromptsDetail;
