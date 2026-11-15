import {
  startTurn, onProgress, onStreamEnd, onSendResponse, managerWait, stalledFor, formatElapsed, STALL_MS,
  type ChatActivities,
} from './chat-activity';

const S = 's1';

describe('chat activity: the "thinking…" bubble stays up for the whole wait', () => {
  it('a turn runs from the send to its stream_end, kept fresh by progress', () => {
    let a: ChatActivities = startTurn({}, S, 1000);
    a = onSendResponse(a, S, { state: 'processing' }, 31_000);        // cloud still on it
    expect(a[S]).toBeTruthy();
    a = onProgress(a, { sessionId: S, turnId: 't1', step: 'generate_flowgram', elapsedMs: 40_000 }, 41_000);
    expect(a[S]).toMatchObject({ since: 1000, step: 'generate_flowgram', turnId: 't1', lastBeat: 41_000 });
    a = onStreamEnd(a, { sessionId: S, state: 'complete', turnId: 't1' }, 60_000);
    expect(a[S]).toBeUndefined();
  });

  it('side replies (a status answer, "queued") leave the running turn alone', () => {
    let a = onProgress({}, { sessionId: S, turnId: 't1', step: 'plan', elapsedMs: 5000 }, 10_000);
    const before = a[S];
    a = onStreamEnd(a, { sessionId: S, state: 'answered', intent: 'busy', sideReply: true, busyTurnId: 't1' }, 12_000);
    a = onSendResponse(a, S, { state: 'queued', intent: 'busy', turnId: 't2' }, 12_000);
    expect(a[S]).toBe(before);
  });

  it('a Manager desktop round trip waits until a post resolves its request ids', () => {
    let a = startTurn({}, S, 0);
    a = onSendResponse(a, S, { state: 'idle', intent: 'manager',
      message: { metadata: { manager: true, pending: true, requestIds: ['r1'] } } }, 5000);
    expect(a[S].waitingOn).toEqual(['r1']);
    a = onStreamEnd(a, { sessionId: S, source: 'manager', correlationId: 'r1' }, 65_000);   // progress post
    expect(a[S]).toMatchObject({ waitingOn: ['r1'], lastBeat: 65_000, since: 0 });
    a = onStreamEnd(a, { sessionId: S, source: 'manager', kind: 'status', pending: true,
      requestIds: ['r1'], nextRequestIds: ['r2'] }, 70_000);                               // asks for more
    expect(a[S].waitingOn).toEqual(['r2']);
    a = onStreamEnd(a, { sessionId: S, source: 'manager', pending: false, requestIds: ['r2'] }, 90_000);
    expect(a[S]).toBeUndefined();
  });

  it('the turn ending does not end a desktop wait opened before it', () => {
    let a = onStreamEnd({}, { sessionId: S, state: 'idle', pending: true, requestIds: ['r1'] }, 1000);
    a = onStreamEnd(a, { sessionId: S, state: 'idle', intent: 'manager' }, 2000);
    expect(a[S].waitingOn).toEqual(['r1']);
  });

  it('a cancelled turn ends the wait', () => {
    const a = onStreamEnd(startTurn({}, S, 0), { sessionId: S, state: 'cancelled' }, 1000);
    expect(a[S]).toBeUndefined();
  });

  it('reads the wait flags from the payload, its manager block or its message metadata', () => {
    expect(managerWait({ pending: false, requestIds: ['a'] })).toEqual({ pending: false, requestIds: ['a'], next: [] });
    expect(managerWait({ manager: { pending: true, requestIds: ['b'] } }).requestIds).toEqual(['b']);
    expect(managerWait({ message: { metadata: { pending: true, requestIds: ['c'] } } }).pending).toBe(true);
    expect(managerWait({ manager: true }).pending).toBeUndefined();
  });

  it('counts as stalled only past STALL_MS without a sign of life', () => {
    const a = startTurn({}, S, 0)[S];
    expect(stalledFor(a, STALL_MS)).toBe(0);
    expect(stalledFor(a, STALL_MS + 1)).toBe(STALL_MS + 1);
    expect(formatElapsed(192_000)).toBe('3m12s');
    expect(formatElapsed(9_400)).toBe('9s');
  });
});
