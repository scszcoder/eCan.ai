import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconOpenColored } from './colored-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { SheetsBundle } from '../../services/sheets-persistence';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useNodeNoteStore } from '../../stores/node-note-store';
import { useConditionPortOrderStore } from '../../stores/condition-port-order-store';
import { useOpenPickerStore } from '../../stores/open-picker-store';
import { loadSkillFile, SkillLoadResult } from '../../services/skill-loader';
import { ipcApi, IPCAPI } from '../../../../services/ipc/api';
import { detectPlatform } from '../../../../config/platform';
import { traverseWorkflowNodes } from '../../utils/traverse-workflow-nodes';

// Note: The Modal is now rendered in OpenPickerModal component at Editor level
// to prevent it from being unmounted during Tools error boundary recovery

type SkillFileItem = {
  filePath: string;
  fileName?: string;
  fileSize?: number;
  skillName?: string;
  updatedAt?: string;
};

interface OpenProps {
  disabled?: boolean;
}

export const Open = ({ disabled }: OpenProps) => {
  const { t } = useTranslation('skillEditor');
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const setPreviewMode = useSkillInfoStore((state) => state.setPreviewMode);
  const setIsSkillLoading = useSkillInfoStore((state) => state.setIsSkillLoading);
  const setDataMappingJson = useSkillInfoStore((state) => state.setDataMappingJson);
  const setDataMappingPath = useSkillInfoStore((state) => state.setDataMappingPath);
  const setRunInCloud = useSkillInfoStore((state) => state.setRunInCloud);
  const setHybridCloudMode = useSkillInfoStore((state) => state.setHybridCloudMode);
  const setLocalHelperSkillId = useSkillInfoStore((state) => state.setLocalHelperSkillId);
  const setLocalHelperMachine = useSkillInfoStore((state) => state.setLocalHelperMachine);
  const setToolsets = useSkillInfoStore((state) => state.setToolsets);
  const setSkillsets = useSkillInfoStore((state) => state.setSkillsets);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const { setFlipped, clear: clearFlipStore } = useNodeFlipStore();
  const clearConditionPortOrders = useConditionPortOrderStore((s) => s.clear);

  // Use global store for picker state so it persists across error boundary recoveries
  const pickerVisible = useOpenPickerStore((s) => s.visible);
  const setPickerVisible = useOpenPickerStore((s) => s.setVisible);
  const pickerLoading = useOpenPickerStore((s) => s.loading);
  const setPickerLoading = useOpenPickerStore((s) => s.setLoading);
  const pickerOpenLoading = useOpenPickerStore((s) => s.openLoading);
  const setPickerOpenLoading = useOpenPickerStore((s) => s.setOpenLoading);
  const pickerQuery = useOpenPickerStore((s) => s.query);
  const setPickerQuery = useOpenPickerStore((s) => s.setQuery);
  const pickerItems = useOpenPickerStore((s) => s.items);
  const setPickerItems = useOpenPickerStore((s) => s.setItems);
  const selectedItem = useOpenPickerStore((s) => s.selectedItem);
  const setSelectedItem = useOpenPickerStore((s) => s.setSelectedItem);
  const setStoreWorkflowDocument = useOpenPickerStore((s) => s.setWorkflowDocument);
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

  const filteredItems = useMemo(() => {
    const query = pickerQuery.trim().toLowerCase();
    const items = pickerItems.filter((item) => {
      const path = item.filePath || '';
      const name = item.skillName || item.fileName || '';
      const matches = !query || path.toLowerCase().includes(query) || name.toLowerCase().includes(query);
      const isJson = path.toLowerCase().endsWith('.json') || (item.fileName || '').toLowerCase().endsWith('.json');
      return matches && isJson;
    });
    return items.sort((a, b) => {
      const aTime = a.updatedAt ? Date.parse(a.updatedAt) : 0;
      const bTime = b.updatedAt ? Date.parse(b.updatedAt) : 0;
      return bTime - aTime;
    });
  }, [pickerItems, pickerQuery]);

  const applyLoadedSkill = useCallback((filePath: string, result: SkillLoadResult) => {
    if (result.success && result.skillInfo) {
      // Open explicitly exits preview mode
      setPreviewMode(false);
      const data = result.skillInfo;
      // skillName is already normalized by skill-loader.ts
      console.log('[SKILL_IO][FRONTEND][SKILL_NAME]', data.skillName);

      // Mark skill as loading so the Run button is blocked until canvas is fully updated
      setIsSkillLoading(true);

      // CRITICAL: Defer bundle loading and document operations to next event loop tick.
      // This prevents React state updates from happening during the current render cycle,
      // which can cause flowgram's internal async operations to access context in a
      // transitional state, leading to React error #321 (Invalid hook call).
      setTimeout(() => {
        // Load bundle if available
        if (result.bundle) {
          loadBundle(result.bundle);
          console.log('[SKILL_IO][FRONTEND][BUNDLE_LOADED]', result.bundlePath);
        } else {
          // For non-bundle files, initialize a main sheet with the diagram data.
          // This ensures ActiveSheetBinder loads the correct document (not blankFlowData).
          const diagram = data.workFlow;
          if (diagram) {
            const now = Date.now();
            useSheetsStore.setState({
              sheets: {
                'main': {
                  id: 'main',
                  name: 'Main',
                  document: JSON.parse(JSON.stringify(diagram)),
                  createdAt: now,
                  lastOpenedAt: now,
                }
              },
              order: ['main'],
              openTabs: ['main'],
              activeSheetId: 'main',
            });
          } else {
            useSheetsStore.setState({ sheets: {}, order: [], openTabs: [], activeSheetId: null });
          }
        }

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
  }, [
    addRecentFile,
    clearFlipStore,
    clearConditionPortOrders,
    loadBundle,
    setBreakpoints,
    setCurrentFilePath,
    setHasUnsavedChanges,
    setPreviewMode,
    setSkillInfo,
    setFlipped,
    setIsSkillLoading,
    workflowDocument,
    setDataMappingJson,
    setDataMappingPath,
    setRunInCloud,
    setHybridCloudMode,
    setLocalHelperSkillId,
    setLocalHelperMachine,
  ]);

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
  }, [applyLoadedSkill, openWebPicker]);

  // Modal is now rendered in OpenPickerModal at Editor level to survive error boundary recovery
  return (
    <Tooltip content={t('open.tooltip')}>
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