/**
 * "This tab was superseded by another client" latch.
 *
 * Desktop mode enforces ONE active session per account (see
 * `gui/ipc/token_manager.py`: `generate_token` deletes the previous token and
 * marks it `session_replaced`). Two frontends on the same machine — the app
 * window plus a browser pointed at the dev server, or two app instances — thus
 * take turns invalidating each other.
 *
 * The login page auto-resumes the backend's restored session
 * (`cloudbase_resume_session`) on mount. Combined with the mutual kick that
 * becomes a livelock: the kicked client reloads to /login, immediately resumes
 * itself, which kicks the other client, which reloads, resumes, ... — the
 * symptom users report as "the login page keeps refreshing" (measured cycle:
 * one new token every 6-9s, indefinitely).
 *
 * Marking the tab as superseded makes the login page stop auto-resuming, so a
 * kick costs exactly one logout instead of an endless ping-pong. The latch is
 * NOT time-bounded on purpose: while the other client is still alive it must
 * never self-promote back. A deliberate manual login clears it, and a fresh
 * tab has fresh sessionStorage, so both legitimate escapes keep working.
 */
const KEY = 'ecan_session_superseded_at';

export function markSessionSuperseded(): void {
  try {
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    /* sessionStorage unavailable — nothing to latch */
  }
}

export function isSessionSuperseded(): boolean {
  try {
    return sessionStorage.getItem(KEY) !== null;
  } catch {
    return false;
  }
}

export function clearSessionSuperseded(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}