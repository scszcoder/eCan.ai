/**
 * What each chat session is waiting on, so the panel can keep a "thinking…" bubble up
 * for the whole wait and not only while its send request is open:
 *
 * - a cloud turn: from the send until its stream_end, kept fresh by the
 *   `skill_editor.chat.progress` heartbeats {turnId, step, elapsedMs};
 * - the Manager's desktop round trips: its "Asking your desktop…" post carries
 *   `pending: true` + `requestIds`, and the post that resolves them repeats the ids with
 *   `pending: false` (or `kind: "status"` + `nextRequestIds` when it waits on more).
 *
 * Replies sent while another turn runs (`sideReply`: a status answer, or "queued")
 * leave the running turn's wait alone. Pure functions; ChatPanel holds the state.
 */

export interface ChatActivity {
  since: number;        // when the wait began (ms)
  lastBeat: number;     // last sign of life (ms)
  step?: string;        // the running turn's current step, from progress events
  turnId?: string;
  waitingOn?: string[]; // desktop request ids the Manager still waits for
}

export type ChatActivities = Record<string, ChatActivity>;

/** Seen no sign of life for this long, a wait counts as stalled. The cloud reports a
 *  turn whose heartbeat is older than 120 s as failed. */
export const STALL_MS = 120_000;

const ids = (v: unknown): string[] =>
  Array.isArray(v) ? v.map(String).filter(Boolean) : [];

/** pending / requestIds / nextRequestIds from a stream_end payload or a message's
 *  metadata (the "Asking your desktop…" post has them in its metadata). */
export function managerWait(p: any): { pending?: boolean; requestIds: string[]; next: string[] } {
  const srcs = [p, p?.manager, p?.metadata, p?.message?.metadata].filter(s => s && typeof s === 'object');
  const src = srcs.find(s => typeof s.pending === 'boolean' || Array.isArray(s.requestIds)) || {};
  return {
    pending: typeof src.pending === 'boolean' ? src.pending : undefined,
    requestIds: ids(src.requestIds),
    next: ids(src.nextRequestIds),
  };
}

function without(acts: ChatActivities, sid: string): ChatActivities {
  if (!(sid in acts)) return acts;
  const { [sid]: _gone, ...rest } = acts;
  return rest;
}

function waitOnDesktop(acts: ChatActivities, sid: string, resolved: string[], next: string[], now: number): ChatActivities {
  const cur = acts[sid];
  const left = (cur?.waitingOn || []).filter(id => !resolved.includes(id));
  const waitingOn = Array.from(new Set([...left, ...next]));
  if (waitingOn.length === 0) return without(acts, sid);
  return { ...acts, [sid]: { since: cur?.since ?? now, lastBeat: now, waitingOn } };
}

/** The owner sent a message: the session is busy from now on. */
export function startTurn(acts: ChatActivities, sid: string, now: number): ChatActivities {
  const cur = acts[sid];
  return { ...acts, [sid]: { ...cur, since: cur?.since ?? now, lastBeat: now } };
}

export function onProgress(acts: ChatActivities, p: any, now: number): ChatActivities {
  const sid = String(p?.sessionId || '');
  if (!sid) return acts;
  const cur = acts[sid];
  const elapsed = Number(p?.elapsedMs);
  return {
    ...acts,
    [sid]: {
      ...cur,
      since: cur?.since ?? (Number.isFinite(elapsed) ? now - elapsed : now),
      lastBeat: now,
      step: typeof p?.step === 'string' && p.step ? p.step : cur?.step,
      turnId: p?.turnId ? String(p.turnId) : cur?.turnId,
    },
  };
}

/** A stream_end (or manager.message, which arrives the same way) for session p.sessionId. */
export function onStreamEnd(acts: ChatActivities, p: any, now: number): ChatActivities {
  const sid = String(p?.sessionId || '');
  if (!sid || p?.sideReply) return acts;
  const cur = acts[sid];
  if (p?.state === 'cancelled') return without(acts, sid);
  if (p?.state === 'processing') {
    return cur ? { ...acts, [sid]: { ...cur, lastBeat: now } } : startTurn(acts, sid, now);
  }
  const wait = managerWait(p);
  if (wait.pending === true) {
    // "Asking your desktop…", or a resumed turn that asks for more.
    return waitOnDesktop(acts, sid, wait.next.length ? wait.requestIds : [], wait.next.length ? wait.next : wait.requestIds, now);
  }
  if (wait.pending === false) {
    return cur?.waitingOn ? waitOnDesktop(acts, sid, wait.requestIds, [], now) : without(acts, sid);
  }
  if (p?.source === 'manager') {
    // A Manager progress / "not responding" post: a sign of life, not an end.
    return cur ? { ...acts, [sid]: { ...cur, lastBeat: now } } : acts;
  }
  // The turn ended. A desktop wait the Manager opened earlier still stands.
  if (cur?.waitingOn?.length) {
    return { ...acts, [sid]: { since: cur.since, lastBeat: now, waitingOn: cur.waitingOn } };
  }
  return without(acts, sid);
}

/** The send request returned. `processing` (the cloud is still on it) and side replies
 *  (intent "busy") keep the wait; a Manager reply that waits on the desktop starts one. */
export function onSendResponse(acts: ChatActivities, sid: string, resp: any, now: number): ChatActivities {
  if (!sid) return acts;
  if (!resp) return without(acts, sid);
  if (resp.state === 'processing' || resp.intent === 'busy') return acts;
  const wait = managerWait(resp);
  if (wait.pending === true) return waitOnDesktop(acts, sid, [], wait.requestIds, now);
  return acts[sid]?.waitingOn?.length ? acts : without(acts, sid);
}

/** ms since the last sign of life when that is longer than STALL_MS, else 0. */
export function stalledFor(a: ChatActivity | undefined, now: number): number {
  if (!a) return 0;
  const age = now - a.lastBeat;
  return age > STALL_MS ? age : 0;
}

export function formatElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}m${String(s % 60).padStart(2, '0')}s` : `${s}s`;
}
