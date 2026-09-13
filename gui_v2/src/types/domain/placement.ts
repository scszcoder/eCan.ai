/**
 * Placement declarations — where work may run, and for how long.
 *
 * The TypeScript twin of `agent/placement.py`. A skill declares what it
 * `requires`; a pod advertises what it `capabilities`. The scheduler matches
 * one against the other, so the two lists must use the same words — a
 * requirement no pod can advertise is a turn that queues forever.
 *
 * Keep CAPABILITIES in step with `agent/placement.py`.
 */

export type Residency = 'local' | 'cloud' | 'any';
export type Lifetime = 'turn' | 'conversation' | 'long_running';

export const DEFAULT_RESIDENCY: Residency = 'any';
export const DEFAULT_LIFETIME: Lifetime = 'conversation';

export interface Placement {
  residency: Residency;
  lifetime: Lifetime;
  requires: string[];
}

export const DEFAULT_PLACEMENT: Placement = {
  residency: DEFAULT_RESIDENCY,
  lifetime: DEFAULT_LIFETIME,
  requires: [],
};

/** What a pod can advertise and a skill can require. */
export const CAPABILITIES = [
  'browser_local',
  'gpu',
  'cn_llm',
  'intl_llm',
  'long_running',
  'file_storage',
] as const;

export type Capability = (typeof CAPABILITIES)[number];

export const CAPABILITY_LABELS: Record<string, string> = {
  browser_local: 'Local browser (RPA / browser-use)',
  gpu: 'GPU inference',
  cn_llm: 'CN-region LLM routing',
  intl_llm: 'International LLM routing',
  long_running: 'Hosts work that never checkpoints',
  file_storage: 'Durable local scratch space',
};

/**
 * Isolation as a capability, never as a binding: a pod carrying
 * `dedicated:<agent-id>` is the only one that can claim that agent's work, but
 * it is still a scheduling decision — if the pod is down the work waits rather
 * than being stranded on a dead machine.
 */
export const DEDICATED_PREFIX = 'dedicated:';

export const dedicatedCapability = (agentId: string): string =>
  `${DEDICATED_PREFIX}${String(agentId || '').trim()}`;

export const isDedicatedCapability = (value: string): boolean =>
  String(value || '').startsWith(DEDICATED_PREFIX);

export const RESIDENCY_OPTIONS: { value: Residency; label: string; help: string }[] = [
  {
    value: 'any',
    label: 'Any',
    help: 'The scheduler places this wherever there is room. The default.',
  },
  {
    value: 'local',
    label: 'Local only',
    help: 'Runs on this machine. Choose this when the work needs something only this desktop has.',
  },
  {
    value: 'cloud',
    label: 'Cloud only',
    help: 'Runs on a pod. Choose this when the work should keep running with the desktop closed.',
  },
];

export const LIFETIME_OPTIONS: { value: Lifetime; label: string; help: string }[] = [
  {
    value: 'turn',
    label: 'Turn — one request, then done',
    help: 'Fine on a cold pod: the ~80s startup does not matter for work nobody is waiting on.',
  },
  {
    value: 'conversation',
    label: 'Conversation — many turns over time',
    help: 'Needs a warm pod. This is chat: somebody is waiting, so a cold start is felt.',
  },
  {
    value: 'long_running',
    label: 'Long running — holds a pod for its whole life',
    help: 'For work that cannot be checkpointed mid-run, such as a crawler holding a browser. It occupies a pod until it finishes.',
  },
];

/** Normalize anything stored on a skill/task into a complete Placement. */
export function readPlacement(source: Record<string, any> | null | undefined): Placement {
  const src = source || {};
  const residency = String(src.residency || '').toLowerCase();
  const lifetime = String(src.lifetime || '').toLowerCase();
  const requires = Array.isArray(src.requires)
    ? src.requires.map((r: any) => String(r || '').trim()).filter(Boolean)
    : [];
  return {
    residency: (['local', 'cloud', 'any'].includes(residency)
      ? residency
      : DEFAULT_RESIDENCY) as Residency,
    lifetime: (['turn', 'conversation', 'long_running'].includes(lifetime)
      ? lifetime
      : DEFAULT_LIFETIME) as Lifetime,
    requires: Array.from(new Set(requires)),
  };
}

/** True when a placement says nothing a scheduler could act on. */
export function isDefaultPlacement(p: Placement): boolean {
  return (
    p.residency === DEFAULT_RESIDENCY &&
    p.lifetime === DEFAULT_LIFETIME &&
    p.requires.length === 0
  );
}
