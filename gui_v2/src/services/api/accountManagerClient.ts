/**
 * ecbAccountManager client.
 *
 * Some cloud capabilities are not GraphQL at all — ecbAccountManager takes
 * `{ action, input }` over POST. Pods are the first of these the UI needs:
 * `pod_list` / `pod_save` / `pod_delete` write `fleet_pools`, the DESIRED state
 * the fleet reconciler reads to build a real Deployment. Writing a pod through
 * GraphQL `addVehicles` instead puts it in `vehicles`, which is OBSERVED state —
 * the row exists and no pod is ever created from it.
 * Contract: eCan_lambda/cn/tencent/POD_API_FOR_CLIENT.md
 *
 * Pods live only in the cloud, so this is used on BOTH platforms — but not by
 * the same transport. The web build is served from the cloud origin and calls
 * ecbAccountManager directly. The desktop cannot: its UI runs on
 * http://localhost:3000 in dev and file:// when packaged, so the browser fetch
 * is refused by CORS ("blocked by CORS policy" -> "Failed to fetch"), and
 * `file://` sends `Origin: null`, which no server allowlist can usefully admit.
 * On the desktop the call therefore goes through the Python backend, which has
 * no origin to check and already holds the session token.
 */
import { detectPlatform } from '@/config/platform';
// Static, not a dynamic import: api-router does not import this module
// back (its only tie to ipc/api is a type-only import, erased at build),
// so there is no cycle to dodge — and a new dynamic edge makes Vite
// re-optimize deps, which breaks already-open pages with
// 'Outdated Optimize Dep' until they are reloaded.
import { apiRouter } from './api-router';
import { userStorageManager } from '../storage/UserStorageManager';
import { getCachedAppConfig } from '../../contexts/AppConfigContext';
import { logger } from '../../utils/logger';

/** Matches APIResponse in services/ipc/api.ts — callers already read `error.message`. */
export interface AccountManagerResponse<T = any> {
  success: boolean;
  data?: T;
  error?: { code: string; message: string; details?: unknown };
  status?: number;
}

const getSettings = (): any => {
  try {
    return (window as any)?.appSettings || (window as any)?.settings || null;
  } catch {
    return null;
  }
};

/**
 * The cloud origin, from the same sources the web build already trusts. The
 * GraphQL endpoint is `<origin>/api/graphql`; ecbAccountManager is a sibling
 * route on that origin, so only the path changes.
 */
export const getAccountManagerEndpoint = (): string => {
  const configured =
    (import.meta as any)?.env?.VITE_APPSYNC_ENDPOINT ||
    getCachedAppConfig()?.cloud?.graphql_endpoint ||
    getSettings()?.wan_api_endpoint ||
    '';
  const trimmed = String(configured).trim();
  if (!trimmed) {
    throw new Error('No cloud endpoint configured — pods need one (cloud.graphql_endpoint).');
  }
  return `${new URL(trimmed).origin}/ecbAccountManager`;
};

/**
 * Call one action. The server derives the owner from the verified bearer, so no
 * owner is ever sent: asserting it client-side is what returned
 * "Cross-owner access is forbidden" for the WeChat account, whose identity.sub
 * matched neither the prefixed nor the bare openid.
 */
export async function callAccountManager<T = any>(
  action: string,
  input?: Record<string, any>,
): Promise<AccountManagerResponse<T>> {
  // Desktop: proxy through the local backend. Same action, same response
  // shape, no browser origin for the cloud to reject.
  if (detectPlatform() === 'desktop') {
    const resp = await apiRouter.execute<T>(
      { method: 'account_manager_call' },
      { action, input: input || {} },
    );
    return resp as AccountManagerResponse<T>;
  }

  const token = userStorageManager.getToken();
  if (!token) {
    return { success: false, error: { code: 'TOKEN_REQUIRED', message: 'Not signed in.' } };
  }

  let endpoint: string;
  try {
    endpoint = getAccountManagerEndpoint();
  } catch (e) {
    return { success: false, error: { code: 'NO_ENDPOINT', message: (e as Error).message } };
  }

  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: token.startsWith('Bearer ') ? token : `Bearer ${token}`,
      },
      body: JSON.stringify({ action, input: input || {} }),
    });

    const body = await response.json().catch(() => ({} as any));

    if (!response.ok || body?.success === false) {
      // Carry the SERVER's message through untouched. The pod cap answers 409
      // with the real number ("that would put this account at 6 pods; the limit
      // is 5"); a generic "failed" throws that away and the customer cannot act.
      return {
        success: false,
        status: response.status,
        error: {
          code: body?.error || `HTTP_${response.status}`,
          message: body?.message || `${action} failed`,
        },
      };
    }

    const { success: _ignored, ...payload } = body;
    return { success: true, status: response.status, data: payload as T };
  } catch (error) {
    logger.error(`[AccountManager] ${action} failed`, error);
    return {
      success: false,
      error: {
        code: 'NETWORK_ERROR',
        message: error instanceof Error ? error.message : `${action} failed`,
      },
    };
  }
}
