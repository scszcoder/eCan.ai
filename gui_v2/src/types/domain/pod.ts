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
