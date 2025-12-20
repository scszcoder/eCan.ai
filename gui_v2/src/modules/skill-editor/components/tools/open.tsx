import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconOpenColored } from './colored-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { SkillInfo } from '../../typings/skill-info';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { SheetsBundle } from '../../services/sheets-persistence';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { loadSkillFile } from '../../services/skill-loader';
import { migrateBundle } from '../../services/schema-migration';

interface OpenProps {
  disabled?: boolean;
}

export const Open = ({ disabled }: OpenProps) => {
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const skillInfoFromStore = useSkillInfoStore((state) => state.skillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const setPreviewMode = useSkillInfoStore((state) => state.setPreviewMode);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const { setFlipped, clear: clearFlipStore } = useNodeFlipStore();

  const handleOpen = useCallback(async () => {
    // Always try IPC first, regardless of hasIPCSupport()
    // The function will detect if IPC is available at runtime
    try {
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        console.log('[SKILL_IO][FRONTEND][IPC_ATTEMPT] showOpenDialog');
        const dialogResponse = await ipcApi.showOpenDialog([
          { name: 'Skill Files', extensions: ['json'] },
          { name: 'All Files', extensions: ['*'] }
        ]);

        if (dialogResponse.success && dialogResponse.data && !dialogResponse.data.cancelled) {
          const filePath = (dialogResponse.data as any).filePaths?.[0] || (dialogResponse.data as any).filePath;
          // 需求2: GetBackend返回的 skillName（从文件夹Name提取）
          const skillNameFromBackend = (dialogResponse.data as any).skillName;
          if (!filePath) { console.warn('[Open] No filePath from dialog'); return; }
          console.log('[SKILL_IO][FRONTEND][SELECTED_MAIN_JSON]', filePath);
          console.log('[SKILL_IO][FRONTEND][SKILL_NAME_FROM_BACKEND]', skillNameFromBackend);
          try { Toast.info({ content: `Opening: ${skillNameFromBackend || String(filePath).split('\\').pop()}` }); } catch {}

          // Use unified skill loader (handles migration and auto-save automatically)
          const result = await loadSkillFile(filePath);
          console.log('[SKILL_IO][FRONTEND][LOAD_RESULT]', { success: result.success, migrated: result.migrated });

          if (result.success && result.skillInfo) {
            // Open explicitly exits preview mode
            setPreviewMode(false);
            const data = result.skillInfo;
            // skillName is already normalized by skill-loader.ts
            console.log('[SKILL_IO][FRONTEND][SKILL_NAME]', data.skillName);

            // Load bundle if available
            if (result.bundle) {
              loadBundle(result.bundle);
              console.log('[SKILL_IO][FRONTEND][BUNDLE_LOADED]', result.bundlePath);
            }

            const diagram = data.workFlow;
            if (diagram) {
              console.log('[Open] Loading skill diagram. Nodes=', Array.isArray(diagram.nodes) ? diagram.nodes.length : 'n/a');
              
              setSkillInfo(data);
              setCurrentFilePath(filePath);
              setHasUnsavedChanges(false);
              
              const breakpointIds = diagram.nodes
                .filter((node: any) => node.data?.break_point)
                .map((node: any) => node.id);
              setBreakpoints(breakpointIds);
              
              // Load diagram into editor (only if no bundle, bundle loading handles this)
              if (!result.bundle) {
                workflowDocument.clear();
                workflowDocument.fromJSON(diagram);
              }
              
              // Restore flip states from saved node data
              clearFlipStore();
              setTimeout(() => {
                diagram.nodes.forEach((node: any) => {
                  if (node?.data?.hFlip === true) {
                    console.log('[Open] Restoring hFlip state for node:', node.id);
                    setFlipped(node.id, true);
                    const loadedNode = workflowDocument.getNode(node.id) as any;
                    if (loadedNode) {
                      if (loadedNode.raw?.data) loadedNode.raw.data.hFlip = true;
                      if (loadedNode.json?.data) loadedNode.json.data.hFlip = true;
                      try {
                        const form = (loadedNode as any).form;
                        if (form?.patchValue) {
                          form.patchValue({ data: { ...form.state?.values?.data, hFlip: true } });
                        }
                      } catch {}
                      try { (loadedNode as any).update?.(); } catch {}
                    }
                  }
                });
              }, 100);
              
              workflowDocument.fitView && workflowDocument.fitView();
              addRecentFile(createRecentFile(filePath, data.skillName || 'Skill'));
            } else {
              // Fallback for older formats
              workflowDocument.clear();
              workflowDocument.fromJSON(data as any);
              clearFlipStore();
              if ((data as any).nodes) {
                (data as any).nodes.forEach((node: any) => {
                  if (node?.data?.hFlip === true) setFlipped(node.id, true);
                });
              }
              workflowDocument.fitView && workflowDocument.fitView();
              setSkillInfo(data);
              setCurrentFilePath(filePath);
              setHasUnsavedChanges(false);
            }
          } else {
            console.error('[Open] Failed to load file:', result.error);
          }
        } else {
          // Dialog was cancelled or failed, don't proceed to web fallback
          console.log('[SKILL_IO][FRONTEND][DIALOG_CANCELLED]');
        }
        return; // handled IPC path (both success and cancel)
    } catch (e) {
      console.warn('[SKILL_IO][FRONTEND][IPC_ERROR]', e);
      // Fall through to web fallback
    }

    // Web fallback path
    console.log('[SKILL_IO][FRONTEND][WEB_MODE_FALLBACK] Using browser FileReader flow');
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,application/json';
    input.style.display = 'none';

    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const raw = JSON.parse(event.target?.result as string);
            // Enforce filename matches skillName not applicable in web picker (no path), but if name provided in file meta, skip
            const isBundle = raw && typeof raw === 'object' && 'mainSheetId' in raw && Array.isArray(raw.sheets);
            if (isBundle) {
              const bundle = raw as SheetsBundle;
              // Apply migration (no auto-save in web mode)
              migrateBundle(bundle);
              loadBundle(bundle);
              // In web mode we don't have file path; use first sheet name or a generic label
              try {
                const firstName = (Array.isArray(bundle.sheets) && bundle.sheets[0]?.name) || 'Multi-sheet Skill';
                const current = skillInfoFromStore;
                if (current?.skillName !== firstName) {
                  setSkillInfo({ ...(current || { skillId: (current as any)?.skillId || '', skillName: firstName, version: '1.0.0', lastModified: new Date().toISOString(), workFlow: workflowDocument.toJSON() as any }), skillName: firstName });
                }
              } catch {}
              setCurrentFilePath(null);
              setHasUnsavedChanges(false);
              return;
            }
            const data = raw as SkillInfo;
            const diagram = data.workFlow;
            if (diagram) {
              setSkillInfo(data);
              setCurrentFilePath(null);
              setHasUnsavedChanges(false);
              const breakpointIds = diagram.nodes
                .filter((node: any) => node.data?.break_point)
                .map((node: any) => node.id);
              setBreakpoints(breakpointIds);
              workflowDocument.clear();
              workflowDocument.fromJSON(diagram);
              // Restore flip states from saved node data (web fallback)
              clearFlipStore();
              diagram.nodes.forEach((node: any) => {
                if (node?.data?.hFlip === true) {
                  console.log('[Open] Restoring hFlip state for node:', node.id);
                  setFlipped(node.id, true);
                  
                  // Also set it directly on the loaded node's raw data
                  const loadedNode = workflowDocument.getNode(node.id) as any;
                  if (loadedNode) {
                    if (loadedNode.raw?.data) {
                      loadedNode.raw.data.hFlip = true;
                    }
                    if (loadedNode.json?.data) {
                      loadedNode.json.data.hFlip = true;
                    }
                    // Force form to update with the flip state
                    try {
                      const form = (loadedNode as any).form;
                      if (form && form.patchValue) {
                        form.patchValue({ data: { ...form.state?.values?.data, hFlip: true } });
                        console.log('[Open] Patched form with hFlip for node (web):', node.id);
                      }
                    } catch (e) {
                      console.warn('[Open] Could not patch form for node (web):', node.id, e);
                    }
                    console.log('[Open] Set hFlip on loaded node raw data (web):', node.id);
                  }
                }
              });
              workflowDocument.fitView && workflowDocument.fitView();
            } else {
              workflowDocument.clear();
              workflowDocument.fromJSON(data as any);
              // Restore flip states for non-workflow format (web fallback)
              clearFlipStore();
              if ((data as any).nodes) {
                (data as any).nodes.forEach((node: any) => {
                  if (node?.data?.hFlip === true) {
                    console.log('[Open] Restoring hFlip state for node:', node.id);
                    setFlipped(node.id, true);
                  }
                });
              }
              workflowDocument.fitView && workflowDocument.fitView();
            }
          } catch (error) {
            console.error('Failed to load file:', error);
          }
        };
        reader.readAsText(file);
      }
      document.body.removeChild(input);
    };

    document.body.appendChild(input);
    input.click();
  }, [workflowDocument, setSkillInfo, setBreakpoints, setCurrentFilePath, setHasUnsavedChanges, setPreviewMode]);

  return (
    <Tooltip content="Open">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconOpenColored size={18} />}
        disabled={disabled}
        onClick={handleOpen}
      />
    </Tooltip>
  );
};