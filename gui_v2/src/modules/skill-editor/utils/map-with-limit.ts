/**
 * Like Promise.all(items.map(fn)), but with at most `limit` calls in flight.
 * The local backend answers one request at a time: firing ~100 history loads
 * at once queued them past the 30 s request timeout and starved every other
 * GUI request behind them.
 */
export async function mapWithLimit<T, R>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<R>
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}
