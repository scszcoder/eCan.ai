/**
 * Open Skill Picker Modal - Rendered via Portal outside React tree
 * to prevent modal from being affected by flowgram context issues.
 * 
 * This component does NOT use useClientContext at all.
 * Instead, it gets the workflow document from the global store,
 * which is set by the Open button when the picker is opened.
 */
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { createPortal } from 'react-dom';
import { Toast, Modal, Input } from '@douyinfe/semi-ui';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useOpenPickerStore } from '../../stores/open-picker-store';
import { loadSkillFile, SkillLoadResult } from '../../services/skill-loader';

type SkillFileItem = {
  filePath: string;
  fileName?: string;
  fileSize?: number;
  skillName?: string;
  updatedAt?: string;
};

// No bridge component needed anymore - document comes from store

// The actual modal content - does NOT use any flowgram hooks
const OpenPickerModalContent = () => {
  // Get the workflow document from the store (set by Open button)
  const workflowDocument = useOpenPickerStore((s) => s.workflowDocument);
  
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
  const setLocalHelperMachine = useSkillInfoStore((state) => state.setLocalHelperMachine);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const { setFlipped, clear: clearFlipStore } = useNodeFlipStore();
  
  // Use global store for picker state
  const { t } = useTranslation('skillEditor');
  const [pickerQuery, setPickerQuery] = useState('');
  const pickerVisible = useOpenPickerStore((s) => s.visible);
  const setPickerVisible = useOpenPickerStore((s) => s.setVisible);
  const pickerLoading = useOpenPickerStore((s) => s.loading);
  const pickerOpenLoading = useOpenPickerStore((s) => s.openLoading);
  const setPickerOpenLoading = useOpenPickerStore((s) => s.setOpenLoading);
  const pickerItems = useOpenPickerStore((s) => s.items);
  const selectedItem = useOpenPickerStore((s) => s.selectedItem);
  const setSelectedItem = useOpenPickerStore((s) => s.setSelectedItem);

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
      setPreviewMode(false);
      const data = result.skillInfo;
      console.log('[SKILL_IO][FRONTEND][SKILL_NAME]', data.skillName);

      setTimeout(() => {
        if (result.bundle) {
          loadBundle(result.bundle);
          console.log('[SKILL_IO][FRONTEND][BUNDLE_LOADED]', result.bundlePath);
        }

        const diagram = data.workFlow;
        if (diagram) {
          console.log('[OpenPickerModal] Loading skill diagram. Nodes=', Array.isArray(diagram.nodes) ? diagram.nodes.length : 'n/a');
          
          setSkillInfo(data);
          setDataMappingJson(result.dataMapping || null, false);
          setDataMappingPath(result.dataMappingPath || null);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);
          
          // Restore cloud execution settings from saved skill
          const cfg: any = (data as any).config || {};
          setRunInCloud((data as any).run_in_cloud === true || cfg.run_in_cloud === true);
          setHybridCloudMode((data as any).hybrid_cloud_mode === true || cfg.hybrid_cloud_mode === true);
          setLocalHelperSkillId((data as any).local_helper_skill_id || cfg.local_helper_skill_id || null);
          setLocalHelperMachine((data as any).local_helper_machine || cfg.local_helper_machine || null);
          
          const breakpointIds = diagram.nodes
            .filter((node: any) => node.data?.break_point)
            .map((node: any) => node.id);
          setBreakpoints(breakpointIds);
          
          if (!result.bundle && workflowDocument) {
            workflowDocument.clear();
            workflowDocument.fromJSON(diagram);
          }
          
          clearFlipStore();
          setTimeout(() => {
            if (!workflowDocument) return;
            diagram.nodes.forEach((node: any) => {
              if (node?.data?.hFlip === true) {
                console.log('[OpenPickerModal] Restoring hFlip state for node:', node.id);
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
          
          if (workflowDocument?.fitView) workflowDocument.fitView();
          addRecentFile(createRecentFile(filePath, data.skillName || 'Skill'));
        } else {
          if (workflowDocument) {
            workflowDocument.clear();
            workflowDocument.fromJSON(data as any);
          }
          clearFlipStore();
          if ((data as any).nodes && workflowDocument) {
            (data as any).nodes.forEach((node: any) => {
              if (node?.data?.hFlip === true) setFlipped(node.id, true);
            });
          }
          if (workflowDocument?.fitView) workflowDocument.fitView();
          setSkillInfo(data);
          setDataMappingJson(result.dataMapping || null, false);
          setDataMappingPath(result.dataMappingPath || null);
          setCurrentFilePath(filePath);
          setHasUnsavedChanges(false);
        }
      }, 0);
    } else {
      console.error('[OpenPickerModal] Failed to load file:', result.error);
      try { Toast.error({ content: result.error || 'Failed to load skill file.' }); } catch {}
    }
  }, [
    addRecentFile,
    clearFlipStore,
    workflowDocument,
    loadBundle,
    setBreakpoints,
    setCurrentFilePath,
    setHasUnsavedChanges,
    setPreviewMode,
    setSkillInfo,
    setFlipped,
    setDataMappingJson,
    setDataMappingPath,
  ]);

  const handlePickerOpen = useCallback(async () => {
    if (!selectedItem?.filePath) return;
    setPickerOpenLoading(true);
    try {
      const result = await loadSkillFile(selectedItem.filePath);
      applyLoadedSkill(selectedItem.filePath, result);
      setPickerVisible(false);
    } catch (error) {
      console.error('[OpenPickerModal] Failed to open skill:', error);
      try { Toast.error({ content: 'Failed to open selected skill.' }); } catch {}
    } finally {
      setPickerOpenLoading(false);
    }
  }, [applyLoadedSkill, selectedItem, setPickerOpenLoading, setPickerVisible]);

  // Don't render when not visible
  if (!pickerVisible) {
    return null;
  }

  return (
    <Modal
      title={t('openPicker.title')}
      visible={pickerVisible}
      onOk={handlePickerOpen}
      onCancel={() => setPickerVisible(false)}
      okText={t('openPicker.okText')}
      cancelText={t('openPicker.cancelText')}
      okButtonProps={{ disabled: !selectedItem || pickerOpenLoading, loading: pickerOpenLoading }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Input
          placeholder={t('openPicker.searchPlaceholder')}
          value={pickerQuery}
          onChange={setPickerQuery}
          showClear
          disabled={pickerLoading}
        />
        {pickerLoading ? (
          <div>Loading...</div>
        ) : (
          <div style={{ maxHeight: 300, overflow: 'auto' }}>
            {filteredItems.map((item: SkillFileItem) => {
              const isSelected = selectedItem?.filePath === item.filePath;
              const title = item.skillName || item.fileName || item.filePath.split('/').pop() || 'Skill';
              return (
                <div
                  key={item.filePath}
                  onClick={() => setSelectedItem(item)}
                  style={{
                    cursor: 'pointer',
                    background: isSelected ? 'var(--semi-color-fill-0)' : 'transparent',
                    borderRadius: 6,
                    padding: '8px 12px',
                    marginBottom: 4,
                    border: isSelected ? '1px solid var(--semi-color-primary)' : '1px solid transparent',
                  }}
                >
                  <div style={{ fontWeight: 500 }}>{title}</div>
                  <div style={{ fontSize: 12, color: 'var(--semi-color-text-2)' }}>{item.filePath}</div>
                </div>
              );
            })}
          </div>
        )}
        {!pickerLoading && filteredItems.length === 0 && (
          <div style={{ color: 'var(--semi-color-text-2)' }}>
            No skills found in S3.
          </div>
        )}
      </div>
    </Modal>
  );
};

// Get or create a portal container
const getPortalContainer = () => {
  let container = document.getElementById('open-picker-portal');
  if (!container) {
    container = document.createElement('div');
    container.id = 'open-picker-portal';
    document.body.appendChild(container);
  }
  return container;
};

// The main export - renders via portal to be completely isolated from React tree
export const OpenPickerModal = () => {
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => {
    // Delay mounting to ensure portal container is ready
    const timer = setTimeout(() => setMounted(true), 50);
    return () => clearTimeout(timer);
  }, []);
  
  if (!mounted) return null;
  
  return createPortal(
    <OpenPickerModalContent />,
    getPortalContainer()
  );
};
