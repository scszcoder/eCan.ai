/**
 * Pods, on both platforms.
 *
 * The desktop reaches pods through the Python IPC handler
 * (`gui/ipc/w2p_handlers/vehicle_handler.py`), which owns the limit check and
 * the settings packing. The web has no Python — `api-router` sends it straight
 * to CloudBase — so the same composition happens here in TypeScript.
 *
 * Everything platform-independent lives in `types/domain/pod.ts` so there is
 * one definition of what a pod row means rather than two; this file is only
 * the transport and the response shape.
 */

import { detectPlatform } from '@/config/platform';
import { GRAPHQL_MUTATIONS, GRAPHQL_QUERIES } from '../api/api-config';
import { apiRouter } from '../api/api-router';
import type { APIResponse } from '../ipc/api';
import { IPCAPI } from '../ipc/api';
import {
  POD_SIZES,
  packPodSettings,
  isCustomerPod,
  podView,
  sizeById,
  type Pod,
  type PodLifecycle,
  type PodLimits,
  type VehicleRow,
} from '@/types/domain/pod';
import { logger } from '../../utils/logger';

export interface PodsResponse {
  pods: Pod[];
  sizes: typeof POD_SIZES;
  limits: PodLimits;
}

const isWeb = () => {
  try {
    return detectPlatform() !== 'desktop';
  } catch {
    return false;
  }
};

/**
 * Advisory only — the server enforces caps at scale-up and is the authority.
 * Shown so a customer does not walk into a refusal, not so the client can
 * decide who gets a pod. The desktop reads the same defaults from env.
 */
const DEFAULT_LIMITS = { max_pods: 5, daily_spend_cny: 500, enforced_by: 'server' };

function fail(code: string, message: string): APIResponse<any> {
  return { success: false, error: { code, message } } as APIResponse<any>;
}

export async function getPods(): Promise<APIResponse<PodsResponse>> {
  if (!isWeb()) return IPCAPI.getInstance().getPods<PodsResponse>();

  const resp = await apiRouter.execute<VehicleRow[]>(
    { method: 'get_pods', graphql: { query: GRAPHQL_QUERIES.QUERY_VEHICLES, resultPath: 'queryVehicles' } },
    { input: {} },
  );

  // An unreachable cloud is an error, not an empty list: pods live only in the
  // cloud, so [] would render as "you have no pods" and invite a customer to
  // create a second one alongside the pod they are already paying for.
  if (!resp?.success) return resp as unknown as APIResponse<PodsResponse>;

  const rows = Array.isArray(resp.data) ? resp.data : [];
  const pods = rows.filter(isCustomerPod).map(podView);
  return {
    success: true,
    data: { pods, sizes: POD_SIZES, limits: { ...DEFAULT_LIMITS, used_pods: pods.length } },
  } as APIResponse<PodsResponse>;
}

export async function savePod(params: Record<string, any>): Promise<APIResponse<any>> {
  if (!isWeb()) return IPCAPI.getInstance().savePod<any>(params);

  const name = String(params?.name || '').trim();
  if (!name) return fail('INVALID_PARAMS', 'name is required');

  const size = sizeById(String(params?.size_id || '')) || undefined;
  const cpu = params?.cpu_cores ?? size?.cpu;
  const memoryGb = params?.memory_gb ?? size?.memory_gb;
  const lifecycle: PodLifecycle = params?.lifecycle === 'on_demand' ? 'on_demand' : 'always_on';
  const replicas = Math.max(1, Number(params?.desired_replicas || 1) || 1);

  // Meaningless on an always-on pod; storing it would show a shutdown rule in
  // the UI that nothing will ever apply.
  let idleMinutes: number | null = null;
  if (lifecycle === 'on_demand' && params?.idle_shutdown_minutes != null) {
    idleMinutes = Math.max(1, Number(params.idle_shutdown_minutes));
  }

  const podId = String(params?.id || '').trim();

  if (!podId) {
    // Refuse rather than silently clamping: a customer who asked for four
    // replicas and got one without being told would read the fleet as broken.
    const existing = await getPods();
    if (!existing?.success) return existing as APIResponse<any>;
    const used = existing.data?.pods?.length ?? 0;
    if (used + 1 > DEFAULT_LIMITS.max_pods) {
      return fail(
        'POD_LIMIT_REACHED',
        `This account is limited to ${DEFAULT_LIMITS.max_pods} pods (${used} already exist). ` +
          'The server enforces this limit.',
      );
    }
  }

  const desired = { lifecycle, idle_shutdown_minutes: idleMinutes, desired_replicas: replicas };
  const fields: Record<string, any> = {
    name,
    vehicleType: 'cloud',
    description: params?.description || '',
    cpuCores: cpu != null ? Number(cpu) : null,
    memoryGb: memoryGb != null ? Number(memoryGb) : null,
    capabilities: Array.isArray(params?.capabilities) ? params.capabilities : [],
    maxConcurrentTasks: Number(params?.max_concurrent_tasks || size?.concurrency || 1),
    environment: params?.environment || 'production',
    // Always written, whether or not the columns exist: it is what a backend
    // without them reads back, and how a pod is told apart from a runtime
    // instance that registered itself.
    settings: packPodSettings(desired),
  };

  const id = podId || `pod_${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`;
  const resp = podId
    ? await apiRouter.execute<any>(
        { method: 'save_pod', graphql: { mutation: GRAPHQL_MUTATIONS.UPDATE_VEHICLES, resultPath: 'updateVehicles' } },
        { input: [{ id, ...fields }] },
      )
    : await apiRouter.execute<any>(
        { method: 'save_pod', graphql: { mutation: GRAPHQL_MUTATIONS.ADD_VEHICLES, resultPath: 'addVehicles' } },
        // A pod the customer just created has not been seen by the fleet yet;
        // saying offline is the truth until it registers itself.
        { input: [{ id, status: 'offline', ...fields }] },
      );

  if (!resp?.success) return resp;

  // addVehicles/updateVehicles report per-record success; a transport-level
  // success carrying success:false is still a failed save.
  const failure = (Array.isArray(resp.data) ? resp.data : []).find((r: any) => r && r.success === false);
  if (failure) return fail('SAVE_POD_ERROR', String(failure.error || 'Failed to save pod'));

  logger.debug(`[pods] saved pod ${id} (${name}) lifecycle=${lifecycle} replicas=${replicas}`);
  // The caller reloads from the cloud rather than trusting an echo, so there is
  // nothing to gain from reconstructing the saved row here.
  return { success: true, data: { id, message: 'Pod saved' } } as APIResponse<any>;
}

export async function deletePod(id: string): Promise<APIResponse<any>> {
  if (!isWeb()) return IPCAPI.getInstance().deletePod<any>(id);

  const podId = String(id || '').trim();
  if (!podId) return fail('INVALID_PARAMS', 'id is required');

  const resp = await apiRouter.execute<any>(
    { method: 'delete_pod', graphql: { mutation: GRAPHQL_MUTATIONS.REMOVE_VEHICLES, resultPath: 'removeVehicles' } },
    { ids: [podId] },
  );
  if (!resp?.success) return resp;

  const failure = (Array.isArray(resp.data) ? resp.data : []).find((r: any) => r && r.success === false);
  if (failure) return fail('DELETE_POD_ERROR', String(failure.error || 'Failed to delete pod'));

  return { success: true, data: { id: podId, message: 'Pod deleted' } } as APIResponse<any>;
}
