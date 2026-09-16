/**
 * Collect `{{var}}` placeholders out of a skill's prompts and turn them into
 * the skill's declared parameters (`need_inputs`).
 *
 * Why this exists: a `{{var}}` in a prompt resolves from the run's
 * prompt_refs, which are seeded from the task's `metadata.task_vars`. The task
 * form only renders a field for a variable the SKILL declares in need_inputs.
 * So a variable typed into a prompt is invisible until someone also declares
 * it by hand — and the failure is silent: the placeholder just never fills.
 * Scanning on save closes that loop.
 *
 * Nodes usually do NOT hold their prompt text: they reference a stored prompt
 * by id (`promptSelection: "pr-665505"`), and that is where the variables
 * actually live. Scanning inline text alone finds nothing on a typical skill,
 * so callers pass a `resolvePrompt` lookup — the prompt store already holds
 * every prompt's text, so this costs no network call.
 *
 * Deliberately ADD-ONLY: a prompt the lookup cannot resolve must never cause
 * an existing declaration to be dropped.
 */

import { traverseWorkflowNodes } from './traverse-workflow-nodes';

/** Placeholders the runtime fills itself — never task variables. */
const RUNTIME_PROVIDED = new Set([
  'input',
  'events',
  'attachments',
  'history',
  'messages',
  'query',
  'human_text',
  'result',
  'state',
]);

const VAR_PATTERN = /\{\{\s*([^}\s|]+?)\s*\}\}/g;

/** A field whose value may carry prompt text. Excludes id/selection refs. */
const isPromptField = (key: string): boolean => {
  const k = String(key || '');
  if (isPromptRefField(k)) return false;
  return /prompt/i.test(k) || /^(task|taskText|instruction|instructions)$/i.test(k);
};

/** A field naming a STORED prompt rather than carrying text. */
const isPromptRefField = (key: string): boolean =>
  /^(promptId|promptSelection|promptRef)$/i.test(String(key || ''));

const readContent = (value: any): string => {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const inner = (value as any).content;
    if (typeof inner === 'string') return inner;
  }
  return '';
};

/**
 * Every `{{var}}` found in the prompts of a diagram's nodes.
 *
 * Skips runtime-provided names and dotted references such as
 * `{{llm_planner.question_to_user}}`, which address an upstream node's output
 * rather than a task variable.
 */
export const collectPromptVars = (
  nodes: any[] | undefined,
  resolvePrompt?: (promptId: string) => string,
): string[] => {
  const found: string[] = [];
  const seen = new Set<string>();

  traverseWorkflowNodes(nodes, (node: any) => {
    const inputs = node?.data?.inputsValues;
    if (!inputs || typeof inputs !== 'object') return;
    Object.keys(inputs).forEach((key) => {
      // A referenced prompt's text is where the variables usually are.
      const isRef = isPromptRefField(key);
      if (!isRef && !isPromptField(key)) return;
      let text = readContent(inputs[key]);
      if (isRef) {
        const id = String(text || '').trim();
        text = id && resolvePrompt ? String(resolvePrompt(id) || '') : '';
      }
      if (!text || text.indexOf('{{') < 0) return;
      let m: RegExpExecArray | null;
      VAR_PATTERN.lastIndex = 0;
      while ((m = VAR_PATTERN.exec(text)) !== null) {
        const name = String(m[1] || '').trim();
        if (!name) continue;
        if (name.includes('.')) continue;              // upstream node output
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) continue;
        if (RUNTIME_PROVIDED.has(name)) continue;
        if (seen.has(name)) continue;
        seen.add(name);
        found.push(name);
      }
    });
  });

  return found;
};

export interface NeedInput {
  name: string;
  type?: string;
  required?: boolean;
  description?: string;
  default?: any;
  [k: string]: any;
}

/**
 * Merge scanned variable names into existing declarations, add-only.
 * Returns the same array instance when nothing was added, so callers can skip
 * a pointless write.
 */
export const mergeScannedVars = (
  existing: NeedInput[] | undefined | null,
  scanned: string[],
): NeedInput[] => {
  const current: NeedInput[] = Array.isArray(existing) ? existing : [];
  if (!scanned.length) return current;

  const known = new Set(current.map((i) => String(i?.name || '').trim()).filter(Boolean));
  const additions = scanned
    .filter((name) => !known.has(name))
    .map((name) => ({
      name,
      type: 'string',
      required: false,
      description: 'Found in a prompt',
    }));

  return additions.length ? [...current, ...additions] : current;
};

/** Convenience: scan a diagram and return the merged declaration list. */
export const syncNeedInputsFromPrompts = (
  nodes: any[] | undefined,
  existing: NeedInput[] | undefined | null,
  resolvePrompt?: (promptId: string) => string,
): NeedInput[] => mergeScannedVars(existing, collectPromptVars(nodes, resolvePrompt));

/**
 * Flatten one stored prompt to searchable text. A prompt is either markdown
 * (``mdContent``) or structured sections, and older ones only have
 * ``rawContent`` — all three shapes carry `{{var}}` placeholders.
 */
export const promptToText = (prompt: any): string => {
  if (!prompt || typeof prompt !== 'object') return '';
  const parts: string[] = [];
  if (typeof prompt.mdContent === 'string') parts.push(prompt.mdContent);
  if (typeof prompt.rawContent === 'string') parts.push(prompt.rawContent);
  for (const key of ['sections', 'userSections']) {
    const sections = (prompt as any)[key];
    if (!Array.isArray(sections)) continue;
    for (const section of sections) {
      const items = section?.items;
      if (Array.isArray(items)) {
        for (const item of items) if (typeof item === 'string') parts.push(item);
      }
      if (typeof section?.customLabel === 'string') parts.push(section.customLabel);
    }
  }
  if (Array.isArray(prompt.humanInputs)) {
    for (const h of prompt.humanInputs) if (typeof h === 'string') parts.push(h);
  }
  return parts.join('\n');
};

/** Build a lookup over the prompt store's loaded prompts. */
export const makePromptResolver = (prompts: any[] | undefined) => {
  const byId = new Map<string, string>();
  for (const p of prompts || []) {
    const id = String(p?.id || '').trim();
    if (id) byId.set(id, promptToText(p));
  }
  return (promptId: string): string => byId.get(String(promptId || '').trim()) || '';
};
