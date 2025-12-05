import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';

import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconSaveColored, IconSaveAsColored } from './colored-icons';
import { useUserStore } from '../../../../stores/userStore';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { SkillInfo } from '../../typings/skill-info';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { IPCWCClient } from '@/services/ipc/ipcWCClient';
import { useSheetsStore } from '../../stores/sheets-store';
import { saveSheetsBundleToPath } from '../../services/sheets-persistence';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { sanitizeNodeApiKeys, sanitizeApiKeysDeep } from '../../utils/sanitize-utils';
import { IPCAPI } from '../../../../services/ipc/api';

// ============================================================================
// Common utilities for Save and SaveAs
// ============================================================================

/**
 * Prepare diagram for saving: handle flip states and remove breakpoints
 */
function prepareDiagramForSave(diagram: any, isFlipped: (id: string) => boolean): void {
  diagram.nodes.forEach((node: any) => {
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

/**
 * Save bundle alongside skill file
 */
async function saveBundleFile(
  bundlePath: string,
  diagram: any,
  saveActiveSheetDoc: (doc: any) => void,
  getAllSheets: () => any
): Promise<void> {
  try {
    saveActiveSheetDoc(diagram);
    const bundle = getAllSheets();
    console.log('[SKILL_IO][BUNDLE_SAVE_ATTEMPT]', { path: bundlePath, sheetsCount: bundle.sheets.length });
    const bundleRes = await saveSheetsBundleToPath(bundlePath, bundle);
    console.log('[SKILL_IO][BUNDLE_SAVE_RESULT]', { path: bundlePath, success: true, mode: bundleRes.mode });
    const msg = bundleRes.mode === 'ipc'
      ? `Bundle saved: ${bundleRes.filePath || bundlePath}`
      : 'Bundle downloaded.';
    try { Toast.success({ content: msg }); } catch {}
  } catch (e) {
    console.warn('[SKILL_IO][BUNDLE_SAVE_ERROR]', (e as Error).message);
    try { Toast.error({ content: 'Bundle save failed.' }); } catch {}
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

export async function saveFile(dataToSave: SkillInfo, _username?: string, currentFilePath?: string | null) {
  try {
    console.log('--- Debug Save: Data to Save ---', dataToSave);
    const jsonString = JSON.stringify(dataToSave, null, 2);
    // console.log('--- Debug Save: Final JSON String ---', jsonString);

    if (ENABLE_LOCAL_DOWNLOAD) {
      // Try IPC first regardless of platform flags
      try {
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        console.log('[SKILL_IO][FRONTEND][IPC_ATTEMPT] showSaveDialog');
        let filePath = currentFilePath;
        if (!filePath) {
          // 问题2FIX: 不要在Default文件名中Add _skill 后缀
          // UserInput的Name就是文件夹Name，Backend会自动Add _skill 后缀到文件夹
          const fileName = (dataToSave.skillName || 'untitled') + '.json';
          console.log('[SKILL_IO][FRONTEND][DEFAULT_FILENAME]', fileName);
          const dialogResponse = await ipcApi.showSaveDialog(fileName, [
            { name: 'Skill Files', extensions: ['json'] },
            { name: 'All Files', extensions: ['*'] }
          ]);
          if (dialogResponse.success && dialogResponse.data && !dialogResponse.data.cancelled) {
            filePath = (dialogResponse.data as any).filePath || (dialogResponse.data as any).filePaths?.[0];
          } else {
            console.log('Save operation was cancelled by user');
            return { cancelled: true };
          }
        }
        // Enforce _skill.json suffix
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
          const writeResponse = await ipcApi.writeSkillFile(filePath, jsonString);
          if (writeResponse.success) {
            console.log('[SKILL_IO][FRONTEND][MAIN_SAVE_OK]', filePath);
            // 需求4: 使用Backend返回的 skillName UpdateFrontend
            const savedSkillName = writeResponse.data?.skillName;
            console.log('[SKILL_IO][FRONTEND][SKILL_NAME_FROM_BACKEND]', savedSkillName);
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

export const Save = ({ disabled }: SaveProps) => {
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const username = useUserStore((state) => state.username);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);
  const { isFlipped } = useNodeFlipStore();

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
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        config: {
          ...(skillInfo as any)?.config,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as any;

      const skillInfoForSave = { ...updatedSkillInfo, workFlow: sanitizedDiagram } as any;
      sanitizeApiKeysDeep(skillInfoForSave);

      // 4. Handle skill rename if name changed
      let effectivePath = currentFilePath || null;
      try {
        if (effectivePath) {
          const norm = effectivePath.replace(/\\/g, '/');
          const m = norm.match(/\/([^\/]+)_skill\/diagram_dir\//);
          const oldBase = m?.[1] || '';
          const proposedBase = String((updatedSkillInfo as any)?.skillName || '').replace(/_skill$/i, '').trim();

          if (oldBase && proposedBase && oldBase !== proposedBase) {
            const resp: any = await IPCWCClient.getInstance().sendRequest('skills.rename', {
              oldName: oldBase,
              newName: proposedBase,
            });
            if (resp?.status === 'success' && resp.result?.skillRoot) {
              const newRoot: string = String(resp.result.skillRoot).replace(/\\/g, '/');
              effectivePath = `${newRoot}/diagram_dir/${proposedBase}_skill.json`;
              setCurrentFilePath(effectivePath);
            }
          }
        }
      } catch (e) {
        console.warn('[Save] rename flow failed or skipped', e);
      }

      // 5. Save the file
      const saveResult = await saveFile(skillInfoForSave, username || undefined, effectivePath);

      if (saveResult && !saveResult.cancelled) {
        const finalPath = saveResult.filePath || effectivePath || '';
        const derivedName = deriveSkillNameFromPath(finalPath, updatedSkillInfo.skillName);
        const finalSkillInfo = { ...updatedSkillInfo, skillName: derivedName } as any;

        setSkillInfo(finalSkillInfo);
        setHasUnsavedChanges(false);

        if (saveResult.filePath && saveResult.filePath !== currentFilePath) {
          setCurrentFilePath(saveResult.filePath);
        }

        if (finalPath) {
          addRecentFile(createRecentFile(finalPath, finalSkillInfo.skillName));
        }

        console.log('[SKILL_IO][SAVE_DONE]');
        try { Toast.success({ content: 'Skill saved.' }); } catch {}

        // 6. Save bundle
        const bundlePath = deriveBundlePath(finalPath, finalSkillInfo.skillName);
        await saveBundleFile(bundlePath, diagram, saveActiveSheetDoc, getAllSheets);
      }
    } catch (error) {
      console.error('Failed to save skill:', error);
    }
  }, [skillInfo, username, document, currentFilePath, setSkillInfo, setCurrentFilePath, setHasUnsavedChanges, isFlipped, addRecentFile, getAllSheets, saveActiveSheetDoc]);

  return (
    <Tooltip content="Save">
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
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);
  const { isFlipped } = useNodeFlipStore();

  const handleSaveAs = useCallback(async () => {
    if (!skillInfo) {
      Toast.warning({ content: 'No skill to save.' });
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

      // 4. Show system save dialog to let user choose path and filename
      const ipcApi = IPCAPI.getInstance();
      let currentName = (skillInfo as any).skillName || 'untitled';
      // Remove _skill suffix if present (skillName should not have it)
      if (currentName.endsWith('_skill')) {
        currentName = currentName.slice(0, -6);
      }
      // Default filename uses base name without _skill suffix
      // User can modify it in the dialog, and we'll extract the name from the final path
      const defaultFilename = `${currentName}.json`;
      
      const dialogResult = await ipcApi.showSaveDialog(defaultFilename, [
        { name: 'Skill Files', extensions: ['json'] }
      ]);

      if (!dialogResult.success || !dialogResult.data?.filePath) {
        console.log('[SAVEAS] User cancelled save dialog');
        return;
      }

      const selectedPath = dialogResult.data.filePath;
      console.log('[SAVEAS] User selected path:', selectedPath);

      // 5. Extract skill name from the selected file path
      // User may have changed the filename in the save dialog
      const fileName = selectedPath.split('/').pop() || '';
      let newSkillName = fileName
        .replace(/\.json$/i, '')           // Remove .json extension
        .replace(/_skill$/i, '');          // Remove _skill suffix
      
      // Fallback to original name if extraction failed
      if (!newSkillName) {
        newSkillName = (skillInfo as any).skillName || 'untitled';
      }
      
      console.log('[SAVEAS] Extracted skill name from path:', newSkillName);

      // 6. Create updated skillInfo with new name
      const updatedSkillInfo = {
        ...skillInfo,
        skillName: newSkillName,
        workFlow: sanitizedDiagram,
        lastModified: new Date().toISOString(),
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        config: {
          ...(skillInfo as any)?.config,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as SkillInfo;

      sanitizeApiKeysDeep(updatedSkillInfo);

      // 7. Prepare bundle data
      saveActiveSheetDoc(diagram);
      const bundle = getAllSheets();

      // 8. Copy skill directory to new location
      // Backend will check if destination already exists
      let finalDiagramPath: string;
      
      // Extract target directory from selected path
      const targetDir = selectedPath.replace(/\/[^/]+$/, '');  // Remove filename to get directory
      
      if (currentFilePath) {
        // Use copySkillTo to copy entire skill directory
        const copyResult = await ipcApi.copySkillTo(
          currentFilePath,
          newSkillName,
          updatedSkillInfo,
          bundle,
          targetDir
        );

        if (copyResult.success && copyResult.data) {
          finalDiagramPath = (copyResult.data as any).diagramPath;
        } else {
          const errorMsg = (copyResult.error as any)?.message || 'Unknown error';
          console.error('[SAVEAS] Copy failed:', errorMsg);
          Toast.error({ content: `Save As failed: ${errorMsg}` });
          return;
        }
      } else {
        // No current path - just save to selected location
        finalDiagramPath = selectedPath;
        await ipcApi.writeSkillFile(selectedPath, JSON.stringify(updatedSkillInfo, null, 2));
        
        // Also save bundle
        const bundlePath = selectedPath.replace(/_skill\.json$/i, '_skill_bundle.json').replace(/\.json$/i, '_bundle.json');
        await ipcApi.writeSkillFile(bundlePath, JSON.stringify(bundle, null, 2));
      }

      // 9. Update in-memory state
      const finalSkillInfo = {
        ...skillInfo,
        skillName: newSkillName,
        workFlow: diagram,  // Keep original diagram in memory
        lastModified: new Date().toISOString(),
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',
        config: {
          ...(skillInfo as any)?.config,
          nodes: { ...((skillInfo as any)?.config?.nodes || {}), ...configNodes },
        },
      } as any;

      setSkillInfo(finalSkillInfo);
      setCurrentFilePath(finalDiagramPath);
      setHasUnsavedChanges(false);
      addRecentFile(createRecentFile(finalDiagramPath, newSkillName));

      console.log('[SKILL_IO][SAVEAS_DONE]', { finalDiagramPath, newSkillName });
      Toast.success({ content: `Skill saved as "${newSkillName}"` });
      
    } catch (error) {
      console.error('Failed to save as:', error);
      Toast.error({ content: `Save As failed: ${error}` });
    }
  }, [skillInfo, currentFilePath, document, setSkillInfo, setCurrentFilePath, setHasUnsavedChanges, isFlipped, addRecentFile, getAllSheets, saveActiveSheetDoc]);

  return (
    <Tooltip content="Save As">
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
