/**
 * Tool handler: get_current_time
 * Returns the current date and time in yyyy-mm-dd hh:mm:ss format.
 */
export async function get_current_time(_toolInput) {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const datetime = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  return { datetime, timezone: "UTC", epoch_ms: now.getTime() };
}
