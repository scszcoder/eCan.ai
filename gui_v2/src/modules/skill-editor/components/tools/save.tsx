import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useClientContext } from '@flowgram.ai/free-layout-editor';

import { Tooltip, IconButton, Toast, Modal, Input } from '@douyinfe/semi-ui';
import { IconSaveColored, IconSaveAsColored } from './colored-icons';
import { useUserStore } from '../../../../stores/userStore';
import { useSkillStore } from '../../../../stores/domain/skillStore';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { SkillInfo } from '../../typings/skill-info';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { ipcApi, IPCAPI } from '../../../../services/ipc/api';
import { useSheetsStore } from '../../stores/sheets-store';
import { saveSheetsBundleToPath } from '../../services/sheets-persistence';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useNodeNoteStore } from '../../stores/node-note-store';
import { sanitizeNodeApiKeys, sanitizeApiKeysDeep } from '../../utils/sanitize-utils';
import { traverseWorkflowNodes } from '../../utils/traverse-workflow-nodes';
import { detectPlatform } from '../../../../config/platform';
import { CURRENT_SCHEMA_VERSION } from '../../services/schema-migration';

// ============================================================================
// Common utilities for Save and SaveAs
// ============================================================================
//
// NOTE ON SCHEMA VERSION:
// When saving, we always set `schemaVersion` to CURRENT_SCHEMA_VERSION.
// This marks the file as using the latest workflow data structure format.
// See: services/schema-migration.ts for version history and migration logic.
// See: typings/skill-info.ts for the difference between `version` and `schemaVersion`.
// ============================================================================

/**
 * Prepare diagram for saving: handle flip states and remove breakpoints
 */
function prepareDiagramForSave(diagram: any, isFlipped: (id: string) => boolean): void {
  // Read all notes from the store once (avoids per-node getState calls)
  const allNotes = useNodeNoteStore.getState().notes;

  traverseWorkflowNodes(diagram.nodes || [], (node: any) => {
      if (!node.data) node.data = {};
      
      // Persist flip states
      const flipState = isFlipped(node.id);
      if (flipState) {
        node.data.hFlip = true;
      } else if (node.data.hFlip) {
        delete node.data.hFlip;
      }
      
      // Remove breakpoints (not persisted)
      if (node.data.break_point) {
        delete node.data.break_point;
      }

      // Inject agentNote from the external note store.
      // The flowgram form model doesn't expose setFieldValue, so notes are
      // stored externally and merged into the serialised diagram here.
      const note = allNotes.get(node.id);
      if (note) {
        node.data.agentNote = note;
      }
      
  });
}

/**
 * Extract mapping_rules from nodes into config.nodes for backend runtime
 */
function extractConfigNodes(diagram: any): Record<string, any> {
  const configNodes: Record<string, any> = {};
  try {
    for (const n of diagram.nodes || []) {
      const data = n?.data || {};
      if (data.mapping_rules) {
        const key = (data.name || n.id || '').toString();
        if (key) {
          configNodes[key] = { ...(configNodes[key] || {}), mapping_rules: data.mapping_rules };
        }
      }
    }
  } catch (e) {
    console.warn('[Save] mapping_rules extraction skipped', e);
  }
  return configNodes;
}

/**
 * Derive bundle file path from skill file path
 */
function deriveBundlePath(skillFilePath: string | null, skillName?: string): string {
  if (skillFilePath) {
    if (/_skill\.json$/i.test(skillFilePath)) {
      return skillFilePath.replace(/_skill\.json$/i, '_skill_bundle.json');
    } else if (/\.json$/i.test(skillFilePath)) {
      return skillFilePath.replace(/\.json$/i, '_skill_bundle.json');
    } else {
      return `${skillFilePath}_skill_bundle.json`;
    }
  }
  return skillName ? `${skillName}_skill_bundle.json` : 'skill_bundle.json';
}

const DEFAULT_DATA_MAPPING = {
  developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
  released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
  node_transfers: {},
  event_data_mapping: {},
};

function deriveDataMappingPath(skillFilePath: string | null, skillName?: string): string {
  if (skillFilePath) {
    const normalized = String(skillFilePath).replace(/\\/g, '/');
    if (normalized.includes('/diagram_dir/')) {
      const root = normalized.split('/diagram_dir/')[0];
      return `${root}/data_mapping.json`;
    }
    const baseDir = normalized.replace(/\/[^/]+$/, '');
    return `${baseDir}/data_mapping.json`;
  }
  if (skillName) {
    const base = normalizeSkillBaseName(skillName);
    // Folder name includes _skill suffix
    return `my_skills/${base}_skill/data_mapping.json`;
  }
  return 'data_mapping.json';
}

function buildDataMappingFromState(skillInfo: SkillInfo, diagram: any) {
  const skillMapping = (skillInfo as any)?.config?.skill_mapping || {
    developing: DEFAULT_DATA_MAPPING.developing,
    released: DEFAULT_DATA_MAPPING.released,
  };

  const node_transfers: Record<string, any> = {};
  try {
    for (const n of diagram.nodes || []) {
      const data = n?.data || {};
      if (data.mapping_rules) {
        const key = (data.name || n.id || '').toString();
        if (key) {
          node_transfers[key] = data.mapping_rules;
        }
      }
    }
  } catch (e) {
    console.warn('[Save] node_transfers build skipped', e);
  }

  return {
    developing: skillMapping.developing || DEFAULT_DATA_MAPPING.developing,
    released: skillMapping.released || DEFAULT_DATA_MAPPING.released,
    node_transfers,
    event_data_mapping: skillMapping.event_data_mapping || skillMapping.event_routing || {},
  };
}

function buildBundleJsonForSave(bundle: any): string {
  const sanitizedBundle = JSON.parse(JSON.stringify(bundle));
  if (sanitizedBundle.sheets) {
    sanitizedBundle.sheets.forEach((sheet: any) => {
      if (sheet.document?.nodes) {
        sanitizeNodeApiKeys(sheet.document.nodes);
      }
    });
  }
  sanitizeApiKeysDeep(sanitizedBundle);
  return JSON.stringify(sanitizedBundle, null, 2);
}

/**
 * Save bundle alongside skill file
 */
async function saveBundleFile(
  bundlePath: string,
  diagram: any,
  saveActiveSheetDoc: (doc: any) => void,
  getAllSheets: () => any,
  t: (key: string, options?: Record<string, any>) => string
): Promise<void> {
  try {
    saveActiveSheetDoc(diagram);
    const bundle = getAllSheets();
    console.log('[SKILL_IO][BUNDLE_SAVE_ATTEMPT]', { path: bundlePath, sheetsCount: bundle.sheets.length });
    const bundleRes = await saveSheetsBundleToPath(bundlePath, bundle);
    console.log('[SKILL_IO][BUNDLE_SAVE_RESULT]', { path: bundlePath, success: true, mode: bundleRes.mode });
    const msg = bundleRes.mode === 'ipc'
      ? t('save.bundleSaved', { path: bundleRes.filePath || bundlePath })
      : t('save.bundleDownloaded');
    try { Toast.success({ content: msg }); } catch {}
  } catch (e) {
    console.warn('[SKILL_IO][BUNDLE_SAVE_ERROR]', (e as Error).message);
    try { Toast.error({ content: t('save.bundleSaveFailed') }); } catch {}
  }
}

/**
 * Derive skill name from file path
 */
function deriveSkillNameFromPath(filePath: string, fallback: string): string {
  try {
    const norm = String(filePath).replace(/\\/g, '/');
    const parts = norm.split('/');
    const idx = parts.lastIndexOf('diagram_dir');
    if (idx > 0) {
      const folder = parts[idx - 1];
      return folder?.replace(/_skill$/i, '') || fallback;
    } else {
      const base = (parts.pop() || '').replace(/\.json$/i, '');
      return base.replace(/_skill$/i, '') || fallback;
    }
  } catch {
    return fallback;
  }
}
// Add File System Access API 的TypeDefinition
declare global {
  interface Window {
    showSaveFilePicker(options?: {
      suggestedName?: string;
      types?: Array<{
        description: string;
        accept: Record<string, string[]>;
      }>;
    }): Promise<FileSystemFileHandle>;
  }

  interface FileSystemFileHandle {
    createWritable(): Promise<FileSystemWritableFileStream>;
  }

  interface FileSystemWritableFileStream extends WritableStream {
    write(data: any): Promise<void>;
    close(): Promise<void>;
  }
}

interface SaveProps {
  disabled?: boolean;
}

// 是否EnabledLocal下载 SkillInfo 文件
const ENABLE_LOCAL_DOWNLOAD = true;

function normalizeSkillBaseName(skillName?: string): string {
  const raw = (skillName || 'untitled').trim();
  return raw.replace(/_skill$/i, '') || 'untitled';
}

/**
 * Sanitize username/email to be safe for S3 directory paths.
 * Converts "jack@xyz.com" -> "jack_xyz_com"
 * Must match backend _safe_user_dir_name() in skill_editor_agent.py
 */
function sanitizeUsername(username: string): string {
  const u = (username || '').trim();
  if (!u) return 'unknown';
  if (u.includes('@')) {
    const [localPart, domainPart] = u.split('@', 2);
    return `${localPart}_${(domainPart || '').replace(/\./g, '_')}`;
  }
  return u.replace(/@/g, '_').replace(/\./g, '_');
}

function buildWebSkillPath(skillName: string, username?: string | null): string {
  const base = normalizeSkillBaseName(skillName);
  // Folder name includes _skill suffix, e.g., "abc" -> "abc_skill/"
  const folderName = `${base}_skill`;
  // Sanitize username for S3 path (convert @ and . to _)
  const ownerPrefix = username ? `${sanitizeUsername(username)}/` : '';
  return `${ownerPrefix}my_skills/${folderName}/diagram_dir/${base}_skill.json`;
}

export async function saveFile(
  dataToSave: SkillInfo,
  _username?: string,
  currentFilePath?: string | null,
  dataMappingJson?: string | null,
  bundleJson?: string | null
) {
  try {
    console.log('[SKILL_IO][SAVE_V2] saveFile called', {
      platform: detectPlatform(),
      hasCurrentPath: !!currentFilePath,
      currentFilePath,
      skillName: dataToSave.skillName,
    });
    const jsonString = JSON.stringify(dataToSave, null, 2);
    // console.log('--- Debug Save: Final JSON String ---', jsonString);

    if (detectPlatform() === 'web') {
      try {
        let filePath = currentFilePath;
        // Defense-in-depth: rewrite flat my_skills paths to nested convention
        if (filePath) {
          const normCheck = String(filePath).replace(/\\/g, '/');
          if (!normCheck.includes('/diagram_dir/') && normCheck.includes('/my_skills/')) {
            const fileName = normCheck.split('/').pop() || '';
            const base = fileName.replace(/\.json$/i, '').replace(/_skill$/i, '');
            const parentDir = normCheck.replace(/\/[^/]+$/, '');
            filePath = `${parentDir}/${base}_skill/diagram_dir/${base}_skill.json`;
            console.log('[SKILL_IO][FRONTEND][WEB_PATH_REWRITE] Flat path rewritten to nested:', filePath);
          }
        }
        if (!filePath) {
          filePath = buildWebSkillPath(dataToSave.skillName, _username);
          console.log('[SKILL_IO][FRONTEND][WEB_DEFAULT_PATH]', filePath);
        }
        const mappingPath = dataMappingJson ? deriveDataMappingPath(filePath, dataToSave.skillName) : null;
        const bundlePath = deriveBundlePath(filePath, dataToSave.skillName);
        const batch = [
          { filePath, content: jsonString },
          ...(dataMappingJson && mappingPath ? [{ filePath: mappingPath, content: dataMappingJson }] : []),
          ...(bundleJson ? [{ filePath: bundlePath, content: bundleJson }] : []),
        ];

        const ipcApi = IPCAPI.getInstance();
        const writeResult = await ipcApi.writeSkillFile(batch);
        const firstResult = Array.isArray(writeResult.data) ? writeResult.data[0] : writeResult.data;
        if (!firstResult) {
          throw new Error('writeSkillFile failed.');
        }
        console.log('[SKILL_IO][FRONTEND][WEB_SAVE_OK]', filePath);
        return { success: true, filePath, skillName: firstResult.skillName };
      } catch (error) {
        console.error('[SKILL_IO][FRONTEND][WEB_SAVE_ERROR]', error);
        throw error;
      }
    }

    if (ENABLE_LOCAL_DOWNLOAD) {
      // Try IPC first regardless of platform flags
      try {
        const ipcApi = IPCAPI.getInstance();
        console.log('[SKILL_IO][FRONTEND][IPC_ATTEMPT] showSaveDialog');
        let filePath = currentFilePath;
        // Defense-in-depth: if filePath is set but flat (no diagram_dir), rewrite to nested
        if (filePath) {
          const normCheck = String(filePath).replace(/\\/g, '/');
          if (!normCheck.includes('/diagram_dir/') && normCheck.includes('/my_skills/')) {
            const fileName = normCheck.split('/').pop() || '';
            const base = fileName.replace(/\.json$/i, '').replace(/_skill$/i, '');
            const parentDir = normCheck.replace(/\/[^/]+$/, '');
            filePath = `${parentDir}/${base}_skill/diagram_dir/${base}_skill.json`;
            console.log('[SKILL_IO][FRONTEND][PATH_REWRITE] Flat path rewritten to nested:', filePath);
          }
        }
        if (!filePath) {
          // First-time save: show native dialog with a default path that follows
          // the nested convention: my_skills/<name>_skill/diagram_dir/<name>_skill.json
          const baseName = normalizeSkillBaseName(dataToSave.skillName);
          const defaultFileName = `${baseName}_skill.json`;
          console.log('[SKILL_IO][FRONTEND][FIRST_SAVE] Showing save dialog, default:', defaultFileName);
          const dialogResponse = await ipcApi.showSaveDialog(defaultFileName, [
            { name: 'Skill Files', extensions: ['json'] },
            { name: 'All Files', extensions: ['*'] }
          ]);
          if (dialogResponse.success && dialogResponse.data && !(dialogResponse.data as any).cancelled) {
            const chosenPath = (dialogResponse.data as any).filePath || (dialogResponse.data as any).filePaths?.[0];
            if (chosenPath) {
              // If user picked a flat path (e.g. my_skills/foo_skill.json), rewrite it
              // to the nested convention: my_skills/foo_skill/diagram_dir/foo_skill.json
              const norm = String(chosenPath).replace(/\\/g, '/');
              if (!norm.includes('/diagram_dir/')) {
                // Extract the base name from the chosen file name
                const chosenFileName = norm.split('/').pop() || '';
                const chosenBase = chosenFileName.replace(/\.json$/i, '').replace(/_skill$/i, '');
                const parentDir = norm.replace(/\/[^/]+$/, ''); // directory user saved into
                filePath = `${parentDir}/${chosenBase}_skill/diagram_dir/${chosenBase}_skill.json`;
                console.log('[SKILL_IO][FRONTEND][FIRST_SAVE] Rewritten to nested path:', filePath);
              } else {
                filePath = chosenPath;
              }
            }
          } else {
            console.log('[SKILL_IO][FRONTEND] Save cancelled by user');
            return { cancelled: true };
          }
        }
        // Existing file: enforce _skill.json suffix
        if (filePath) {
          if (/\.(json)$/i.test(filePath) && !/_skill\.json$/i.test(filePath)) {
            filePath = filePath.replace(/\.json$/i, '_skill.json');
          }
          if (!/\.json$/i.test(filePath)) {
            filePath = `${filePath}_skill.json`;
          }
        }
        if (filePath) {
          console.log('[SKILL_IO][FRONTEND][IPC_ATTEMPT] writeSkillFile', filePath);
          const writeResponse = await ipcApi.writeSkillFile({ filePath, content: jsonString });
          if (writeResponse.success) {
            console.log('[SKILL_IO][FRONTEND][MAIN_SAVE_OK]', filePath);
            // 需求4: 使用Backend返回的 skillName UpdateFrontend
            const responseData = Array.isArray(writeResponse.data) ? writeResponse.data[0] : writeResponse.data;
            const savedSkillName = responseData?.skillName;
            console.log('[SKILL_IO][FRONTEND][SKILL_NAME_FROM_BACKEND]', savedSkillName);
            if (dataMappingJson) {
              const mappingPath = deriveDataMappingPath(filePath, dataToSave.skillName);
              try {
                await ipcApi.writeSkillFile({ filePath: mappingPath, content: dataMappingJson });
              } catch (e) {
                console.warn('[SKILL_IO][FRONTEND][MAPPING_SAVE_ERROR]', e);
              }
            }
            return { 
              success: true, 
              filePath,
              skillName: savedSkillName  // 返回 skillName Used forUpdate
            };
          }
          console.error('[SKILL_IO][FRONTEND][MAIN_SAVE_ERROR]', writeResponse.error);
          throw new Error(writeResponse.error || 'Failed to write file');
        }
      } catch (err) {
        console.warn('[SKILL_IO][FRONTEND][IPC_SAVE_ERROR]', err);
      }

      // Web fallback: File System Access API or forced download
      const blob = new Blob([jsonString], { type: 'application/json' });
      const fileName = (dataToSave.skillName || 'skill') + '_skill.json';
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: fileName,
          types: [{ description: 'JSON Files', accept: { 'application/json': ['.json'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        console.log('[SKILL_IO][FRONTEND][MAIN_SAVE_OK_WEB]', fileName);
        return { success: true };
      } catch (e) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 100);
        console.log('[SKILL_IO][FRONTEND][MAIN_SAVE_OK_DOWNLOAD]', fileName);
        return { success: true };
      }
    }
    
    return { success: true };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      console.log('Save operation was cancelled by user');
      return { cancelled: true };
    } else {
      console.error('[SKILL_IO][FRONTEND][MAIN_SAVE_FATAL]', error);
      throw error;
    }
  }
}


/**
 * After disk save, sync skill to local DB + cloud DB and update the Skills page store.
 * Uses saveAgentSkill IPC (upsert) which handles both create and update,
 * plus cloud sync automatically.
 */
async function syncSkillToDBAndStore(
  skillInfo: any,
  filePath: string,
  username: string | null | undefined,
) {
  try {
    const api = IPCAPI.getInstance();
    const owner = username || '';

    const localHelperSkillId = (skillInfo as any).local_helper_skill_id ?? null;
    const localHelperMachine = (skillInfo as any).local_helper_machine ?? null;
    const hybridCloudMode = (skillInfo as any).hybrid_cloud_mode ?? false;
    const runInCloud = (skillInfo as any).run_in_cloud ?? false;
    const existingConfig = (skillInfo as any).config || {};
    const helperNameFromStore = (() => {
      try {
        if (!localHelperSkillId || typeof localHelperSkillId !== 'string') return null;
        if (!localHelperSkillId.startsWith('skill_')) return String(localHelperSkillId);
        const store = useSkillStore.getState();
        const found = store.items.find((s: any) => String(s.id) === String(localHelperSkillId));
        return found?.name || null;
      } catch {
        return null;
      }
    })();

    const updatedConfig = {
      ...existingConfig,
      run_in_cloud: runInCloud,
      hybrid_cloud_mode: hybridCloudMode,
      local_helper_skill_id: localHelperSkillId,
      local_helper_skill_name: (existingConfig as any)?.local_helper_skill_name ?? helperNameFromStore ?? null,
      local_helper_machine: localHelperMachine,
    };

    // Build the payload that save_agent_skill IPC handler expects
    // IMPORTANT: Only send fields that exist on GraphQL SkillUpdateInput.
    // Persist hybrid-cloud settings inside `config`.
    const skillPayload: Record<string, any> = {
      id: skillInfo.skillId || skillInfo.id,
      name: skillInfo.skillName || skillInfo.name || 'Unnamed Skill',
      description: skillInfo.description || '',
      version: skillInfo.version || '1.0.0',
      path: filePath || skillInfo.path || '',
      level: skillInfo.level || 'entry',
      config: updatedConfig,
      diagram: skillInfo.workFlow || {},
      tags: skillInfo.tags || [],
      source: 'ui',
    };

    console.log('[SKILL_IO][DB_SYNC] Syncing skill to DB:', skillPayload.name, 'id:', skillPayload.id);

    // For brand-new skills there is no DB record yet (no skill ID).
    // save_agent_skill requires an ID, so skip to avoid "Skill ID is required" error.
    // The backend will create the DB entry on the next sync_skill_from_file call.
    if (!skillPayload.id) {
      console.log('[SKILL_IO][DB_SYNC] No skill ID — skipping save_agent_skill for new skill');
      return;
    }

    const resp = await api.saveAgentSkill(owner, skillPayload);

    if (resp && resp.success) {
      console.log('[SKILL_IO][DB_SYNC] Skill saved to DB + cloud sync triggered');

      // Update the Skills page store so the list reflects changes immediately
      const store = useSkillStore.getState();
      const skillId = String((resp as any).data?.skill_id || skillPayload.id);
      const storeItem = {
        id: skillId,
        name: skillPayload.name,
        owner,
        description: skillPayload.description,
        version: skillPayload.version,
        path: skillPayload.path,
        level: skillPayload.level,
        config: skillPayload.config,
        diagram: skillPayload.diagram,
        tags: skillPayload.tags,
        source: 'ui' as const,
        status: 'active',
      };

      const existing = store.items.find((s) => String(s.id) === skillId);
      if (existing) {
        store.updateItem(skillId, storeItem);
        console.log('[SKILL_IO][DB_SYNC] Updated existing skill in store:', skillId);
      } else {
        store.addItem(storeItem as any);
        console.log('[SKILL_IO][DB_SYNC] Added new skill to store:', skillId);
      }
    } else {
      console.warn('[SKILL_IO][DB_SYNC] saveAgentSkill failed:', resp?.error);
    }
  } catch (e) {
    // Non-fatal: disk save already succeeded
    console.warn('[SKILL_IO][DB_SYNC] Error syncing skill to DB (non-fatal):', e);
  }
}

export const Save = ({ disabled }: SaveProps) => {
  const { t } = useTranslation('skillEditor');
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const dataMappingJson = useSkillInfoStore((state) => state.dataMappingJson);
  const dataMappingDirty = useSkillInfoStore((state) => state.dataMappingDirty);
  const setDataMappingJson = useSkillInfoStore((state) => state.setDataMappingJson);
  const setDataMappingDirty = useSkillInfoStore((state) => state.setDataMappingDirty);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const username = useUserStore((state) => state.username);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);
  const { isFlipped } = useNodeFlipStore();
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const localHelperSkillId = useSkillInfoStore((state) => state.localHelperSkillId);
  const localHelperMachine = useSkillInfoStore((state) => state.localHelperMachine);
  const localHelperSkillName = (() => {
    try {
      if (!localHelperSkillId || typeof localHelperSkillId !== 'string') return null;
      if (!localHelperSkillId.startsWith('skill_')) return String(localHelperSkillId);
      const store = useSkillStore.getState();
      const found = store.items.find((s: any) => String(s.id) === String(localHelperSkillId));
      return found?.name || null;
    } catch {
      return null;
    }
  })();

  const handleSave = useCallback(async () => {
    if (!skillInfo) return;

    try {
      // 1. Get and prepare diagram
      const diagram = document.toJSON();
      prepareDiagramForSave(diagram, isFlipped);

      // 2. Prepare sanitized copy for file persistence
      const sanitizedDiagram = JSON.parse(JSON.stringify(diagram));
      sanitizeNodeApiKeys(sanitizedDiagram?.nodes);

      // 3. Extract config nodes and create updated skillInfo
      const configNodes = extractConfigNodes(diagram);
      const updatedSkillInfo = {
        ...skillInfo,
        workFlow: diagram,
        lastModified: new Date().toISOString(),
        schemaVersion: CURRENT_SCHEMA_VERSION,  // Always save with current workflow schema version
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        run_in_cloud: runInCloud,
        hybrid_cloud_mode: hybridCloudMode,
        local_helper_skill_id: localHelperSkillId,
        local_helper_skill_name: localHelperSkillName,
        local_helper_machine: localHelperMachine,
        config: {
          ...(skillInfo as any)?.config,
          run_in_cloud: runInCloud,
          hybrid_cloud_mode: hybridCloudMode,
          local_helper_skill_id: localHelperSkillId,
          local_helper_skill_name: (skillInfo as any)?.config?.local_helper_skill_name ?? localHelperSkillName,
          local_helper_machine: localHelperMachine,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as any;

      const skillInfoForSave = { ...updatedSkillInfo, workFlow: sanitizedDiagram } as any;
      sanitizeApiKeysDeep(skillInfoForSave);

      let dataMappingForSave: string | null = null;
      if (dataMappingDirty && dataMappingJson) {
        try {
          const parsed = JSON.parse(dataMappingJson);
          dataMappingForSave = JSON.stringify(parsed, null, 2);
        } catch (e) {
          console.error('[Save] data_mapping.json invalid', e);
          try { Toast.error({ content: t('save.invalidMapping') }); } catch {}
          return;
        }
      } else {
        const mappingObj = buildDataMappingFromState(updatedSkillInfo, diagram);
        dataMappingForSave = JSON.stringify(mappingObj, null, 2);
        setDataMappingJson(dataMappingForSave, false);
        setDataMappingDirty(false);
      }

      // 4. Handle skill rename if name changed
      let effectivePath = currentFilePath || null;
      try {
        if (effectivePath) {
          const norm = effectivePath.replace(/\\/g, '/');
          const m = norm.match(/\/([^\/]+)_skill\/diagram_dir\//);
          const oldBase = m?.[1] || '';
          const proposedBase = String((updatedSkillInfo as any)?.skillName || '').replace(/_skill$/i, '').trim();

          if (oldBase && proposedBase && oldBase !== proposedBase) {
            const api = IPCAPI.getInstance();
            const resp = await api.renameSkill(oldBase, proposedBase);
            if (resp.success && resp.data?.skillRoot) {
              const newRoot: string = String(resp.data.skillRoot).replace(/\\/g, '/');
              effectivePath = `${newRoot}/diagram_dir/${proposedBase}_skill.json`;
              setCurrentFilePath(effectivePath);
            }
          }
        }
      } catch (e) {
        console.warn('[Save] rename flow failed or skipped', e);
      }

      let bundleJsonForSave: string | null = null;
      if (detectPlatform() === 'web') {
        saveActiveSheetDoc(diagram);
        const bundle = getAllSheets();
        bundleJsonForSave = buildBundleJsonForSave(bundle);
      }

      // 5. Save the file
      const saveResult = await saveFile(
        skillInfoForSave,
        username || undefined,
        effectivePath,
        dataMappingForSave,
        bundleJsonForSave
      );

      if (saveResult && !saveResult.cancelled) {
        const finalPath = saveResult.filePath || effectivePath || '';
        const derivedName = deriveSkillNameFromPath(finalPath, updatedSkillInfo.skillName);
        const finalSkillInfo = { ...updatedSkillInfo, skillName: derivedName } as any;

        setSkillInfo(finalSkillInfo);
        setHasUnsavedChanges(false);

        if (saveResult.filePath && saveResult.filePath !== currentFilePath) {
          setCurrentFilePath(saveResult.filePath);
        }

        const mappingPath = deriveDataMappingPath(finalPath, finalSkillInfo.skillName);
        try { useSkillInfoStore.getState().setDataMappingPath(mappingPath); } catch {}

        if (finalPath) {
          addRecentFile(createRecentFile(finalPath, finalSkillInfo.skillName));
        }

        console.log('[SKILL_IO][SAVE_DONE]');
        try { Toast.success({ content: t('save.saved') }); } catch {}

        // Sync to local DB + cloud DB and update Skills page store
        await syncSkillToDBAndStore(finalSkillInfo, finalPath, username);

        // 6. Save bundle (web mode batch already handled)
        if (detectPlatform() !== 'web') {
          const bundlePath = deriveBundlePath(finalPath, finalSkillInfo.skillName);
          await saveBundleFile(bundlePath, diagram, saveActiveSheetDoc, getAllSheets, t);
        }
      }
    } catch (error) {
      console.error('Failed to save skill:', error);
    }
  }, [
    skillInfo,
    username,
    document,
    currentFilePath,
    setSkillInfo,
    setCurrentFilePath,
    setHasUnsavedChanges,
    isFlipped,
    addRecentFile,
    getAllSheets,
    saveActiveSheetDoc,
    dataMappingJson,
    dataMappingDirty,
    setDataMappingJson,
    setDataMappingDirty,
    username,
    runInCloud,
    hybridCloudMode,
    localHelperSkillId,
    localHelperMachine,
  ]);

  return (
    <Tooltip content={t('toolbar.save')}>
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconSaveColored size={18} />}
        disabled={disabled}
        onClick={handleSave}
      />
    </Tooltip>
  );
};

export const SaveAs = ({ disabled }: SaveProps) => {
  const { t } = useTranslation('skillEditor');
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const dataMappingJson = useSkillInfoStore((state) => state.dataMappingJson);
  const dataMappingDirty = useSkillInfoStore((state) => state.dataMappingDirty);
  const setDataMappingJson = useSkillInfoStore((state) => state.setDataMappingJson);
  const setDataMappingDirty = useSkillInfoStore((state) => state.setDataMappingDirty);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);
  const { isFlipped } = useNodeFlipStore();
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const localHelperSkillId = useSkillInfoStore((state) => state.localHelperSkillId);
  const localHelperMachine = useSkillInfoStore((state) => state.localHelperMachine);
  const username = useUserStore((state) => state.username);

  const handleSaveAs = useCallback(async () => {
    if (!skillInfo) {
      Toast.warning({ content: t('saveAs.noSkill') });
      return;
    }

    try {
      // 1. Get and prepare diagram first
      const diagram = document.toJSON();
      prepareDiagramForSave(diagram, isFlipped);

      // 2. Prepare sanitized copy for file persistence
      const sanitizedDiagram = JSON.parse(JSON.stringify(diagram));
      sanitizeNodeApiKeys(sanitizedDiagram?.nodes);

      // 3. Extract config nodes
      const configNodes = extractConfigNodes(diagram);

      // 4. Determine save target (web uses modal input, desktop uses native dialog)
      let selectedPath: string | null = null;
      let newSkillName = '';

      if (detectPlatform() === 'web') {
        const requestedName = await new Promise<string | null>((resolve) => {
          let inputValue = '';
          let modalInstance: ReturnType<typeof Modal.confirm> | null = null;

          modalInstance = Modal.confirm({
            title: t('saveAs.title'),
            content: (
              <div style={{ marginTop: 16 }}>
                <p style={{ marginBottom: 8 }}>{t('saveAs.nameLabel')}</p>
                <Input
                  placeholder={t('saveAs.namePlaceholder')}
                  autoFocus
                  onChange={(value) => { inputValue = value; }}
                  onEnterPress={() => {
                    if (inputValue.trim()) {
                      modalInstance?.destroy();
                      resolve(inputValue.trim());
                    }
                  }}
                />
              </div>
            ),
            okText: t('saveAs.okText'),
            cancelText: t('saveAs.cancelText'),
            onOk: () => {
              modalInstance?.destroy();
              resolve(inputValue.trim() || null);
            },
            onCancel: () => {
              modalInstance?.destroy();
              resolve(null);
            },
          });
        });

        if (!requestedName) {
          console.log('[SAVEAS] User cancelled save-as modal');
          return;
        }

        newSkillName = requestedName.endsWith('_skill')
          ? requestedName.slice(0, -6)
          : requestedName;

        try {
          const exists = await ipcApi.checkSkillExists(newSkillName);
          if (exists?.data?.exists) {
            Modal.warning({
              title: t('saveAs.alreadyExistsTitle'),
              content: t('saveAs.alreadyExistsContent', { name: newSkillName }),
            });
            return;
          }
        } catch (e) {
          console.warn('[SAVEAS] Failed to check skill existence:', e);
        }

        selectedPath = buildWebSkillPath(newSkillName, username);
      } else {
        const ipcApi = IPCAPI.getInstance();
        let currentName = (skillInfo as any).skillName || 'untitled';
        if (currentName.endsWith('_skill')) {
          currentName = currentName.slice(0, -6);
        }
        const defaultFilename = `${currentName}.json`;

        const dialogResult = await ipcApi.showSaveDialog(defaultFilename, [
          { name: 'Skill Files', extensions: ['json'] }
        ]);

        if (!dialogResult.success || !dialogResult.data?.filePath) {
          console.log('[SAVEAS] User cancelled save dialog');
          return;
        }

        selectedPath = dialogResult.data.filePath;
        console.log('[SAVEAS] User selected path:', selectedPath);

        const fileName = selectedPath.split('/').pop() || '';
        newSkillName = fileName
          .replace(/\.json$/i, '')
          .replace(/_skill$/i, '');

        if (!newSkillName) {
          newSkillName = (skillInfo as any).skillName || 'untitled';
        }
      }

      console.log('[SAVEAS] Extracted skill name from path:', newSkillName);

      // 6. Create updated skillInfo with new name
      const updatedSkillInfo = {
        ...skillInfo,
        skillName: newSkillName,
        workFlow: sanitizedDiagram,
        lastModified: new Date().toISOString(),
        schemaVersion: CURRENT_SCHEMA_VERSION,  // Always save with current workflow schema version
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        run_in_cloud: runInCloud,
        hybrid_cloud_mode: hybridCloudMode,
        local_helper_skill_id: localHelperSkillId,
        local_helper_machine: localHelperMachine,
        config: {
          ...(skillInfo as any)?.config,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as SkillInfo;

      sanitizeApiKeysDeep(updatedSkillInfo);

      let dataMappingForSave: string | null = null;
      if (dataMappingDirty && dataMappingJson) {
        try {
          const parsed = JSON.parse(dataMappingJson);
          dataMappingForSave = JSON.stringify(parsed, null, 2);
        } catch (e) {
          console.error('[SaveAs] data_mapping.json invalid', e);
          Toast.error({ content: t('save.invalidMapping') });
          return;
        }
      } else {
        const mappingObj = buildDataMappingFromState(updatedSkillInfo, diagram);
        dataMappingForSave = JSON.stringify(mappingObj, null, 2);
        setDataMappingJson(dataMappingForSave, false);
        setDataMappingDirty(false);
      }

      // 7. Prepare bundle data
      saveActiveSheetDoc(diagram);
      const bundle = getAllSheets();

      // 8. Save to new location
      let finalDiagramPath: string;
      if (!selectedPath) {
        throw new Error('Save As path is missing');
      }

      if (detectPlatform() === 'web') {
        finalDiagramPath = selectedPath;
        const mappingPath = dataMappingForSave ? deriveDataMappingPath(finalDiagramPath, newSkillName) : null;
        const bundlePath = deriveBundlePath(finalDiagramPath, newSkillName);
        const bundleJsonForSave = buildBundleJsonForSave(bundle);

        const batch = [
          { filePath: finalDiagramPath, content: JSON.stringify(updatedSkillInfo, null, 2) },
          ...(dataMappingForSave && mappingPath ? [{ filePath: mappingPath, content: dataMappingForSave }] : []),
          { filePath: bundlePath, content: bundleJsonForSave },
        ];

        await ipcApi.writeSkillFile(batch);
      } else {
        const ipcApi = IPCAPI.getInstance();
        const targetDir = selectedPath.replace(/\/[^/]+$/, '');

        if (currentFilePath) {
          const copyResult = await ipcApi.copySkillTo(
            currentFilePath,
            newSkillName,
            updatedSkillInfo,
            bundle,
            targetDir
          );

          if (copyResult.success && copyResult.data) {
            finalDiagramPath = (copyResult.data as any).diagramPath;
            if (dataMappingForSave) {
              const mappingPath = deriveDataMappingPath(finalDiagramPath, newSkillName);
              try {
                await ipcApi.writeSkillFile({ filePath: mappingPath, content: dataMappingForSave });
              } catch (e) {
                console.warn('[SAVEAS] Failed to save data_mapping.json', e);
              }
            }
          } else {
            const errorMsg = (copyResult.error as any)?.message || 'Unknown error';
            console.error('[SAVEAS] Copy failed:', errorMsg);
            Toast.error({ content: `Save As failed: ${errorMsg}` });
            return;
          }
        } else {
          finalDiagramPath = selectedPath;
          await ipcApi.writeSkillFile({ filePath: selectedPath, content: JSON.stringify(updatedSkillInfo, null, 2) });
          const bundlePath = selectedPath.replace(/_skill\.json$/i, '_skill_bundle.json').replace(/\.json$/i, '_bundle.json');
          await ipcApi.writeSkillFile({ filePath: bundlePath, content: JSON.stringify(bundle, null, 2) });
          if (dataMappingForSave) {
            const mappingPath = deriveDataMappingPath(selectedPath, newSkillName);
            await ipcApi.writeSkillFile({ filePath: mappingPath, content: dataMappingForSave });
          }
        }
      }

      // 9. Update in-memory state
      const finalSkillInfo = {
        ...skillInfo,
        skillName: newSkillName,
        workFlow: diagram,  // Keep original diagram in memory
        lastModified: new Date().toISOString(),
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        run_in_cloud: runInCloud,
        hybrid_cloud_mode: hybridCloudMode,
        local_helper_skill_id: localHelperSkillId,
        local_helper_machine: localHelperMachine,
        config: {
          ...(skillInfo as any)?.config,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as any;

      setSkillInfo(finalSkillInfo);
      setCurrentFilePath(finalDiagramPath);
      try { useSkillInfoStore.getState().setDataMappingPath(deriveDataMappingPath(finalDiagramPath, newSkillName)); } catch {}
      setHasUnsavedChanges(false);
      addRecentFile(createRecentFile(finalDiagramPath, newSkillName));

      console.log('[SKILL_IO][SAVEAS_DONE]', { finalDiagramPath, newSkillName });
      Toast.success({ content: t('saveAs.savedAs', { name: newSkillName }) });

      // Sync to local DB + cloud DB and update Skills page store
      await syncSkillToDBAndStore(finalSkillInfo, finalDiagramPath, username);
      
    } catch (error) {
      console.error('Failed to save as:', error);
      Toast.error({ content: t('saveAs.saveFailed', { error: String(error) }) });
    }
  }, [
    skillInfo,
    currentFilePath,
    document,
    setSkillInfo,
    setCurrentFilePath,
    setHasUnsavedChanges,
    isFlipped,
    addRecentFile,
    getAllSheets,
    saveActiveSheetDoc,
    dataMappingJson,
    dataMappingDirty,
    setDataMappingJson,
    setDataMappingDirty,
  ]);

  return (
    <Tooltip content={t('toolbar.saveAs')}>
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconSaveAsColored size={18} />}
        disabled={disabled}
        onClick={handleSaveAs}
      />
    </Tooltip>
  );
};
