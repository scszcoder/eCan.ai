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
// The vehicles GraphQL mappings are deliberately gone: pods are fleet_pools
// rows, reached through ecbAccountManager, not vehicles rows reached through
// GraphQL. packPodSettings/isCustomerPod/podView belonged to the vehicles
// shape and have no reader left here — they stay in the domain module for the
// desktop's own migration path.
import { callAccountManager } from '../api/accountManagerClient';
import type { APIResponse } from '../ipc/api';
import { IPCAPI } from '../ipc/api';
import {
  POD_SIZES,
  sizeById,
  type Pod,
  type PodLifecycle,
  type PodLimits,
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

  // `vehicles` is OBSERVED state — rows a running pod writes about itself. A pod
  // the CUSTOMER asked for is a row in `fleet_pools`, which is what the fleet
  // reconciler reads to build a real Deployment; one written through addVehicles
  // exists in the database and no pod is ever created from it. So both platforms
  // go to ecbAccountManager. Contract:
  // eCan_lambda/cn/tencent/POD_API_FOR_CLIENT.md
  const resp = await callAccountManager<any>('pod_list');

  // An unreachable cloud is an error, not an empty list: pods live only in the
  // cloud, so [] would render as "you have no pods" and invite a customer to
  // create a second one alongside the pod they are already paying for.
  if (!resp?.success) return resp as unknown as APIResponse<PodsResponse>;

  const pods = (Array.isArray(resp.data?.pods) ? resp.data.pods : []).map(poolView);
  // Usage counts DESIRED replicas, not rows — one pool of 3 is 3 pods on the bill.
  const used = pods.reduce((n: number, p: Pod) => n + (Number(p.desired_replicas) || 0), 0);
  return {
    success: true,
    data: {
      pods,
      sizes: POD_SIZES,
      limits: {
        ...DEFAULT_LIMITS,
        used_pods: used,
        max_pods: Number(resp.data?.limits?.podCeiling) || DEFAULT_LIMITS.max_pods,
      },
    },
  } as APIResponse<PodsResponse>;
}

/**
 * A fleet_pools row as the panel's Pod. Desired and observed stay separate:
 * `desired_replicas` is what was asked for, `live_replicas` what the fleet
 * actually has, and merging them into one number is how a UI ends up claiming a
 * pod is running when it is not.
 */
function poolView(row: any): Pod {
  return {
    id: String(row?.id || ''),
    name: String(row?.name || ''),
    lifecycle: row?.lifecycle === 'on_demand' ? 'on_demand' : 'always_on',
    idle_shutdown_minutes: row?.idleShutdownMinutes ?? null,
    desired_replicas: Number(row?.desiredReplicas) || 0,
    cpu_cores: row?.cpu ?? null,
    memory_gb: row?.memoryGb ?? null,
    capabilities: Array.isArray(row?.capabilities) ? row.capabilities.map(String) : [],
    // `liveReplicas` comes from HEARTBEATS, not from a stored status: a pod keeps
    // status='online' until the reaper notices it died, up to 6 minutes later.
    status: Number(row?.liveReplicas) > 0 ? 'online' : 'offline',
    last_heartbeat: row?.instances?.[0]?.lastHeartbeat ?? null,
    // A FULL PodCost, not a partial one: the panel renders
    // `cost.monthly_cny.toFixed(0)` directly, so a missing field is a TypeError
    // and a blank page, not a blank number. The figure comes from the server's
    // estimatedMonthlyFen, which uses the same rates runnerCostFen bills at, so
    // the price beside a lifecycle toggle cannot drift from the charge.
    cost: {
      lifecycle: row?.lifecycle === 'on_demand' ? 'on_demand' : 'always_on',
      replicas: Number(row?.desiredReplicas) || 0,
      monthly_cny: (Number(row?.estimatedMonthlyFen) || 0) / 100,
      hourly_cny: (Number(row?.estimatedMonthlyFen) || 0) / 100 / 730,
      // on_demand only bills while it runs, so its monthly figure is a ceiling.
      monthly_is_ceiling: row?.lifecycle === 'on_demand',
      currency: 'CNY',
    },
  } as Pod;
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

  // No local cap pre-check: the server enforces it and answers 409 with the real
  // number ("that would put this account at 6 pods; the limit is 5"). Guessing
  // here can refuse a save the server would have allowed, and the guess was
  // wrong before — it counted rows that runtime pods had registered.

  // pod_save writes fleet_pools — the DESIRED state the reconciler converges.
  // Omit `id` to create; the server mints it. No owner is sent: the server takes
  // it from the verified bearer, and asserting it client-side is what returned
  // "Cross-owner access is forbidden" for this WeChat account.
  const resp = await callAccountManager<any>('pod_save', {
    ...(podId ? { id: podId } : {}),
    name,
    lifecycle,
    desired_replicas: replicas,
    idle_shutdown_minutes: idleMinutes ?? undefined,
    ...(cpu != null ? { cpu: Number(cpu) } : {}),
    ...(memoryGb != null ? { memory_gb: Number(memoryGb) } : {}),
    capabilities: Array.isArray(params?.capabilities) ? params.capabilities : [],
    ...(params?.task_id ? { task_id: String(params.task_id) } : {}),
  });

  // Carry the server's own message: the 409 names the real limit, and replacing
  // it with a generic failure leaves the customer nothing to act on.
  if (!resp?.success) return resp as APIResponse<any>;

  const id = String(resp.data?.pod?.id || podId || '');

  logger.debug(`[pods] saved pod ${id} (${name}) lifecycle=${lifecycle} replicas=${replicas}`);
  // The caller reloads from the cloud rather than trusting an echo, so there is
  // nothing to gain from reconstructing the saved row here.
  return { success: true, data: { id, message: 'Pod saved' } } as APIResponse<any>;
}

export async function deletePod(id: string): Promise<APIResponse<any>> {
  if (!isWeb()) return IPCAPI.getInstance().deletePod<any>(id);

  const podId = String(id || '').trim();
  if (!podId) return fail('INVALID_PARAMS', 'id is required');

  // Soft delete: the reconciler has to see the row to scale the Deployment to
  // zero. A row that vanishes first orphans a Deployment that keeps running and
  // keeps billing.
  const resp = await callAccountManager<any>('pod_delete', { id: podId });
  if (!resp?.success) return resp as APIResponse<any>;

  // The row survives until its pods are gone, so the honest word is "stopping".
  return {
    success: true,
    data: { id: podId, message: resp.data?.note || 'Pod stopping' },
  } as APIResponse<any>;
}
