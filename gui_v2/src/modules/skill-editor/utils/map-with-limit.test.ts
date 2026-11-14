import { mapWithLimit } from './map-with-limit';

describe('mapWithLimit', () => {
  it('keeps at most `limit` calls in flight and returns results in order', async () => {
    let inFlight = 0;
    let peak = 0;
    const out = await mapWithLimit([5, 1, 4, 2, 3], 2, async (n) => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, n));
      inFlight -= 1;
      return n * 10;
    });
    expect(out).toEqual([50, 10, 40, 20, 30]);
    expect(peak).toBe(2);
  });

  it('handles an empty list', async () => {
    expect(await mapWithLimit([], 3, async (n: number) => n)).toEqual([]);
  });
});
