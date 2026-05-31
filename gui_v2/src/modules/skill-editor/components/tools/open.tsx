import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconOpenColored } from './colored-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import '../../../../services/ipc/file-api';
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useNodeNoteStore } from '../../stores/node-note-store';
import { useConditionPortOrderStore } from '../../stores/condition-port-order-store';
import { useOpenPickerStore } from '../../stores/open-picker-store';
import { loadSkillFile, SkillLoadResult } from '../../services/skill-loader';
import { IPCAPI } from '../../../../services/ipc/api';

// Note: The Modal is now rendered in OpenPickerModal component at Editor level
// to prevent it from being unmounted during Tools error boundary recovery

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

  const setPickerVisible = useOpenPickerStore((s) => s.setVisible);
  const setPickerLoading = useOpenPickerStore((s) => s.setLoading);
  const setPickerItems = useOpenPickerStore((s) => s.setItems);
  const setSelectedItem = useOpenPickerStore((s) => s.setSelectedItem);
  const setStoreWorkflowDocument = useOpenPickerStore((s) => s.setWorkflowDocument);

  const restoreNodeLocalState = useCallback((nodes: any[]) => {
    clearFlipStore();
    clearConditionPortOrders();
    useNodeNoteStore.getState().clear();

    setTimeout(() => {
      nodes.forEach((node: any) => {
        if (node?.data?.hFlip === true) {
          console.log('[Open] Restoring hFlip state for node:', node.id);
          setFlipped(node.id, true);
          const loadedNode = workflowDocument.getNode(node.id) as any;
          if (loadedNode) {
            if (loadedNode.raw?.data) loadedNode.raw.data.hFlip = true;
            if (loadedNode.json?.data) loadedNode.json.data.hFlip = true;
            try {
              const form = loadedNode.form;
              if (form?.patchValue) {
                form.patchValue({ data: { ...form.state?.values?.data, hFlip: true } });
              }
            } catch {}
            try { loadedNode.update?.(); } catch {}
          }
        }
        if (node?.data?.agentNote) {
          useNodeNoteStore.getState().setNote(node.id, node.data.agentNote);
        }
      });
    }, 100);
  }, [clearConditionPortOrders, clearFlipStore, setFlipped, workflowDocument]);

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
        setSkillInfo(data);
        setDataMappingJson(result.dataMapping || null, false);
        setDataMappingPath(result.dataMappingPath || null);
        setCurrentFilePath(filePath);
        setHasUnsavedChanges(false);

        const cfg: any = (data as any).config || {};
        setRunInCloud((data as any).run_in_cloud === true || cfg.run_in_cloud === true);
        setHybridCloudMode((data as any).hybrid_cloud_mode === true || cfg.hybrid_cloud_mode === true);
        setLocalHelperSkillId((data as any).local_helper_skill_id || cfg.local_helper_skill_id || null);
        setLocalHelperMachine((data as any).local_helper_machine || cfg.local_helper_machine || null);
        setToolsets((data as any).toolsets || []);
        setSkillsets((data as any).skillsets || []);

        if (diagram) {
          console.log('[Open] Loading skill diagram. Nodes=', Array.isArray(diagram.nodes) ? diagram.nodes.length : 'n/a');
          const nodes = Array.isArray(diagram.nodes) ? diagram.nodes : [];
          const breakpointIds = nodes
            .filter((node: any) => node.data?.break_point)
            .map((node: any) => node.id);
          setBreakpoints(breakpointIds);
          if (!result.bundle) {
            workflowDocument.clear();
            workflowDocument.fromJSON(diagram);
          }
          restoreNodeLocalState(nodes);
        } else {
          workflowDocument.clear();
          workflowDocument.fromJSON(data as any);
          const nodes = Array.isArray((data as any).nodes) ? (data as any).nodes : [];
          restoreNodeLocalState(nodes);
        }

        workflowDocument.fitView && workflowDocument.fitView();
        addRecentFile(createRecentFile(filePath, data.skillName || 'Skill'));
        setIsSkillLoading(false);
      }, 0);
    } else {
      console.error('[Open] Failed to load file:', result.error);
      try { Toast.error({ content: result.error || 'Failed to load skill file.' }); } catch {}
    }
  }, [
    addRecentFile,
    loadBundle,
    restoreNodeLocalState,
    setBreakpoints,
    setCurrentFilePath,
    setDataMappingJson,
    setDataMappingPath,
    setHasUnsavedChanges,
    setHybridCloudMode,
    setIsSkillLoading,
    setLocalHelperMachine,
    setLocalHelperSkillId,
    setPreviewMode,
    setRunInCloud,
    setSkillInfo,
    setSkillsets,
    setToolsets,
    workflowDocument,
  ]);

  const openRemotePicker = useCallback(async () => {
    setStoreWorkflowDocument(workflowDocument);
    setPickerLoading(true);
    setPickerVisible(true);
    setSelectedItem(null);
    try {
      const ipcApi = IPCAPI.getInstance();
      const response = await ipcApi.listSkillFiles(undefined, 200);
      if (response?.success && Array.isArray(response.data)) {
        setPickerItems(response.data as any[]);
      } else {
        setPickerItems([]);
        try { Toast.error({ content: response?.error?.message || 'Failed to list skill files.' }); } catch {}
      }
    } catch (error) {
      console.error('[Open] Failed to list skill files:', error);
      setPickerItems([]);
      try { Toast.error({ content: 'Failed to list skill files.' }); } catch {}
    } finally {
      setPickerLoading(false);
    }
  }, [
    setPickerItems,
    setPickerLoading,
    setPickerVisible,
    setSelectedItem,
    setStoreWorkflowDocument,
    workflowDocument,
  ]);

  const handleOpen = useCallback(async () => {
    setStoreWorkflowDocument(workflowDocument);
    try {
      const ipcApi = IPCAPI.getInstance();
      console.log('[SKILL_IO][FRONTEND][IPC_ATTEMPT] showOpenDialog');
      const dialogResponse = await ipcApi.showOpenDialog([
        { name: 'Skill Files', extensions: ['json'] },
        { name: 'All Files', extensions: ['*'] },
      ]);

      const selectedPath = dialogResponse?.data?.filePath;
      if (!dialogResponse?.success || dialogResponse?.data?.cancelled || !selectedPath) {
        console.log('[SKILL_IO][FRONTEND][DIALOG_CANCELLED]');
        return;
      }

      const result = await loadSkillFile(selectedPath);
      applyLoadedSkill(selectedPath, result);
    } catch (error) {
      console.warn('[SKILL_IO][FRONTEND][IPC_ERROR]', error);
      await openRemotePicker();
    }
  }, [applyLoadedSkill, openRemotePicker, setStoreWorkflowDocument, workflowDocument]);

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