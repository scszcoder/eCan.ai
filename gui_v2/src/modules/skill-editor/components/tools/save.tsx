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
import { saveSheetsBundleToPath, saveSheetsBundle } from '../../services/sheets-persistence';
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

export async function saveFile(dataToSave: SkillInfo, username?: string, currentFilePath?: string | null) {
  try {
    console.log('--- Debug Save: Data to Save ---', dataToSave);
    const jsonString = JSON.stringify(dataToSave, null, 2);
    console.log('--- Debug Save: Final JSON String ---', jsonString);

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

  const handleSave = useCallback(async () => {
    if (!skillInfo) return;

    try {
      // 1. Get the latest diagram state
      const diagram = document.toJSON();

      // 2. Ensure breakpoints are NOT persisted: strip any break_point flags
      // 3. SECURITY: Strip API keys from LLM and browser_automation nodes
      diagram.nodes.forEach((node: any) => {
        if (node?.data?.break_point) {
          delete node.data.break_point;
        }
        
        // Strip API keys from LLM nodes
        if (node?.type === 'llm' && node?.data?.inputsValues) {
          const inputs = node.data.inputsValues;
          if (inputs.apiKey?.content) {
            console.log(`[Save] Stripping API key from LLM node: ${node.data.name || node.id}`);
            inputs.apiKey.content = '';
          }
        }
        
        // Strip API keys from browser_automation nodes
        if (node?.type === 'browser-automation' && node?.data?.inputsValues) {
          const inputs = node.data.inputsValues;
          if (inputs.apiKey?.content) {
            console.log(`[Save] Stripping API key from browser_automation node: ${node.data.name || node.id}`);
            inputs.apiKey.content = '';
          }
        }
      });

      // 3. Promote node-level mapping_rules into top-level config.nodes for backend runtime
      const configNodes: Record<string, any> = {};
      try {
        for (const n of diagram.nodes || []) {
          const data = (n && n.data) || {};
          if (data && data.mapping_rules) {
            const key = (data.name || n.id || '').toString();
            if (key) {
              configNodes[key] = { ...(configNodes[key] || {}), mapping_rules: data.mapping_rules };
            }
          }
        }
      } catch (e) {
        console.warn('[Save] mapping_rules promotion skipped', e);
      }

      // 4. Build data_mapping.json structure
      const dataMappingJson: any = {
        developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
        released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
        node_transfers: {},
        event_routing: {}
      };

      try {
        // Extract skill-level mappings from START node (stored in config.skill_mapping)
        const skillMapping = (skillInfo as any)?.config?.skill_mapping;
        if (skillMapping) {
          if (skillMapping.developing) {
            dataMappingJson.developing = skillMapping.developing;
          }
          if (skillMapping.released) {
            dataMappingJson.released = skillMapping.released;
          }
          if (skillMapping.event_routing) {
            dataMappingJson.event_routing = skillMapping.event_routing;
          }
        }
        
        // Extract node-to-node transfer mappings from other nodes (skip START node)
        for (const n of diagram.nodes || []) {
          const nodeData = n?.data || {};
          const nodeName = nodeData.name || n.id;
          const nodeType = nodeData.type || n.type;
          const nodeId = n.id;
          
          // Skip START node (already handled above)
          if (nodeType === 'start' || nodeType === 'event' || nodeId === 'start') {
            continue;
          }
          
          // If this node has mapping rules, add to node_transfers
          if (nodeData.mapping_rules) {
            dataMappingJson.node_transfers[nodeName] = nodeData.mapping_rules;
          }
        }
        
        console.log('[Save] Generated data_mapping.json:', dataMappingJson);
      } catch (e) {
        console.warn('[Save] data_mapping.json generation failed', e);
      }

      // 5. Create the updated skillInfo object, merging config nodes
      const updatedSkillInfo = {
        ...skillInfo,
        workFlow: diagram,
        lastModified: new Date().toISOString(),
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',  // Include backend runtime mode
        config: {
          ...(skillInfo as any)?.config,
          nodes: {
            ...((skillInfo as any)?.config?.nodes || {}),
            ...configNodes,
          },
        },
      } as any;

      // 4. If and only if user changed the base skill name, rename the underlying <name>_skill folder
      let effectivePath = currentFilePath || null;
      try {
        if (effectivePath) {
          // Expect path like .../<old>_skill/diagram_dir/<old>_skill.json
          const norm = effectivePath.replace(/\\/g, '/');
          const m = norm.match(/\/([^\/]+)_skill\/diagram_dir\//);
          const oldBase = m?.[1] || '';
          // Derive proposed new base from updatedSkillInfo, stripping any _skill suffix
          const proposedBase = String((updatedSkillInfo as any)?.skillName || '')
            .replace(/_skill$/i, '')
            .trim();

          // Only attempt rename when we have both names and they differ
          if (oldBase && proposedBase && oldBase !== proposedBase) {
            const resp: any = await IPCWCClient.getInstance().sendRequest('skills.rename', {
              oldName: oldBase,
              newName: proposedBase,
            });
            if (resp?.status === 'success' && resp.result?.skillRoot) {
              const newRoot: string = String(resp.result.skillRoot).replace(/\\/g, '/');
              // Point to new diagram json under renamed root (backend appends _skill)
              effectivePath = `${newRoot}/diagram_dir/${proposedBase}_skill.json`;
              setCurrentFilePath(effectivePath);
            }
          }
        }
      } catch (e) {
        console.warn('[Save] rename flow failed or skipped', e);
      }

      // 5. Save the file with platform-aware handling
      const saveResult = await saveFile(updatedSkillInfo, username || undefined, effectivePath);

      if (saveResult && !saveResult.cancelled) {
        // Derive skillName from saved path (folder <name>_skill) to avoid backend mismatch
        const finalPath = saveResult.filePath || effectivePath || '';
        let derivedName = updatedSkillInfo.skillName;
        try {
          if (finalPath) {
            const norm = String(finalPath).replace(/\\/g, '/');
            const parts = norm.split('/');
            const idx = parts.lastIndexOf('diagram_dir');
            if (idx > 0) {
              const folder = parts[idx - 1];
              derivedName = (folder?.replace(/_skill$/i, '') || derivedName) as string;
            } else {
              const base = (parts.pop() || '').replace(/\.json$/i, '');
              derivedName = base.replace(/_skill$/i, '') || derivedName;
            }
          }
        } catch {}

        // Update the skill info store with path-derived name
        const finalSkillInfo = { ...updatedSkillInfo, skillName: derivedName } as any;
        setSkillInfo(finalSkillInfo);
        setHasUnsavedChanges(false);

        // Update file path if we got a new one (from Save As dialog)
        if (saveResult.filePath && saveResult.filePath !== currentFilePath) {
          setCurrentFilePath(saveResult.filePath);
        }

        // Add to recent files when saving (update last opened time)
        const finalFilePath = saveResult.filePath || effectivePath;
        if (finalFilePath) {
          addRecentFile(createRecentFile(finalFilePath, (finalSkillInfo as any).skillName));
        }

        console.log('[SKILL_IO][FRONTEND][MAIN_SAVE_DONE]');
        try { Toast.success({ content: 'Skill saved.' }); } catch {}

        // Save data_mapping.json alongside skill JSON
        try {
          const finalFilePath = saveResult.filePath || effectivePath;
          if (finalFilePath) {
            // Determine mapping file path: replace _skill.json with _data_mapping.json
            let mappingPath = finalFilePath;
            if (/_skill\.json$/i.test(mappingPath)) {
              mappingPath = mappingPath.replace(/_skill\.json$/i, '_data_mapping.json');
            } else if (/\.json$/i.test(mappingPath)) {
              mappingPath = mappingPath.replace(/\.json$/i, '_data_mapping.json');
            } else {
              mappingPath = `${mappingPath}_data_mapping.json`;
            }
            
            const mappingJsonString = JSON.stringify(dataMappingJson, null, 2);
            console.log('[SKILL_IO][MAPPING_SAVE_ATTEMPT]', { path: mappingPath });
            
            // Try IPC save first
            try {
              const { IPCAPI } = await import('../../../../services/ipc/api');
              const ipcApi = IPCAPI.getInstance();
              const writeResponse = await ipcApi.writeSkillFile(mappingPath, mappingJsonString);
              if (writeResponse.success) {
                console.log('[SKILL_IO][MAPPING_SAVE_OK]', mappingPath);
              } else {
                console.warn('[SKILL_IO][MAPPING_SAVE_ERROR]', writeResponse.error);
              }
            } catch (err) {
              console.warn('[SKILL_IO][MAPPING_IPC_ERROR]', err);
              // Web fallback: download
              const blob = new Blob([mappingJsonString], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = mappingPath.split('/').pop()?.split('\\').pop() || 'data_mapping.json';
              a.click();
              URL.revokeObjectURL(url);
              console.log('[SKILL_IO][MAPPING_SAVE_OK_DOWNLOAD]', a.download);
            }
          }
        } catch (e) {
          console.warn('[Save] data_mapping.json save failed', e);
        }

        // Also persist the multi-sheet bundle alongside the skill JSON (no extra prompts)
        try {
          // Persist current canvas into the active sheet before bundling
          saveActiveSheetDoc(diagram);
          const bundle = getAllSheets();
          // Derive bundle path/name: enforce *_skill_bundle.json next to *_skill.json
          let bundleTarget = 'skill_bundle.json';
          if (finalFilePath) {
            if (/_skill\.json$/i.test(finalFilePath)) {
              bundleTarget = finalFilePath.replace(/_skill\.json$/i, '_skill_bundle.json');
            } else if (/\.json$/i.test(finalFilePath)) {
              bundleTarget = finalFilePath.replace(/\.json$/i, '_skill_bundle.json');
            } else {
              bundleTarget = `${finalFilePath}_skill_bundle.json`;
            }
          } else if ((finalSkillInfo as any).skillName) {
            bundleTarget = `${(finalSkillInfo as any).skillName}_skill_bundle.json`;
          }
          console.log('[SKILL_IO][FRONTEND][BUNDLE_SAVE_ATTEMPT]', { path: bundleTarget, sheetsCount: bundle.sheets.length });
          const bundleRes = await saveSheetsBundleToPath(bundleTarget, bundle);
          console.log('[SKILL_IO][FRONTEND][BUNDLE_SAVE_RESULT]', { path: bundleTarget, success: true, mode: bundleRes.mode });
          try {
            const msg = bundleRes.mode === 'ipc'
              ? `Bundle saved: ${bundleRes.filePath || bundleTarget}`
              : 'Bundle downloaded.';
            Toast.success({ content: msg });
          } catch {}
        } catch (e) {
          console.warn('[SKILL_IO][FRONTEND][BUNDLE_SAVE_ERROR]', (e as Error).message);
          try { Toast.error({ content: 'Bundle save failed.' }); } catch {}
        }
      }
    } catch (error) {
      console.error('Failed to save skill:', error);
      // TODO: Show user-friendly error message
    }
  }, [skillInfo, username, document, currentFilePath, setSkillInfo, setCurrentFilePath, setHasUnsavedChanges]);

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
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const username = useUserStore((state) => state.username);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);

  const handleSaveAs = useCallback(async () => {
    if (!skillInfo) return;

    try {
      const diagram = document.toJSON();
      // Ensure breakpoints are NOT persisted in Save As as well
      diagram.nodes.forEach((node: any) => {
        if (node?.data?.break_point) {
          delete node.data.break_point;
        }
      });

      // Build data_mapping.json structure (same as Save)
      const dataMappingJson: any = {
        developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
        released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
        node_transfers: {},
        event_routing: {}
      };

      try {
        const skillMapping = (skillInfo as any)?.config?.skill_mapping;
        if (skillMapping) {
          if (skillMapping.developing) dataMappingJson.developing = skillMapping.developing;
          if (skillMapping.released) dataMappingJson.released = skillMapping.released;
          if (skillMapping.event_routing) dataMappingJson.event_routing = skillMapping.event_routing;
        }
        
        for (const n of diagram.nodes || []) {
          const nodeData = n?.data || {};
          const nodeName = nodeData.name || n.id;
          const nodeType = nodeData.type || n.type;
          const nodeId = n.id;
          
          if (nodeType === 'start' || nodeType === 'event' || nodeId === 'start') continue;
          if (nodeData.mapping_rules) {
            dataMappingJson.node_transfers[nodeName] = nodeData.mapping_rules;
          }
        }
      } catch (e) {
        console.warn('[SaveAs] data_mapping.json generation failed', e);
      }

      const updatedSkillInfo: SkillInfo = {
        ...skillInfo,
        workFlow: diagram,
        lastModified: new Date().toISOString(),
        mode: (skillInfo as any)?.mode ?? 'development',
        run_mode: (skillInfo as any)?.run_mode ?? 'developing',  // Include backend runtime mode
      } as SkillInfo;

      const saveResult = await saveFile(updatedSkillInfo, username || undefined, null);
      if (saveResult && !saveResult.cancelled) {
        setSkillInfo(updatedSkillInfo);
        setHasUnsavedChanges(false);
        if (saveResult.filePath) {
          setCurrentFilePath(saveResult.filePath);
          addRecentFile(createRecentFile(saveResult.filePath, updatedSkillInfo.skillName));
        }

        console.log('[SKILL_IO][FRONTEND][MAIN_SAVEAS_DONE]');
        try { Toast.success({ content: 'Skill saved as new file.' }); } catch {}

        // Save data_mapping.json alongside skill JSON
        try {
          const finalFilePath = saveResult.filePath || '';
          if (finalFilePath) {
            let mappingPath = finalFilePath;
            if (/_skill\.json$/i.test(mappingPath)) {
              mappingPath = mappingPath.replace(/_skill\.json$/i, '_data_mapping.json');
            } else if (/\.json$/i.test(mappingPath)) {
              mappingPath = mappingPath.replace(/\.json$/i, '_data_mapping.json');
            } else {
              mappingPath = `${mappingPath}_data_mapping.json`;
            }
            
            const mappingJsonString = JSON.stringify(dataMappingJson, null, 2);
            console.log('[SKILL_IO][MAPPING_SAVEAS_ATTEMPT]', { path: mappingPath });
            
            try {
              const { IPCAPI } = await import('../../../../services/ipc/api');
              const ipcApi = IPCAPI.getInstance();
              const writeResponse = await ipcApi.writeSkillFile(mappingPath, mappingJsonString);
              if (writeResponse.success) {
                console.log('[SKILL_IO][MAPPING_SAVEAS_OK]', mappingPath);
              }
            } catch (err) {
              console.warn('[SKILL_IO][MAPPING_SAVEAS_IPC_ERROR]', err);
              const blob = new Blob([mappingJsonString], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = mappingPath.split('/').pop()?.split('\\').pop() || 'data_mapping.json';
              a.click();
              URL.revokeObjectURL(url);
            }
          }
        } catch (e) {
          console.warn('[SaveAs] data_mapping.json save failed', e);
        }

        try {
          saveActiveSheetDoc(diagram);
          const bundle = getAllSheets();
          const finalFilePath = saveResult.filePath || '';
          let bundleTarget = 'skill_bundle.json';
          if (finalFilePath) {
            if (/_skill\.json$/i.test(finalFilePath)) {
              bundleTarget = finalFilePath.replace(/_skill\.json$/i, '_skill_bundle.json');
            } else if (/\.json$/i.test(finalFilePath)) {
              bundleTarget = finalFilePath.replace(/\.json$/i, '_skill_bundle.json');
            } else {
              bundleTarget = `${finalFilePath}_skill_bundle.json`;
            }
          } else if (updatedSkillInfo.skillName) {
            bundleTarget = `${updatedSkillInfo.skillName}_skill_bundle.json`;
          }
          console.log('[SKILL_IO][FRONTEND][BUNDLE_SAVE_ATTEMPT]', { path: bundleTarget, sheetsCount: bundle.sheets.length });
          const bundleRes = await saveSheetsBundleToPath(bundleTarget, bundle);
          console.log('[SKILL_IO][FRONTEND][BUNDLE_SAVE_RESULT]', { path: bundleTarget, success: true, mode: bundleRes.mode });
          try {
            const msg = bundleRes.mode === 'ipc'
              ? `Bundle saved: ${bundleRes.filePath || bundleTarget}`
              : 'Bundle downloaded.';
            Toast.success({ content: msg });
          } catch {}
        } catch (e) {
          console.warn('[SKILL_IO][FRONTEND][BUNDLE_SAVE_ERROR]', (e as Error).message);
          try { Toast.error({ content: 'Bundle save failed.' }); } catch {}
        }
      }
    } catch (error) {
      console.error('Failed to save as:', error);
    }
  }, [skillInfo, username, document, setSkillInfo, setCurrentFilePath, setHasUnsavedChanges]);

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
