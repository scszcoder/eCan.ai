import React, { useEffect, useMemo, useState } from 'react';
import { AutoComplete, Tooltip } from 'antd';
import { AppstoreOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

/**
 * Lightweight per-tab workspace (tenant) picker for LightRAG.
 *
 * - Persists the chosen workspace name in sessionStorage under `storageKey`.
 * - Empty / missing value means "use server default workspace" (backward-compat).
 * - Populates suggestions from `lightrag.getWorkspaces` but also allows free
 *   text so users can start a new workspace on the fly (the first
 *   ingest/query using a brand-new name will make the server create it).
 *
 * Recommended category names for `eCan.ai`:
 *   - customer_service
 *   - product_details
 *   - general_faq
 *
 * (Sales / transactional data should NOT go through RAG — use a SQL tool.)
 */
export interface WorkspacePickerProps {
  /** Current workspace value (controlled). Empty string = server default. */
  value: string;
  /** Called when the user picks / types a different workspace. */
  onChange: (workspace: string) => void;
  /** Optional sessionStorage key for self-persistence. Omit when the
   *  picker is wired to the shared `useWorkspace()` hook (which handles
   *  persistence and cross-component sync on its own). */
  storageKey?: string;
  /** Label placement hint; caller decides layout. Default false = inline. */
  block?: boolean;
  /** Optional placeholder override. */
  placeholder?: string;
  /** Optional title/label to show above the picker. */
  label?: string;
  /** Optional callback fired once on mount with the restored value. */
  onRestored?: (workspace: string) => void;
}

interface WorkspaceInfo {
  name: string;
  is_valid?: boolean;
}

const DEFAULT_SUGGESTIONS = [
  'customer_service',
  'product_details',
  'general_faq',
];

const WorkspacePicker: React.FC<WorkspacePickerProps> = ({
  value,
  onChange,
  storageKey,
  placeholder,
  label,
  block,
  onRestored,
}) => {
  const [options, setOptions] = useState<{ value: string; label: React.ReactNode }[]>([]);

  // Restore from sessionStorage on first mount, only if the current value
  // is empty AND a storageKey was supplied. When the picker is driven by
  // useWorkspace() the parent already restored the value, so we skip both
  // the read and the write.
  useEffect(() => {
    if (!storageKey) return;
    try {
      const saved = sessionStorage.getItem(storageKey) || '';
      if (saved && !value) {
        onChange(saved);
        onRestored && onRestored(saved);
      }
    } catch {
      /* ignore */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Persist on every change (only when a storageKey is supplied)
  useEffect(() => {
    if (!storageKey) return;
    try {
      sessionStorage.setItem(storageKey, value || '');
    } catch {
      /* ignore */
    }
  }, [value, storageKey]);

  // Fetch existing workspaces from server for suggestions
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const resp = await get_ipc_api().lightragApi.getWorkspaces<{
          workspaces: WorkspaceInfo[];
          current?: string;
        }>();
        const existing = (resp.success && resp.data?.workspaces) || [];
        const names = new Set<string>();
        existing.forEach((w) => {
          if (w && typeof w.name === 'string' && w.name.trim()) names.add(w.name.trim());
        });
        DEFAULT_SUGGESTIONS.forEach((n) => names.add(n));
        const opts = Array.from(names).sort().map((n) => ({
          value: n,
          label: n,
        }));
        if (mounted) setOptions(opts);
      } catch {
        if (mounted) {
          setOptions(
            DEFAULT_SUGGESTIONS.map((n) => ({ value: n, label: n })),
          );
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const filteredOptions = useMemo(() => {
    const q = (value || '');
    if (!q) return options;
    const qLower = q.toLowerCase();
    return options.filter((o) => o.value.toLowerCase().includes(qLower) || o.value.includes(q));
  }, [options, value]);

  const { t } = useTranslation();

  return (
    <div style={{ display: block ? 'block' : 'inline-flex', alignItems: 'center', gap: 8 }}>
      {label ? (
        <span style={{ fontSize: 12, opacity: 0.75, whiteSpace: 'nowrap' }}>
          <AppstoreOutlined style={{ marginRight: 4 }} />
          {label}
          <Tooltip title={t('pages.knowledge.lightrag.workspacePicker.tooltip')}>
            <InfoCircleOutlined style={{ marginLeft: 4, opacity: 0.55 }} />
          </Tooltip>
        </span>
      ) : null}
      <AutoComplete
        value={value}
        onChange={(v) => {
          onChange((v || '').trim());
        }}
        options={filteredOptions}
        placeholder={placeholder || t('pages.knowledge.lightrag.workspacePicker.placeholder')}
        allowClear
        size="small"
        style={{ width: 220 }}
        getPopupContainer={() => document.body}
      />
    </div>
  );
};

export default WorkspacePicker;
