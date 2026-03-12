import React from 'react';
import { useTranslation } from 'react-i18next';
import { Dropdown, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconFolderOpen, IconDeleteStroked, IconExit, IconPlus, IconLayers, IconEdit, IconUpload, IconMinus, IconSave } from '@douyinfe/semi-icons';
import { useClientContext, usePlayground, WorkflowSelectService, WorkflowDocument, useService } from '@flowgram.ai/free-layout-editor';
import { useSheetsStore } from '../../stores/sheets-store';
import { IPCAPI } from '../../../../services/ipc/api';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useUserStore } from '../../../../stores/userStore';
import { SavePromptsModal, collectInlinePrompts } from './SavePromptsModal';

/**
 * Minimal sheet menu - opens on click of a toolbar icon, similar to Add Node.
 * Actions: Open Sheet (by id), Close Active, Delete Active, New Sheet.
 * MVP uses prompt dialogs for simplicity.
 */
export const SheetsMenu: React.FC = () => {
  const { t } = useTranslation('skillEditor');
  const ctx = useClientContext();
  const playground = usePlayground();
  const workflowDocument = useService(WorkflowDocument);
  const selectService = useService(WorkflowSelectService);
  const activeId = useSheetsStore((s) => s.activeSheetId);
  const openSheet = useSheetsStore((s) => s.openSheet);
  const closeSheet = useSheetsStore((s) => s.closeSheet);
  const deleteSheet = useSheetsStore((s) => s.deleteSheet);
  const newSheet = useSheetsStore((s) => s.newSheet);
  const clearActiveSheet = useSheetsStore((s) => s.clearActiveSheet);
  const saveActiveDocument = useSheetsStore((s) => s.saveActiveDocument);
  const sheetOrder = useSheetsStore((s) => s.order);
  const sheetMap = useSheetsStore((s) => s.sheets);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const renameSheet = useSheetsStore((s) => s.renameSheet);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  
  // Get skill info and username for register/unregister
  const skillInfo = useSkillInfoStore((s) => s.skillInfo);
  const setSkillInfo = useSkillInfoStore((s) => s.setSkillInfo);
  const currentFilePath = useSkillInfoStore((s) => s.currentFilePath);
  const username = useUserStore((s) => s.username);

  const [visible, setVisible] = React.useState(false);
  const [savePromptsVisible, setSavePromptsVisible] = React.useState(false);
  const sheetList = React.useMemo(() => {
    return sheetOrder.map((id) => sheetMap[id]).filter(Boolean);
  }, [sheetOrder, sheetMap]);

  const handleOpen = () => {
    const id = window.prompt(t('sheetsMenu.openSheetPrompt'));
    if (id) openSheet(id);
  };

  const handleTestLanggraph2Flowgram = async () => {
    try {
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.testLanggraph2Flowgram();
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.testExported') });
      } else {
        Toast.error({ content: t('sheetsMenu.testFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] test-langgraph2flowgram error', e);
      Toast.error({ content: t('sheetsMenu.testIpcError') });
    } finally {
      setVisible(false);
    }
  };

  const handleInsertSheetCall = () => {
    try {
      const center = playground.config.getPosFromMouseEvent({
        clientX: Math.round(window.innerWidth / 2),
        clientY: Math.round((window.innerHeight / 2)),
      });
      const node = workflowDocument.createWorkflowNodeByType('sheet-call' as any, center, undefined as any, undefined);
      // Select the new node for editing in sidebar
      selectService.selectNode(node);
      setVisible(false);
    } catch (e) {
      console.error('Failed to insert sheet-call node', e);
    }
  };
  const handleClose = () => {
    if (activeId) closeSheet(activeId);
  };
  const handleDelete = () => {
    if (!activeId) return;
    if (activeId === 'main') return alert(t('sheetsMenu.deleteMainSheet'));
    if (confirm(t('sheetsMenu.deleteSheetConfirm', { id: activeId }))) {
      deleteSheet(activeId);
    }
  };
  const handleNew = () => {
    const name = prompt(t('sheetsMenu.newSheetNamePrompt')) || undefined;
    const id = newSheet(name, null);
    openSheet(id);
  };

  const handleClear = () => {
    if (!activeId) return;
    const ok = confirm(t('sheetsMenu.clearSheetConfirm'));
    if (!ok) return;
    clearActiveSheet();
  };

  const handleRename = () => {
    if (!activeId) return;
    const name = prompt(t('sheetsMenu.renameSheetPrompt'));
    if (!name) return;
    renameSheet(activeId, name);
  };

  // ---- Register / Unregister Skill ----
  const handleRegisterSkill = async () => {
    if (!skillInfo) {
      Toast.warning({ content: t('sheetsMenu.noSkillLoaded') });
      setVisible(false);
      return;
    }
    if (!username) {
      Toast.warning({ content: t('sheetsMenu.notLoggedIn') });
      setVisible(false);
      return;
    }

    try {
      console.info('[SheetsMenu] Registering skill:', skillInfo.skillName);
      const ipc = IPCAPI.getInstance();

      // Build config payload for cloud-related runtime behavior.
      // AppSync `AWSJSON` expects a JSON string; backend will parse it.
      const runInCloud = useSkillInfoStore.getState().runInCloud;
      const hybridCloudMode = useSkillInfoStore.getState().hybridCloudMode;
      const localHelperSkillId = useSkillInfoStore.getState().localHelperSkillId;
      const localHelperMachine = useSkillInfoStore.getState().localHelperMachine;
      const dataMappingJson = useSkillInfoStore.getState().dataMappingJson;

      let skillMapping: any = undefined;
      if (typeof dataMappingJson === 'string' && dataMappingJson.trim()) {
        try {
          skillMapping = JSON.parse(dataMappingJson);
        } catch (e) {
          console.warn('[SheetsMenu] Failed to parse dataMappingJson; skipping skill_mapping in config', e);
        }
      }

      if (skillMapping === undefined) {
        skillMapping = (skillInfo as any)?.config?.skill_mapping;
      }

      if (skillMapping === undefined) {
        // Minimal default mapping structure (matches data_mapping.json defaults)
        skillMapping = {
          developing: { mappings: [], options: { strict: false, apply_order: 'top_down' } },
          released: { mappings: [], options: { strict: true, apply_order: 'top_down' } },
          event_routing: {},
        };
      }

      const configObj: any = {
        nodes: (skillInfo as any)?.config?.nodes || {},
        run_in_cloud: !!runInCloud,
        hybrid_cloud_mode: !!hybridCloudMode,
        local_helper_machine: localHelperMachine ?? null,
        local_helper_skill_id: localHelperSkillId ?? null,
      };

      configObj.skill_mapping = skillMapping;
      
      // Build SkillInput from current skillInfo
      const skillInput = {
        name: skillInfo.skillName,
        description: skillInfo.description || `Skill: ${skillInfo.skillName}`,
        path: currentFilePath || undefined,
        version: skillInfo.version || '1.0.0',
        level: 'basic',
        public: false,
        rentable: false,
        config: JSON.stringify(configObj),
      };

      const resp = await ipc.newAgentSkill(username, skillInput);
      console.log('[SheetsMenu] register response:', resp);
      if (resp.success) {
        // Update skillInfo with the database ID so unregister works
        const results = Array.isArray(resp.data) ? resp.data : [resp.data];
        const result = results[0];
        if (result?.id) {
          console.info('[SheetsMenu] Updating skillId from', skillInfo.skillId, 'to database id:', result.id);
          setSkillInfo({ ...skillInfo, skillId: result.id });
        }
        Toast.success({ content: t('sheetsMenu.registeredSuccess', { name: skillInfo.skillName }) });
      } else {
        Toast.error({ content: t('sheetsMenu.registerFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] register-skill error', e);
      Toast.error({ content: t('sheetsMenu.registerError') });
    } finally {
      setVisible(false);
    }
  };

  const handleUnregisterSkill = async () => {
    if (!skillInfo) {
      Toast.warning({ content: t('sheetsMenu.noSkillForUnregister') });
      setVisible(false);
      return;
    }
    if (!username) {
      Toast.warning({ content: t('sheetsMenu.notLoggedIn') });
      setVisible(false);
      return;
    }

    const ok = confirm(t('sheetsMenu.unregisterConfirm', { name: skillInfo.skillName }));
    if (!ok) {
      setVisible(false);
      return;
    }

    try {
      const ipc = IPCAPI.getInstance();
      
      // If we don't have a database skillId, try to find it by name from getAllMine
      let skillIdToDelete = skillInfo.skillId;
      if (!skillIdToDelete || skillIdToDelete === '') {
        console.info('[SheetsMenu] No skillId, looking up by name:', skillInfo.skillName);
        try {
          const allResp = await ipc.getAgentSkills(username, []);
          const skills = Array.isArray(allResp?.data) ? allResp.data : (allResp?.data as any)?.skills || [];
          const match = skills.find((s: any) => s.name === skillInfo.skillName);
          if (match?.id) {
            skillIdToDelete = match.id;
            console.info('[SheetsMenu] Found skill by name, id:', skillIdToDelete);
          }
        } catch (lookupErr) {
          console.warn('[SheetsMenu] Failed to lookup skill by name:', lookupErr);
        }
      }
      
      if (!skillIdToDelete || skillIdToDelete === '') {
        Toast.error({ content: t('sheetsMenu.unregisterNotFound', { name: skillInfo.skillName }) });
        setVisible(false);
        return;
      }
      
      console.info('[SheetsMenu] Unregistering skill:', skillIdToDelete);
      const resp = await ipc.deleteAgentSkill(username, skillIdToDelete);
      console.log('[SheetsMenu] unregister response:', resp);
      
      // Check both the outer response and the inner result
      const results = Array.isArray(resp.data) ? resp.data : [resp.data];
      const result = results[0] as any;
      
      if (resp.success && result?.success !== false) {
        // Clear the skillId since it's no longer registered
        setSkillInfo({ ...skillInfo, skillId: '' });
        Toast.success({ content: t('sheetsMenu.unregisteredSuccess', { name: skillInfo.skillName }) });
      } else {
        const errMsg = result?.error || resp.error?.message || 'unknown error';
        Toast.error({ content: t('sheetsMenu.unregisterFailed', { error: errMsg }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] unregister-skill error', e);
      Toast.error({ content: t('sheetsMenu.unregisterError') });
    } finally {
      setVisible(false);
    }
  };

  // ---- Dev test driver: step simulation ----
  const handleSetupStepSim = async () => {
    try {
      console.info('[SIM][FE] setup-step-sim: saving active document and sending bundle to backend');
      // Persist current active document first
      try { saveActiveDocument(ctx.document.toJSON()); } catch {}
      const bundle = getAllSheets();
      try { console.debug('[SIM][FE] setup-step-sim bundle summary', { sheets: bundle?.sheets?.length, mainSheetId: (bundle as any)?.mainSheetId, activeSheetId: (bundle as any)?.activeSheetId }); } catch {}
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.setupSimStep(bundle);
      console.info('[SIM][FE] setup-step-sim: backend response', resp);
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.setupStepSimComplete') });
      } else {
        Toast.error({ content: t('sheetsMenu.setupFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] setup-step-sim error', e);
      Toast.error({ content: t('sheetsMenu.setupStepSimError') });
    } finally {
      setVisible(false);
    }
  };

  const handleStepSim = async () => {
    try {
      console.info('[SIM][FE] step-sim: requesting backend to advance one node');
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.stepSim();
      console.info('[SIM][FE] step-sim: backend response', resp);
      if (!resp.success) {
        Toast.error({ content: t('sheetsMenu.stepFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] step-sim error', e);
      Toast.error({ content: t('sheetsMenu.stepSimError') });
    } finally {
      setVisible(false);
    }
  };

  const handleSimTimerEvent = async () => {
    try {
      console.info('[SIM][FE] sim-timer-event: requesting backend');
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.simTimerEvent();
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.simTimerEventTriggered') });
      } else {
        Toast.error({ content: t('sheetsMenu.simTimerEventFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] sim-timer-event error', e);
      Toast.error({ content: t('sheetsMenu.simTimerEventError') });
    } finally {
      setVisible(false);
    }
  };

  const handleSimWebsocketEvent = async () => {
    try {
      console.info('[SIM][FE] sim-websocket-event: requesting backend');
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.simWebsocketEvent();
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.simWebsocketEventTriggered') });
      } else {
        Toast.error({ content: t('sheetsMenu.simWebsocketEventFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] sim-websocket-event error', e);
      Toast.error({ content: t('sheetsMenu.simWebsocketEventError') });
    } finally {
      setVisible(false);
    }
  };

  const handleSimSseEvent = async () => {
    try {
      console.info('[SIM][FE] sim-sse-event: requesting backend');
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.simSseEvent();
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.simSseEventTriggered') });
      } else {
        Toast.error({ content: t('sheetsMenu.simSseEventFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] sim-sse-event error', e);
      Toast.error({ content: t('sheetsMenu.simSseEventError') });
    } finally {
      setVisible(false);
    }
  };

  const handleSimWebhookEvent = async () => {
    try {
      console.info('[SIM][FE] sim-webhook-event: requesting backend');
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.simWebhookEvent();
      if (resp.success) {
        Toast.success({ content: t('sheetsMenu.simWebhookEventTriggered') });
      } else {
        Toast.error({ content: t('sheetsMenu.simWebhookEventFailed', { error: resp.error?.message || 'unknown error' }) });
      }
    } catch (e) {
      console.error('[SheetsMenu] sim-webhook-event error', e);
      Toast.error({ content: t('sheetsMenu.simWebhookEventError') });
    } finally {
      setVisible(false);
    }
  };

  return (
    <>
    <Dropdown
      position="bottomLeft"
      trigger="custom"
      visible={visible}
      onClickOutSide={() => setVisible(false)}
      render={
        <Dropdown.Menu>
          <Dropdown.Item icon={<IconPlus />} onClick={handleInsertSheetCall}>{t('sheetsMenu.insertSheetCall')}</Dropdown.Item>
          <Dropdown.Item icon={<IconPlus />} onClick={handleNew}>{t('sheetsMenu.newSheet')}</Dropdown.Item>
          <Dropdown.Item icon={<IconUpload />} onClick={handleRegisterSkill} disabled={!skillInfo}>{t('sheetsMenu.registerSkill')}</Dropdown.Item>
          <Dropdown.Item icon={<IconMinus />} onClick={handleUnregisterSkill} disabled={!skillInfo}>{t('sheetsMenu.unregisterSkill')}</Dropdown.Item>
          <Dropdown.Item icon={<IconSave />} onClick={() => {
            try {
              const docJson = ctx.document.toJSON();
              const entries = collectInlinePrompts(docJson);
              if (entries.length === 0) {
                Toast.info({ content: t('sheetsMenu.savePromptsNone') });
                setVisible(false);
                return;
              }
            } catch {}
            setSavePromptsVisible(true);
            setVisible(false);
          }}>{t('sheetsMenu.savePrompts')}</Dropdown.Item>
          <Dropdown.Divider />
          <Dropdown.Item icon={<IconFolderOpen />} onClick={handleOpen}>{t('sheetsMenu.openSheetById')}</Dropdown.Item>
          <Dropdown.Item disabled>
            <span style={{ fontWeight: 600, color: '#666' }}>{t('sheetsMenu.openSheet')}</span>
          </Dropdown.Item>
          {/* Auto-generated list of available sheets */}
          {(sheetList || []).map((s) => (
            <Dropdown.Item key={s.id} onClick={() => { openSheet(s.id); setVisible(false); }}>
              {s.name || s.id} <span style={{ color: '#999' }}>({s.id})</span>
            </Dropdown.Item>
          ))}
          <Dropdown.Item icon={<IconEdit />} onClick={handleRename} disabled={!activeId}>{t('sheetsMenu.renameActiveSheet')}</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleClear} disabled={!activeId}>{t('sheetsMenu.clearSheet')}</Dropdown.Item>
          <Dropdown.Item icon={<IconExit />} onClick={handleClose} disabled={!activeId}>{t('sheetsMenu.closeActiveSheet')}</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleDelete} disabled={!activeId}>{t('sheetsMenu.deleteActiveSheet')}</Dropdown.Item>
          <Dropdown.Divider />
          <Dropdown.Item icon={<IconEdit />} onClick={handleSetupStepSim}>{t('sheetsMenu.devSetupStepSim')}</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleStepSim}>{t('sheetsMenu.devStepSim')}</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleTestLanggraph2Flowgram}>{t('sheetsMenu.devTestLanggraph')}</Dropdown.Item>
          <Dropdown.Divider />
          <Dropdown.Item icon={<IconEdit />} onClick={handleSimTimerEvent}>{t('sheetsMenu.simTimerEvent')}</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleSimWebsocketEvent}>{t('sheetsMenu.simWebsocketEvent')}</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleSimSseEvent}>{t('sheetsMenu.simSseEvent')}</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleSimWebhookEvent}>{t('sheetsMenu.simWebhookEvent')}</Dropdown.Item>
        </Dropdown.Menu>
      }
    >
      <IconButton
        icon={<IconLayers />}
        theme="borderless"
        type="tertiary"
        style={{ color: '#fff' }}
        onClick={() => setVisible((v) => !v)}
      />
    </Dropdown>
    <SavePromptsModal
      visible={savePromptsVisible}
      onClose={() => setSavePromptsVisible(false)}
    />
    </>
  );
};
