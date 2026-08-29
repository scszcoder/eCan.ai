import React, { useEffect, useState } from 'react';
import { Select, Tooltip, theme } from 'antd';
import { AppstoreOutlined, CheckOutlined, FolderOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';

/**
 * Lightweight per-tab workspace (tenant) picker for LightRAG.
 *
 * - Persists the chosen workspace name in sessionStorage under `storageKey`.
 * - Empty / missing value means "use server default workspace" (backward-compat).
 * - Populates existing workspaces from `lightrag.getWorkspaces`. Creation is
 *   intentionally kept in Settings so a typo cannot silently select a new
 *   empty tenant from the global header.
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

const WorkspacePicker: React.FC<WorkspacePickerProps> = ({
  value,
  onChange,
  storageKey,
  placeholder,
  label,
  block,
  onRestored,
}) => {
  const [workspaceNames, setWorkspaceNames] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const { token } = theme.useToken();

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
      setLoading(true);
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
        const serverCurrent = (resp.success && resp.data?.current || '').trim();
        if (serverCurrent) names.add(serverCurrent);
        const opts = Array.from(names).sort();
        if (mounted) {
          setWorkspaceNames(opts);
          // The shared workspace state starts empty in a fresh browser
          // session. Show the server's configured workspace instead of the
          // misleading "server default" placeholder.
          if (!value && serverCurrent) onChange(serverCurrent);
        }
      } catch {
        if (mounted) setWorkspaceNames([]);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const { t } = useTranslation();

  return (
    <div style={{
      display: block ? 'flex' : 'inline-flex',
      width: block ? '100%' : 'auto',
      alignItems: 'center',
      gap: 10,
    }}>
      {label ? (
        <span style={{ display: 'inline-flex', alignItems: 'center', fontSize: 12, color: token.colorTextSecondary, whiteSpace: 'nowrap' }}>
          <AppstoreOutlined style={{ marginRight: 5, color: token.colorPrimary }} />
          <span style={{ fontWeight: 500 }}>{label}</span>
          <Tooltip title={t('pages.knowledge.lightrag.workspacePicker.tooltip')}>
            <InfoCircleOutlined style={{ marginLeft: 5, color: token.colorTextTertiary }} />
          </Tooltip>
        </span>
      ) : null}
      <Select
        value={value || undefined}
        onChange={(v) => onChange((v || '').trim())}
        options={workspaceNames.map((name) => ({
          value: name,
          label: (
            <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
              <FolderOutlined style={{ color: name === value ? token.colorPrimary : token.colorTextTertiary }} />
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
              {name === value && <CheckOutlined style={{ color: token.colorPrimary, fontSize: 12 }} />}
            </span>
          ),
        }))}
        placeholder={placeholder || t('pages.knowledge.lightrag.workspacePicker.placeholder')}
        loading={loading}
        showSearch
        optionFilterProp="value"
        size="middle"
        style={{ width: block ? '100%' : 210, minWidth: 0 }}
        popupMatchSelectWidth={240}
        getPopupContainer={() => document.body}
      />
    </div>
  );
};

export default WorkspacePicker;
