import { useCallback, useMemo } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconOpenColored } from './colored-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useOpenPickerStore } from '../../stores/open-picker-store';
import { loadSkillFile, SkillLoadResult } from '../../services/skill-loader';
import { ipcApi, IPCAPI } from '../../../../services/ipc/api';
import { detectPlatform } from '../../../../config/platform';

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
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const setPreviewMode = useSkillInfoStore((state) => state.setPreviewMode);
  const setDataMappingJson = useSkillInfoStore((state) => state.setDataMappingJson);
  const setDataMappingPath = useSkillInfoStore((state) => state.setDataMappingPath);
  const setRunInCloud = useSkillInfoStore((state) => state.setRunInCloud);
  const setHybridCloudMode = useSkillInfoStore((state) => state.setHybridCloudMode);
  const setLocalHelperSkillId = useSkillInfoStore((state) => state.setLocalHelperSkillId);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const { setFlipped, clear: clearFlipStore } = useNodeFlipStore();
  
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

      // CRITICAL: Defer bundle loading and document operations to next event loop tick.
      // This prevents React state updates from happening during the current render cycle,
      // which can cause flowgram's internal async operations to access context in a
      // transitional state, leading to React error #321 (Invalid hook call).
      setTimeout(() => {
        // Load bundle if available
        if (result.bundle) {
          loadBundle(result.bundle);
          console.log('[SKILL_IO][FRONTEND][BUNDLE_LOADED]', result.bundlePath);
        }

        const diagram = data.workFlow;
        if (diagram) {
          console.log('[Open] Loading skill diagram. Nodes=', Array.isArray(diagram.nodes) ? diagram.nodes.length : 'n/a');
          
          setSkillInfo(data);
          setDataMappingJson(result.dataMapping || null, false);
          setDataMappingPath(result.dataMappingPath || null);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);
          
          // Restore run_in_cloud setting from saved skill
          setRunInCloud((data as any).run_in_cloud === true);
          setHybridCloudMode((data as any).hybrid_cloud_mode === true);
          setLocalHelperSkillId((data as any).local_helper_skill_id || null);
          
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
          setDataMappingJson(result.dataMapping || null, false);
          setDataMappingPath(result.dataMappingPath || null);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);
        }
      }, 0); // End of setTimeout - delay to allow React to settle
    } else {
      console.error('[Open] Failed to load file:', result.error);
      try { Toast.error({ content: result.error || 'Failed to load skill file.' }); } catch {}
    }
  }, [
    addRecentFile,
    clearFlipStore,
    loadBundle,
    setBreakpoints,
    setCurrentFilePath,
    setHasUnsavedChanges,
    setPreviewMode,
    setSkillInfo,
    setFlipped,
    workflowDocument,
    setDataMappingJson,
    setDataMappingPath,
    setRunInCloud,
    setHybridCloudMode,
    setLocalHelperSkillId,
  ]);

  const openWebPicker = useCallback(async () => {
    // Store the workflow document reference in global store so the modal can access it
    setStoreWorkflowDocument(workflowDocument);
    setPickerVisible(true);
    setSelectedItem(null);
    setPickerLoading(true);
    try {
      const ipcApi = IPCAPI.getInstance();
      const response = await ipcApi.listSkillFiles(undefined, 200);
      const items = response.success ? response.data : [];
      setPickerItems(items || []);
    } catch (error) {
      console.error('[Open][WebPicker] Failed to list skills:', error);
      try { Toast.error({ content: 'Failed to load skills from S3.' }); } catch {}
    } finally {
      setPickerLoading(false);
    }
  }, [workflowDocument, setStoreWorkflowDocument]);

  const handlePickerOpen = useCallback(async () => {
    if (!selectedItem?.filePath) return;
    setPickerOpenLoading(true);
    try {
      const result = await loadSkillFile(selectedItem.filePath);
      applyLoadedSkill(selectedItem.filePath, result);
      setPickerVisible(false);
    } catch (error) {
      console.error('[Open][WebPicker] Failed to open skill:', error);
      try { Toast.error({ content: 'Failed to open selected skill.' }); } catch {}
    } finally {
      setPickerOpenLoading(false);
    }
  }, [applyLoadedSkill, selectedItem]);

  const handleOpen = useCallback(async () => {
    if (detectPlatform() === 'web') {
      await openWebPicker();
      return;
    }

    // Desktop path uses IPC dialogs
    try {
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
          applyLoadedSkill(filePath, result);
        }
        return; // handled IPC path in desktop mode
    } catch (e) {
      console.warn('[SKILL_IO][FRONTEND][IPC_ERROR]', e);
      try { Toast.error({ content: 'Failed to open file dialog.' }); } catch {}
    };
  }, [applyLoadedSkill, openWebPicker]);

  // Modal is now rendered in OpenPickerModal at Editor level to survive error boundary recovery
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