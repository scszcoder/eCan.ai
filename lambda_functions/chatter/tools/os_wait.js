/**
 * Tool handler: os_wait
 * Wait a specified number of seconds.
 */
export async function os_wait(toolInput) {
  const seconds = toolInput?.seconds ?? 1;
  const clampedSeconds = Math.min(Math.max(seconds, 0), 30); // cap at 30s for Lambda safety
  await new Promise((resolve) => setTimeout(resolve, clampedSeconds * 1000));
  return { waited_seconds: clampedSeconds };
}
