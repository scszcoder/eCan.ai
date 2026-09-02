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
  /** Optional placeholder override. */
  placeholder?: string;
  /** Optional title/label override shown next to the picker. */
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

  // Localised label/tooltip shown next to the picker. The tooltip doubles
  // as the "what is a workspace?" explainer that used to be missing — see
  // the user feedback about workspace context being invisible.
  const workspaceLabel = label || t('pages.knowledge.lightrag.workspacePicker.label');
  const workspaceTooltip = t('pages.knowledge.lightrag.workspacePicker.tooltip');

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      flexShrink: 0,
    }}>
      <AppstoreOutlined style={{ color: token.colorPrimary, fontSize: 12 }} />
      <span style={{ fontSize: 12, color: token.colorTextSecondary, fontWeight: 500, whiteSpace: 'nowrap' }}>
        {workspaceLabel}
      </span>
      <Tooltip title={workspaceTooltip} placement="bottom">
        <InfoCircleOutlined style={{ color: token.colorTextTertiary, fontSize: 12, cursor: 'help' }} />
      </Tooltip>
      <Select
        value={value || undefined}
        onChange={(v) => onChange((v || '').trim())}
        // options only carry value; visual rendering is delegated to
        // optionRender so the closed picker shows a plain "test3" label
        // (standard antd Select look) while the dropdown shows the
        // folder-icon + check-mark affordance.
        options={workspaceNames.map((name) => ({ value: name, label: name }))}
        optionRender={(option) => (
          <span style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <FolderOutlined
              style={{
                color: option.value === value ? token.colorPrimary : token.colorTextTertiary,
              }}
            />
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {option.label}
            </span>
            {option.value === value && (
              <CheckOutlined style={{ color: token.colorPrimary, fontSize: 12 }} />
            )}
          </span>
        )}
        placeholder={placeholder || t('pages.knowledge.lightrag.workspacePicker.placeholder')}
        loading={loading}
        showSearch
        optionFilterProp="value"
        size="middle"
        style={{ width: 160, minWidth: 0 }}
        popupMatchSelectWidth={240}
        getPopupContainer={() => document.body}
      />
    </div>
  );
};

export default WorkspacePicker;
