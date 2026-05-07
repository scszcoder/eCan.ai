import { useCallback, useEffect, useState } from 'react';

/**
 * Single source of truth for the LightRAG workspace (tenant) selected in
 * the Knowledge page. Backed by ``sessionStorage`` so it survives tab
 * switches but doesn't leak between browser sessions, and broadcast over
 * a ``CustomEvent`` so the header picker, RetrievalTab and DocumentsTab
 * stay in sync without a global state library.
 *
 * Empty string === "use the LightRAG server's default workspace" (the
 * pre-multi-tenant behavior). All callers should treat empty as "no
 * override" and omit the ``workspace`` field from outbound IPC payloads.
 */
const STORAGE_KEY = 'lightrag-ported:workspace:active';
const EVENT_NAME = 'lightrag-workspace-changed';

export function getStoredWorkspace(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function setStoredWorkspace(workspace: string): void {
  const next = (workspace || '').trim();
  try {
    sessionStorage.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore quota errors */
  }
  try {
    window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: next }));
  } catch {
    /* ignore (non-browser env) */
  }
}

/**
 * React hook returning ``[workspace, setWorkspace]``. The setter persists
 * to sessionStorage and broadcasts the change so other useWorkspace()
 * consumers in the same window stay in sync.
 */
export function useWorkspace(): [string, (workspace: string) => void] {
  const [workspace, setWorkspaceState] = useState<string>(() => getStoredWorkspace());

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      setWorkspaceState(typeof detail === 'string' ? detail : '');
    };
    window.addEventListener(EVENT_NAME, handler as EventListener);
    return () => window.removeEventListener(EVENT_NAME, handler as EventListener);
  }, []);

  const setWorkspace = useCallback((next: string) => {
    const trimmed = (next || '').trim();
    setStoredWorkspace(trimmed);
    // Local state will also be updated by the event listener, but set it
    // synchronously so the caller's render reflects the new value
    // immediately without waiting for the event loop.
    setWorkspaceState(trimmed);
  }, []);

  return [workspace, setWorkspace];
}
