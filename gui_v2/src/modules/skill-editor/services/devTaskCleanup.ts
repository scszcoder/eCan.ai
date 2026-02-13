/**
 * Dev-mode Fargate task cleanup on logout.
 *
 * Registers with LogoutManager to cancel all active dev-mode ECS tasks
 * that were launched from the skill editor during this session.
 * This prevents orphaned Fargate tasks from running (and billing)
 * after the user logs out.
 */
import { logoutManager } from '../../../services/LogoutManager';
import { useRunningNodeStore } from '../stores/running-node-store';

let registered = false;

/**
 * Cancel all tracked dev-mode Fargate tasks.
 * Called automatically on logout and can also be called manually.
 */
async function cancelAllDevTasks(): Promise<void> {
  const { devTasks, clearDevTasks, setActiveRunId, setRunningNodeId } =
    useRunningNodeStore.getState();

  if (devTasks.length === 0) {
    console.log('[DevTaskCleanup] No dev tasks to cancel');
    return;
  }

  console.log(`[DevTaskCleanup] Cancelling ${devTasks.length} dev task(s) on logout...`);

  // Dynamic import to avoid circular deps
  const { IPCAPI } = await import('../../../services/ipc/api');
  const ipcApi = IPCAPI.getInstance();

  // We need a username for the cancel call
  let username: string | null = null;
  try {
    const { useUserStore } = await import('../../../stores/userStore');
    username = useUserStore.getState().username;
  } catch {
    // Fallback: try localStorage
    try {
      const session = localStorage.getItem('userSession');
      if (session) {
        const parsed = JSON.parse(session);
        username = parsed?.username || parsed?.user?.username;
      }
    } catch {}
  }

  if (!username) {
    console.warn('[DevTaskCleanup] No username available; cannot cancel dev tasks');
    return;
  }

  // Fire all cancel requests in parallel (best-effort, don't block logout)
  const cancelPromises = devTasks.map(async (task) => {
    try {
      const cancelPayload = {
        run_id: task.runId,
        skill_id: task.skillId,
      };
      console.log(`[DevTaskCleanup] Cancelling dev task: runId=${task.runId}, skillId=${task.skillId}`);
      await ipcApi.cancelRunSkill(username!, cancelPayload);
      console.log(`[DevTaskCleanup] ✅ Cancelled: ${task.runId}`);
    } catch (err) {
      console.warn(`[DevTaskCleanup] ⚠️ Failed to cancel ${task.runId}:`, err);
    }
  });

  // Wait for all cancels with a timeout so we don't block logout forever
  try {
    await Promise.race([
      Promise.allSettled(cancelPromises),
      new Promise((resolve) => setTimeout(resolve, 8000)), // 8s max
    ]);
  } catch {}

  // Clear tracking state
  clearDevTasks();
  setActiveRunId(null);
  setRunningNodeId(null);
  console.log('[DevTaskCleanup] All dev tasks processed');
}

/**
 * Register the cleanup handler with LogoutManager.
 * Safe to call multiple times — only registers once.
 */
export function registerDevTaskCleanup(): void {
  if (registered) return;
  registered = true;

  logoutManager.registerCleanup({
    name: 'DevTaskCleanup',
    cleanup: cancelAllDevTasks,
    priority: 10, // Run early — before user state/tokens are cleared (priority 25-30)
  });

  console.log('[DevTaskCleanup] Registered with LogoutManager (priority=10)');
}
