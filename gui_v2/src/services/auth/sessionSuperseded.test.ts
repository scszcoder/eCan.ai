import {
  markSessionSuperseded,
  isSessionSuperseded,
  clearSessionSuperseded,
} from './sessionSuperseded';

const KEY = 'ecan_session_superseded_at';

describe('sessionSuperseded latch', () => {
  beforeEach(() => {
    // Each case starts from a fresh tab (no latch) so state never leaks.
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it('is not superseded on a fresh tab', () => {
    expect(isSessionSuperseded()).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it('mark_session sets the latch and is detected', () => {
    expect(isSessionSuperseded()).toBe(false);

    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);
  });

  it('records a millisecond timestamp so a later reader can reason about age', () => {
    const before = Date.now();
    markSessionSuperseded();
    const stored = Number(sessionStorage.getItem(KEY));

    expect(Number.isFinite(stored)).toBe(true);
    expect(stored).toBeGreaterThanOrEqual(before);
    expect(stored).toBeLessThanOrEqual(Date.now());
  });

  it('is idempotent — marking again keeps the latch set', () => {
    markSessionSuperseded();
    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);
  });

  it('clear_session removes the latch', () => {
    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);

    clearSessionSuperseded();
    expect(isSessionSuperseded()).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it('clears even when nothing was ever marked (safe no-op)', () => {
    expect(() => clearSessionSuperseded()).not.toThrow();
    expect(isSessionSuperseded()).toBe(false);
  });

  it('mark → clear → mark transitions cleanly', () => {
    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);

    clearSessionSuperseded();
    expect(isSessionSuperseded()).toBe(false);

    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);
  });

  // Mirrors LoginCN.saveLoginSession(): a deliberate, successful manual login
  // calls clearSessionSuperseded() so the tab can auto-resume again later.
  it('a successful login clears an active latch', () => {
    // Simulate this tab having been kicked by another client.
    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);

    // ...the user logs in on purpose; the success path clears the latch.
    clearSessionSuperseded();

    expect(isSessionSuperseded()).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  // The latch lives in sessionStorage, so a brand-new tab starts unsaturated
  // (a legitimate escape from the latch, per the module doc).
  it('a fresh session tab does not inherit a previous tab latch', () => {
    markSessionSuperseded();
    expect(isSessionSuperseded()).toBe(true);

    // A new tab has its own empty sessionStorage.
    sessionStorage.clear();
    expect(isSessionSuperseded()).toBe(false);
  });

  describe('when sessionStorage is unavailable', () => {
    it('mark does not throw, is reports false, clear does not throw', () => {
      jest.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new Error('storage blocked');
      });
      jest.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
        throw new Error('storage blocked');
      });
      jest.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
        throw new Error('storage blocked');
      });

      expect(() => markSessionSuperseded()).not.toThrow();
      expect(isSessionSuperseded()).toBe(false);
      expect(() => clearSessionSuperseded()).not.toThrow();
    });
  });
});
