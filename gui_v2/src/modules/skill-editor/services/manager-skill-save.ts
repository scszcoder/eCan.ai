/**
 * Saves the skills the cloud Manager builds in the background.
 *
 * A Manager-requested build ends with a `skill_editor.chat.stream_end` whose
 * payload carries `managerHandoff = {skill_name?, store_id?, sessionId}` and the
 * finished `flowgram`. That skill is saved as a local skill through the Save
 * button's own steps (skill file, bundle, data mapping, DB row, Skills list,
 * cloud upload) WITHOUT loading it into the canvas, so whatever the owner has
 * open, saved or not, stays as it was. The relay's matching
 * `canvas.load_flowgram_data` for that flowgram is skipped.
 *
 * Saved at most once per (sessionId, skill_name, messageId); a local skill
 * with the same name is updated rather than duplicated.
 */
import i18n from 'i18next';
import { eventBus } from '../../../utils/eventBus';

export interface ManagerHandoff {
  skill_name?: string;
  store_id?: string;
  sessionId: string;
}

export interface ManagerSkillSavedEvent {
  sessionId: string;      // the chat session the build reported into
  threadId: string;       // managerHandoff.sessionId
  skillId: string;
  skillName: string;
  storeId?: string;
}

export const MANAGER_SKILL_SAVED_EVENT = 'skill_editor:manager_skill_saved';

// ---------------------------------------------------------------------------
// Once-only guard
// ---------------------------------------------------------------------------

const GUARD_STORAGE_KEY = 'ecan_manager_skill_saves';
const GUARD_MAX = 200;
const inFlightOrDone = new Set<string>();

function persistedKeys(): string[] {
  try {
    const raw = localStorage.getItem(GUARD_STORAGE_KEY);
    const list = raw ? JSON.parse(raw) : [];
    return Array.isArray(list) ? list.map(String) : [];
  } catch {
    return [];
  }
}

export function managerSaveKey(handoff: ManagerHandoff, messageId: string | undefined): string {
  return [handoff.sessionId, handoff.skill_name || '', messageId || ''].join('|');
}

/** True for the first caller of a key; false while it is saving or once it saved. */
export function claimManagerSave(key: string): boolean {
  if (inFlightOrDone.has(key) || persistedKeys().includes(key)) return false;
  inFlightOrDone.add(key);
  return true;
}

/** The save failed: let a later stream_end for the same key try again. */
export function releaseManagerSave(key: string): void {
  inFlightOrDone.delete(key);
}

/** The save succeeded: remember it across reloads too. */
export function confirmManagerSave(key: string): void {
  inFlightOrDone.add(key);
  try {
    const keys = persistedKeys().filter((k) => k !== key);
    keys.push(key);
    localStorage.setItem(GUARD_STORAGE_KEY, JSON.stringify(keys.slice(-GUARD_MAX)));
  } catch {
    // in-memory guard still holds for this session
  }
}

// ---------------------------------------------------------------------------
// Keep the Manager's flowgram off the canvas
// ---------------------------------------------------------------------------

const SUPPRESS_MS = 60_000;
const suppressedFlowgrams = new Map<string, number>();

// The relay sends the flowgram twice (stream_end, then canvas.load_flowgram_data),
// not always as the identical object, so match on its name and node ids.
function flowgramSignature(flowgram: any): string {
  const f = asObject(flowgram);
  if (!f || !Array.isArray(f.nodes) || f.nodes.length === 0) return '';
  const name = String(f.metadata?.skillName || f.skillName || f.name || '');
  return `${name}|${f.nodes.map((n: any) => String(n?.id ?? '')).join(',')}`;
}

export function suppressCanvasLoad(flowgram: any): void {
  const sig = flowgramSignature(flowgram);
  if (sig) suppressedFlowgrams.set(sig, Date.now() + SUPPRESS_MS);
}

/** True (once) when this flowgram is a Manager build that must not replace the canvas. */
export function consumeCanvasLoadSuppression(flowgram: any): boolean {
  const now = Date.now();
  for (const [sig, until] of suppressedFlowgrams) {
    if (until < now) suppressedFlowgrams.delete(sig);
  }
  const sig = flowgramSignature(flowgram);
  if (!sig || !suppressedFlowgrams.has(sig)) return false;
  suppressedFlowgrams.delete(sig);
  return true;
}

// ---------------------------------------------------------------------------
// The stream_end hook
// ---------------------------------------------------------------------------

function asObject(value: any): any {
  if (typeof value === 'string') {
    try { return JSON.parse(value); } catch { return null; }
  }
  return value && typeof value === 'object' ? value : null;
}

export function readManagerBuild(payload: any): { handoff: ManagerHandoff; flowgram: any } | null {
  const handoff = asObject(payload?.managerHandoff);
  const flowgram = asObject(payload?.flowgram);
  if (!handoff || !handoff.sessionId || !flowgram || !Array.isArray(flowgram.nodes)) return null;
  // Only the finished build: requirement and plan turns of the same build may carry a draft flowgram.
  if (payload?.state && payload.state !== 'complete') return null;
  return { handoff: handoff as ManagerHandoff, flowgram };
}

function skillBaseName(handoff: ManagerHandoff, flowgram: any): string {
  const raw = String(
    handoff.skill_name || flowgram?.metadata?.skillName || flowgram?.skillName || flowgram?.name || '',
  ).trim();
  return raw.replace(/_skill$/i, '').replace(/[\\/:*?"<>|]/g, '_').trim();
}

/**
 * Called for every stream_end, synchronously (unifiedEventHandler), so saving
 * does not depend on the chat panel being open: it marks the flowgram so the
 * canvas command that follows is skipped, then saves in the background.
 * Returns the save promise (resolved with the saved event, or null).
 */
export function handleManagerBuildDone(payload: any): Promise<ManagerSkillSavedEvent | null> | null {
  const build = readManagerBuild(payload);
  if (!build) return null;
  suppressCanvasLoad(payload.flowgram);
  const key = managerSaveKey(build.handoff, payload?.messageId);
  if (!claimManagerSave(key)) {
    console.log('[ManagerSkillSave] already saved, skipping:', key);
    return null;
  }
  return saveManagerBuild(build.handoff, build.flowgram, String(payload?.sessionId || ''))
    .then((saved) => {
      confirmManagerSave(key);
      eventBus.emit(MANAGER_SKILL_SAVED_EVENT, saved);
      return saved;
    })
    .catch((e) => {
      releaseManagerSave(key);
      console.warn('[ManagerSkillSave] save failed:', e);
      import('@douyinfe/semi-ui')
        .then(({ Toast }) => Toast.warning({
          content: i18n.t('chatPanel.managerSkillSaveFailed', { ns: 'skillEditor', error: String(e?.message || e) }),
        }))
        .catch(() => {});
      return null;
    });
}

async function saveManagerBuild(
  handoff: ManagerHandoff,
  flowgram: any,
  chatSessionId: string,
): Promise<ManagerSkillSavedEvent> {
  const [{ saveSkillDocument }, { flowgramToDocument }, { loadSkillFile }, { useSkillStore },
    { useUserStore }, { IPCAPI }, { detectPlatform }, { createSkillInfo }] = await Promise.all([
    import('../components/tools/save'),
    import('./canvas-controller'),
    import('./skill-loader'),
    import('../../../stores/domain/skillStore'),
    import('../../../stores/userStore'),
    import('../../../services/ipc/api'),
    import('../../../config/platform'),
    import('../typings/skill-info'),
  ]);
  await import('../../../services/ipc/file-api');

  const name = skillBaseName(handoff, flowgram);
  if (!name) throw new Error('the build has no skill name');
  const username = useUserStore.getState().username;
  const api = IPCAPI.getInstance();
  const isWeb = detectPlatform() === 'web';
  const description = String(flowgram?.metadata?.description || '');

  const findLocal = () => useSkillStore.getState().items.find((s: any) =>
    String(s.name || '').replace(/_skill$/i, '') === name && s.source !== 'code' && s.path,
  );
  let existing: any = findLocal();
  if (!existing) {
    const check = await api.checkSkillExists(name).catch(() => null);
    if (check?.success && check.data?.exists) {
      // On disk but not in the list yet: reload the list to learn its path.
      await useSkillStore.getState().forceRefresh(username || '').catch(() => {});
      existing = findLocal();
      if (!existing) throw new Error(`a skill named "${name}" exists but could not be located`);
    }
  }

  let filePath: string | null = null;
  let skillInfo: any;
  if (existing) {
    filePath = String(existing.path);
    const loaded = await loadSkillFile(filePath, { autoSaveMigrated: false, lightweight: true });
    skillInfo = loaded.success && loaded.skillInfo ? { ...loaded.skillInfo } : { skillName: name };
    skillInfo.skillName = name;
    skillInfo.skillId = skillInfo.skillId || String(existing.id);
    if (description) skillInfo.description = description;
  } else {
    const emptyFlow = { nodes: [], edges: [] } as any;
    skillInfo = createSkillInfo(emptyFlow);
    skillInfo.skillName = name;
    skillInfo.description = description;
    if (!isWeb) {
      // Same scaffold the New Skill button uses: my_skills/<name>_skill/... + DB row.
      const now = Date.now();
      const resp = await api.scaffoldSkill(name, description, 'diagram',
        { skillName: name, description, owner: '', version: '1.0.0', workFlow: emptyFlow, config: {},
          mode: 'development', run_mode: 'developing' },
        { mainSheetId: 'main', sheets: [{ id: 'main', name: 'Main', document: emptyFlow, createdAt: now, lastOpenedAt: now }],
          openTabs: ['main'], activeSheetId: 'main' });
      const data: any = resp?.data;
      if (!resp?.success || !data) throw new Error(resp?.error?.message || 'could not create the skill folder');
      filePath = data.diagramPath || `${data.skillRoot}/diagram_dir/${name}_skill.json`;
      if (data.skillId) skillInfo.skillId = String(data.skillId);
    }
  }

  const result = await saveSkillDocument({
    skillInfo,
    document: flowgramToDocument(flowgram),
    filePath,
    username,
    t: (key, options) => i18n.t(key, { ns: 'skillEditor', ...(options || {}) }) as string,
  });
  if (!result) throw new Error('the save did not complete');

  const skillName = result.finalSkillInfo?.skillName || name;
  const skillId = String(result.skillId || skillInfo.skillId || findLocal()?.id || '');

  try {
    const resp = await api.executeRequest('a2a.skill_saved', {
      skill_id: skillId,
      skill_name: skillName,
      store_id: handoff.store_id ?? null,
      thread_id: handoff.sessionId,
    });
    if (!resp?.success) console.warn('[ManagerSkillSave] a2a.skill_saved failed:', resp?.error);
  } catch (e) {
    console.warn('[ManagerSkillSave] a2a.skill_saved failed:', e);
  }

  return { sessionId: chatSessionId, threadId: handoff.sessionId, skillId, skillName, storeId: handoff.store_id };
}
