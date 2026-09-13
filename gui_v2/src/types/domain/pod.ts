/**
 * Pods — a vehicle the customer creates, sizes and pays for.
 *
 * The TypeScript twin of `agent/pod_sizing.py`. A pod is a row in
 * agent_vehicles with vehicle_type='cloud': the fleet scheduler places turns on
 * it, and unlike a discovered machine it is a recurring charge.
 *
 * Desired state (what the customer set) and observed state (what the fleet
 * reports) are kept apart on purpose. A customer raising `desired_replicas`
 * should watch `status` converge, not be told it already happened.
 */

export type PodLifecycle = 'always_on' | 'on_demand';

export const DEFAULT_LIFECYCLE: PodLifecycle = 'always_on';
export const DEFAULT_IDLE_SHUTDOWN_MINUTES = 15;

/**
 * CNY, TKE Serverless. These reproduce the fleet design's stated figure —
 * 2 vCPU / 4 GiB always-on ≈ ¥321/month — so they are the rates it was computed
 * from. A client-side estimate for a form, not billing: the server is the
 * authority on what anything actually cost.
 */
export const CPU_CORE_HOUR_CNY = 0.12;
export const MEMORY_GIB_HOUR_CNY = 0.05;
export const HOURS_PER_MONTH = 730;

export interface PodSize {
  id: string;
  cpu: number;
  memory_gb: number;
  concurrency: number;
}

export const POD_SIZES: PodSize[] = [
  { id: 'small', cpu: 1, memory_gb: 2, concurrency: 8 },
  { id: 'standard', cpu: 2, memory_gb: 4, concurrency: 16 },
  { id: 'large', cpu: 4, memory_gb: 8, concurrency: 32 },
  { id: 'xlarge', cpu: 8, memory_gb: 16, concurrency: 64 },
];

export interface PodCost {
  lifecycle: PodLifecycle;
  replicas: number;
  hourly_cny: number;
  monthly_cny: number;
  /** on_demand has no predictable monthly figure; this is the never-idle ceiling. */
  monthly_is_ceiling: boolean;
  currency: string;
}

export interface Pod {
  id: string;
  name: string;
  owner?: string;
  description?: string;

  // Desired state — what the customer set
  lifecycle: PodLifecycle;
  idle_shutdown_minutes?: number | null;
  desired_replicas: number;
  cpu_cores?: number | null;
  memory_gb?: number | null;
  capabilities: string[];
  max_concurrent_tasks?: number;

  // Observed state — what the fleet reports
  status?: string;
  last_heartbeat?: string | null;
  health_score?: number;

  cost?: PodCost;
}

export interface PodLimits {
  max_pods: number;
  daily_spend_cny: number;
  used_pods: number;
  enforced_by: string;
}

export function hourlyCostCny(cpu: number, memoryGb: number): number {
  return (cpu || 0) * CPU_CORE_HOUR_CNY + (memoryGb || 0) * MEMORY_GIB_HOUR_CNY;
}

export function monthlyCostCny(cpu: number, memoryGb: number): number {
  return hourlyCostCny(cpu, memoryGb) * HOURS_PER_MONTH;
}

export function estimatePodCost(
  cpu: number,
  memoryGb: number,
  lifecycle: PodLifecycle = DEFAULT_LIFECYCLE,
  replicas = 1,
): PodCost {
  const n = Math.max(1, replicas || 1);
  return {
    lifecycle,
    replicas: n,
    hourly_cny: Number((hourlyCostCny(cpu, memoryGb) * n).toFixed(4)),
    monthly_cny: Number((monthlyCostCny(cpu, memoryGb) * n).toFixed(2)),
    monthly_is_ceiling: lifecycle === 'on_demand',
    currency: 'CNY',
  };
}

export function sizeById(id: string): PodSize | undefined {
  return POD_SIZES.find((s) => s.id === id);
}

/** The size that matches a saved pod's cpu/mem, if it was made from one. */
export function matchSize(cpu?: number | null, memoryGb?: number | null): PodSize | undefined {
  return POD_SIZES.find((s) => s.cpu === cpu && s.memory_gb === memoryGb);
}

export function describeSize(size: PodSize): string {
  return `${size.cpu} vCPU · ${size.memory_gb} GiB · up to ${size.concurrency} turns at once`;
}

export const LIFECYCLE_OPTIONS: { value: PodLifecycle; label: string; help: string }[] = [
  {
    value: 'always_on',
    label: 'Always on',
    help: 'Stays up and answers immediately. Charged around the clock, whether or not anyone talks to the agent.',
  },
  {
    value: 'on_demand',
    label: 'On demand',
    help: 'Started when there is work and scaled away when idle. Cheaper, but the first reply after a quiet spell waits for a cold start (~80s).',
  },
];

// ---------------------------------------------------------------------------
// Reading a cloud vehicle row as a pod
//
// The TypeScript twin of `_pod_view` / `_is_customer_pod` in
// `gui/ipc/w2p_handlers/vehicle_handler.py`. The desktop reaches pods through
// the Python IPC handler; the web talks to CloudBase directly and has no
// Python, so the same rules have to exist on both sides. `tests/
// test_pods_are_cloud_backed.py` and `podModel.test.ts` pin them together.
// ---------------------------------------------------------------------------

/** Desired state travels under this key in `settings` until CN grows columns. */
export const POD_SETTINGS_KEY = 'pod';

export interface PodDesiredState {
  lifecycle: PodLifecycle;
  idle_shutdown_minutes?: number | null;
  desired_replicas: number;
}

/** A raw `queryVehicles` row. Snake and camel spellings both arrive. */
export type VehicleRow = Record<string, any>;

/** The desired-state blob this client wrote, or {}. */
export function podSettingsBlob(row: VehicleRow): Partial<PodDesiredState> {
  let settings = row?.settings ?? {};
  if (typeof settings === 'string') {
    try {
      settings = JSON.parse(settings);
    } catch {
      return {};
    }
  }
  if (!settings || typeof settings !== 'object' || Array.isArray(settings)) return {};
  const blob = (settings as any)[POD_SETTINGS_KEY];
  return blob && typeof blob === 'object' && !Array.isArray(blob) ? blob : {};
}

/**
 * True for a pod the customer created, not a running instance.
 *
 * `vehicle_type` alone does not separate them: the fleet's own
 * `vehicle_register` hard-codes 'cloud' for every pod that registers itself,
 * and each Deployment rollout leaves the previous pod behind as an offline
 * tombstone. Listing those as "your pods" shows invented costs and Delete
 * buttons for rows nobody created, and counts them against the pod limit.
 * Only `save_pod` writes the desired-state blob, so that is the discriminator.
 */
export function isCustomerPod(row: VehicleRow): boolean {
  return row?.vehicle_type === 'cloud' && Object.keys(podSettingsBlob(row)).length > 0;
}

/** What `save_pod` stores, so a backend without the columns can read it back. */
export function packPodSettings(desired: PodDesiredState): Record<string, any> {
  return { [POD_SETTINGS_KEY]: desired };
}

function pick(row: VehicleRow, ...names: string[]): any {
  for (const n of names) {
    if (row?.[n] !== null && row?.[n] !== undefined) return row[n];
  }
  return undefined;
}

/**
 * One cloud row as the UI needs it.
 *
 * Desired state is read column-first, blob-second: once CN has the columns the
 * column is authoritative and a blob written before the migration loses. Both
 * spellings of the sized fields are accepted because the server mirrors
 * camelCase to snake_case on the way out and only one is guaranteed present.
 */
export function podView(row: VehicleRow): Pod {
  const blob = podSettingsBlob(row);
  const desired = <K extends keyof PodDesiredState>(name: K): PodDesiredState[K] | undefined =>
    row?.[name] === null || row?.[name] === undefined ? blob[name] : row[name];

  const cpu = pick(row, 'cpu_cores', 'cpuCores') ?? 0;
  const memoryGb = pick(row, 'memory_gb', 'memoryGb') ?? 0;
  const lifecycle: PodLifecycle =
    desired('lifecycle') === 'on_demand' ? 'on_demand' : DEFAULT_LIFECYCLE;
  const replicas = Math.max(1, Number(desired('desired_replicas') ?? 1) || 1);

  return {
    ...row,
    id: row?.id,
    name: row?.name,
    status: row?.status || 'offline',
    cpu_cores: cpu,
    memory_gb: memoryGb,
    max_concurrent_tasks: pick(row, 'max_concurrent_tasks', 'maxConcurrentTasks') ?? 1,
    last_heartbeat: pick(row, 'last_heartbeat', 'lastHeartbeat') ?? null,
    health_score: pick(row, 'health_score', 'healthScore'),
    lifecycle,
    desired_replicas: replicas,
    idle_shutdown_minutes: desired('idle_shutdown_minutes') ?? null,
    capabilities: Array.isArray(row?.capabilities) ? row.capabilities : [],
    cost: estimatePodCost(cpu, memoryGb, lifecycle, replicas),
  };
}
