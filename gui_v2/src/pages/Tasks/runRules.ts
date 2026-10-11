// Task run rules stored in task metadata (settings JSON) and read by the
// runner: agent/ec_tasks/resource_gate.py, task_deps.py and runner.py.

export interface RunRulesForm {
  run_class?: 'normal' | 'background';
  max_lateness_min?: number | null;
  overlap_policy?: 'skip' | 'queue_one';
  after_tasks?: string[];
  after_require_success?: boolean;
  exclusive_resources?: string[];
  run_once?: boolean;
  start_after_idle_min?: number | null;
}

export const RUN_RULE_KEYS = ['run_class', 'max_lateness_min', 'overlap_policy', 'after', 'exclusive_resources',
  'run_once', 'start_after_idle_min'];

export function readRunRules(metadata: any): RunRulesForm {
  const m = metadata && typeof metadata === 'object' ? metadata : {};
  const lateness = m.max_lateness_min;
  return {
    run_class: m.run_class === 'background' ? 'background' : 'normal',
    max_lateness_min: lateness === undefined || lateness === null || lateness === '' ? null : Number(lateness),
    overlap_policy: m.overlap_policy === 'queue_one' ? 'queue_one' : 'skip',
    after_tasks: Array.isArray(m.after?.tasks) ? m.after.tasks.map(String) : [],
    after_require_success: !!m.after?.require_success,
    exclusive_resources: Array.isArray(m.exclusive_resources) ? m.exclusive_resources.map(String) : [],
    run_once: !!m.run_once,
    start_after_idle_min: m.start_after_idle_min ? Number(m.start_after_idle_min) : null,
  };
}

/** metadata with the form's run rules applied; defaults are left out, not stored. */
export function applyRunRules(metadata: Record<string, any>, v: RunRulesForm): Record<string, any> {
  const out: Record<string, any> = { ...metadata };
  RUN_RULE_KEYS.forEach((k) => delete out[k]);
  if (v.run_class === 'background') out.run_class = 'background';
  if (v.max_lateness_min !== undefined && v.max_lateness_min !== null && String(v.max_lateness_min) !== ''
      && Number(v.max_lateness_min) >= 0) {
    out.max_lateness_min = Number(v.max_lateness_min);
  }
  if (v.overlap_policy === 'queue_one') out.overlap_policy = 'queue_one';
  const after = (v.after_tasks || []).map(String).filter(Boolean);
  if (after.length) out.after = { tasks: after, require_success: !!v.after_require_success };
  const exclusive = Array.from(new Set((v.exclusive_resources || []).map((s) => String(s).trim()).filter(Boolean)));
  if (exclusive.length) out.exclusive_resources = exclusive;
  if (v.run_once) out.run_once = true;
  if (v.start_after_idle_min && Number(v.start_after_idle_min) > 0) out.start_after_idle_min = Number(v.start_after_idle_min);
  return out;
}

function prereqsOf(task: any): string[] {
  let m = task?.metadata;
  if (typeof m === 'string') {
    try { m = JSON.parse(m); } catch { m = {}; }
  }
  return Array.isArray(m?.after?.tasks) ? m.after.tasks.map(String) : [];
}

/** Names along a dependency cycle through taskId (["A","B","A"]), or null. */
export function findAfterCycle(taskId: string, taskName: string, prereqs: string[], allTasks: any[]): string[] | null {
  const byId = new Map<string, any>((allTasks || []).map((t) => [String(t.id), t]));
  const next = (id: string) => (id === taskId ? prereqs : prereqsOf(byId.get(id)));
  const name = (id: string) => (id === taskId ? taskName : (byId.get(id)?.name || id));
  const seen = new Set<string>();
  const path: string[] = [];
  const visit = (id: string): string[] | null => {
    if (id === taskId && path.length) return [...path, id];
    if (seen.has(id)) return null;
    seen.add(id);
    path.push(id);
    for (const n of next(id)) {
      const hit = visit(String(n));
      if (hit) return hit;
    }
    path.pop();
    return null;
  };
  const cycle = visit(taskId);
  return cycle ? cycle.map(name) : null;
}
