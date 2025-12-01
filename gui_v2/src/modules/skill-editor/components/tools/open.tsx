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

          // Read file content through IPC
          const fileResponse = await ipcApi.readSkillFile(filePath);
          console.log('[SKILL_IO][FRONTEND][IPC_READ_PRIMARY_RESULT]', { success: fileResponse.success, size: fileResponse?.data?.content?.length ?? 'n/a' });

          if (fileResponse.success && fileResponse.data) {
            const raw = JSON.parse(fileResponse.data.content);
            // 需求2: 不再Check文件名和 skillName 是否匹配
            // 因为我们会用Backend返回的 skillName（从文件夹Name提取）覆盖文件中的 skillName
            const nameInFile = String((raw && (raw as any).skillName) || '').trim();
            if (nameInFile && skillNameFromBackend && nameInFile !== skillNameFromBackend) {
              console.log('[SKILL_IO][FRONTEND][WILL_OVERRIDE_SKILL_NAME]', { 
                fromFile: nameInFile, 
                fromFolder: skillNameFromBackend 
              });
            }
            
            // Case A: primary file itself is a bundle
            const isBundle = raw && typeof raw === 'object' && 'mainSheetId' in raw && Array.isArray(raw.sheets);
            if (isBundle) {
              const bundle = raw as SheetsBundle;
              console.log('[SKILL_IO][FRONTEND][PRIMARY_IS_BUNDLE] Loading primary bundle file:', filePath);
              loadBundle(bundle);
              // 需求2: 使用Backend返回的 skillName（从文件夹Name提取）
              try {
                const norm = String(filePath).replace(/\\/g, '/');
                const parts = norm.split('/');
                const idx = parts.lastIndexOf('diagram_dir');
                let skillName = '';
                if (idx > 0) {
                  const folder = parts[idx - 1];
                  skillName = folder?.replace(/_skill$/i, '') || '';
                }
                if (!skillName) {
                  const base = (parts.pop() || '').replace(/\.json$/i, '');
                  skillName = base.replace(/_skill$/i, '');
                }
                console.log('[SKILL_IO][FRONTEND][SET_SKILL_NAME]', skillName);
                const current = skillInfoFromStore;
                if (current?.skillName !== skillName) {
                  setSkillInfo({ ...(current || { skillId: (current as any)?.skillId || '', skillName: skillName, version: '1.0.0', lastModified: new Date().toISOString(), workFlow: workflowDocument.toJSON() as any }), skillName: skillName });
                }
              } catch {}
              setCurrentFilePath(filePath);
              setHasUnsavedChanges(false);
              addRecentFile(createRecentFile(filePath, 'Multi-sheet Bundle'));
              return;
            }

            // Case B: primary file embeds a bundle inside { bundle: { mainSheetId, sheets } }
            try {
              const embedded = (raw as any)?.bundle;
              const looksLikeBundle = embedded && typeof embedded === 'object' && 'mainSheetId' in embedded && Array.isArray(embedded.sheets);
              if (looksLikeBundle) {
                console.log('[SKILL_IO][FRONTEND][PRIMARY_HAS_EMBEDDED_BUNDLE] Loading embedded bundle inside primary:', filePath);
                loadBundle(embedded as SheetsBundle);
                // 需求2: 使用Backend返回的 skillName
                try {
                  const norm = String(filePath).replace(/\\/g, '/');
                  const parts = norm.split('/');
                  const idx = parts.lastIndexOf('diagram_dir');
                  let skillName = '';
                  if (idx > 0) {
                    const folder = parts[idx - 1];
                    skillName = folder?.replace(/_skill$/i, '') || '';
                  }
                  if (!skillName) {
                    const base = (parts.pop() || '').replace(/\.json$/i, '');
                    skillName = base.replace(/_skill$/i, '');
                  }
                  console.log('[SKILL_IO][FRONTEND][SET_SKILL_NAME]', skillName);
                  const current = skillInfoFromStore;
                  if (current?.skillName !== skillName) {
                    setSkillInfo({ ...(current || { skillId: (current as any)?.skillId || '', skillName: skillName, version: '1.0.0', lastModified: new Date().toISOString(), workFlow: workflowDocument.toJSON() as any }), skillName: skillName });
                  }
                } catch {}
                setCurrentFilePath(filePath);
                setHasUnsavedChanges(false);
                addRecentFile(createRecentFile(filePath, 'Multi-sheet Bundle (embedded)'));
                return;
              }
            } catch (e) {
              console.warn('[SKILL_IO][FRONTEND][EMBEDDED_BUNDLE_CHECK_ERROR]', e);
            }

            // Try sibling bundle
            try {
              const idx = filePath.toLowerCase().lastIndexOf('.json');
              const base = idx !== -1 ? filePath.slice(0, idx) : filePath;
              const candidates = [
                `${base}_bundle.json`,
                `${base}-bundle.json`,
              ];
              console.log('[SKILL_IO][FRONTEND][BUNDLE_CANDIDATES]', candidates);
              for (const bundlePath of candidates) {
                try {
                  console.log('[SKILL_IO][FRONTEND][TRY_BUNDLE_PATH]', bundlePath);
                  const bundleResp = await ipcApi.readSkillFile(bundlePath);
                  console.log('[SKILL_IO][FRONTEND][TRY_BUNDLE_RESULT]', bundlePath, 'success=', bundleResp.success);
                  if (bundleResp.success && bundleResp.data) {
                    const maybeBundle = JSON.parse(bundleResp.data.content);
                    const isSiblingBundle = maybeBundle && typeof maybeBundle === 'object' && 'mainSheetId' in maybeBundle && Array.isArray(maybeBundle.sheets);
                    if (isSiblingBundle) {
                      console.log('[SKILL_IO][FRONTEND][FOUND_BUNDLE_JSON]', bundlePath);
                      loadBundle(maybeBundle as SheetsBundle);
                      // 需求2: 使用Backend返回的 skillName
                      try {
                        const skillName = skillNameFromBackend || ((String(filePath).split(/[/\\]/).pop() || '').replace(/\.json$/i, '').replace(/_skill$/i, ''));
                        console.log('[SKILL_IO][FRONTEND][SET_SKILL_NAME]', skillName);
                        const current = skillInfoFromStore;
                        if (current?.skillName !== skillName) {
                          setSkillInfo({ ...(current || { skillId: (current as any)?.skillId || '', skillName: skillName, version: '1.0.0', lastModified: new Date().toISOString(), workFlow: workflowDocument.toJSON() as any }), skillName: skillName });
                        }
                      } catch {}
                      // Keep currentFilePath as the main skill JSON path
                      setCurrentFilePath(filePath);
                      setHasUnsavedChanges(false);
                      addRecentFile(createRecentFile(bundlePath, 'Multi-sheet Bundle'));
                      return;
                    }
                  }
                } catch (err) {
                  console.warn('[SKILL_IO][FRONTEND][TRY_BUNDLE_ERROR]', bundlePath, err);
                }
              }
              console.log('[SKILL_IO][FRONTEND][NO_BUNDLE_JSON] No valid sibling bundle found; proceeding with single-skill load.');
            } catch (e) {
              console.warn('[SKILL_IO][FRONTEND][BUNDLE_CHECK_ERROR]', e);
            }

            const data = raw as SkillInfo;
            // Derive skillName from path to avoid backend mismatch
            try {
              const norm = String(filePath).replace(/\\/g, '/');
              // Expect <...>/<name>_skill/diagram_dir/<name>_skill.json or fallback to filename
              const parts = norm.split('/');
              const idx = parts.lastIndexOf('diagram_dir');
              let nameFromPath = '';
              if (idx > 0) {
                const folder = parts[idx - 1];
                nameFromPath = folder?.replace(/_skill$/i, '') || '';
              }
              if (!nameFromPath) {
                const base = (parts.pop() || '').replace(/\.json$/i, '');
                nameFromPath = base.replace(/_skill$/i, '');
              }
              if (nameFromPath) {
                data.skillName = nameFromPath;
              }
            } catch {}

            const diagram = data.workFlow;
            if (diagram) {
              console.log('[Open] Loading single-skill diagram. Nodes=', Array.isArray(diagram.nodes) ? diagram.nodes.length : 'n/a');
              setSkillInfo(data);
              setCurrentFilePath(filePath);
              setHasUnsavedChanges(false);
              const breakpointIds = diagram.nodes
                .filter((node: any) => node.data?.break_point)
                .map((node: any) => node.id);
              setBreakpoints(breakpointIds);
              workflowDocument.clear();
              workflowDocument.fromJSON(diagram);
              // Restore flip states from saved node data
              clearFlipStore();
              
              // Use setTimeout to ensure nodes are fully loaded before patching
              setTimeout(() => {
                diagram.nodes.forEach((node: any) => {
                  if (node?.data?.hFlip === true) {
                    console.log('[Open] Restoring hFlip state for node:', node.id);
                    setFlipped(node.id, true);
                    
                    // Also set it directly on the loaded node's raw data
                    const loadedNode = workflowDocument.getNode(node.id);
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
                          console.log('[Open] Patched form with hFlip for node:', node.id);
                        } else {
                          console.warn('[Open] Form not ready for node:', node.id);
                        }
                      } catch (e) {
                        console.warn('[Open] Could not patch form for node:', node.id, e);
                      }
                      
                      // Force node to re-render by triggering an update
                      try {
                        (loadedNode as any).update?.();
                      } catch {}
                      
                      console.log('[Open] Set hFlip on loaded node raw data:', node.id);
                    }
                  }
                  if (node?.data?.vFlip === true) {
                    console.log('[Open] Restoring vFlip state for node:', node.id);
                    // vFlip support can be added here when implemented
                  }
                });
              }, 100); // Small delay to ensure forms are initialized
              
              workflowDocument.fitView && workflowDocument.fitView();
            } else {
              workflowDocument.clear();
              workflowDocument.fromJSON(data as any);
              // Restore flip states for non-workflow format
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
          } else {
            console.error('[Open] Failed to read primary file:', fileResponse.error);
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
                  const loadedNode = workflowDocument.getNode(node.id);
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
  }, [workflowDocument, setSkillInfo, setBreakpoints, setCurrentFilePath, setHasUnsavedChanges]);

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