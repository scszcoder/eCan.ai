/**
 * Storage for the LightRAG workspace (knowledge base) selected in the
 * Knowledge page. Lives in the IPC service layer so API calls that the page
 * doesn't parameterise explicitly (graph, history, cache) can still be scoped
 * to the selected workspace. Empty string === the server's default workspace.
 */
export const WORKSPACE_STORAGE_KEY = 'lightrag-ported:workspace:active';
export const WORKSPACE_EVENT_NAME = 'lightrag-workspace-changed';

export function getStoredWorkspace(): string {
  try {
    return sessionStorage.getItem(WORKSPACE_STORAGE_KEY) || '';
  } catch {
    return '';
  }
}

export function setStoredWorkspace(workspace: string): void {
  const next = (workspace || '').trim();
  try {
    sessionStorage.setItem(WORKSPACE_STORAGE_KEY, next);
  } catch {
    /* ignore quota errors */
  }
  try {
    window.dispatchEvent(new CustomEvent(WORKSPACE_EVENT_NAME, { detail: next }));
  } catch {
    /* ignore (non-browser env) */
  }
}

/** Add the selected workspace to an IPC payload unless the caller set one. */
export function withWorkspace<T extends Record<string, any>>(payload?: T): T & { workspace?: string } {
  const body = { ...(payload || {}) } as T & { workspace?: string };
  if (!body.workspace) {
    const ws = getStoredWorkspace();
    if (ws) body.workspace = ws;
  }
  return body;
}
