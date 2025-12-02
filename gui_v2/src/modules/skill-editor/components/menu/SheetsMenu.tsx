import React from 'react';
import { Dropdown, IconButton, Toast } from '@douyinfe/semi-ui';
import { IconFolderOpen, IconDeleteStroked, IconExit, IconPlus, IconLayers, IconEdit } from '@douyinfe/semi-icons';
import { useClientContext, usePlayground, WorkflowSelectService, WorkflowDocument, useService } from '@flowgram.ai/free-layout-editor';
import { useSheetsStore } from '../../stores/sheets-store';
import { IPCAPI } from '../../../../services/ipc/api';

/**
 * Minimal sheet menu - opens on click of a toolbar icon, similar to Add Node.
 * Actions: Open Sheet (by id), Close Active, Delete Active, New Sheet.
 * MVP uses prompt dialogs for simplicity.
 */
export const SheetsMenu: React.FC = () => {
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

  const [visible, setVisible] = React.useState(false);
  const sheetList = React.useMemo(() => sheetOrder.map((id) => sheetMap[id]).filter(Boolean), [sheetOrder, sheetMap]);

  const handleOpen = () => {
    const id = window.prompt('Open sheet by ID:');
    if (id) openSheet(id);
  };

  const handleTestLanggraph2Flowgram = async () => {
    try {
      const ipc = IPCAPI.getInstance();
      const resp = await ipc.testLanggraph2Flowgram();
      if (resp.success) {
        Toast.success({ content: 'langgraph2flowgram test exported to test_skill/diagram_dir' });
      } else {
        Toast.error({ content: `Test failed: ${resp.error?.message || 'unknown error'}` });
      }
    } catch (e) {
      console.error('[SheetsMenu] test-langgraph2flowgram error', e);
      Toast.error({ content: 'IPC error while testing langgraph2flowgram' });
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
    if (activeId === 'main') return alert('Cannot delete the main sheet in MVP.');
    if (confirm(`Delete sheet '${activeId}'? This cannot be undone.`)) {
      deleteSheet(activeId);
    }
  };
  const handleNew = () => {
    const name = prompt('New sheet name?') || undefined;
    const id = newSheet(name, null);
    openSheet(id);
  };

  const handleClear = () => {
    if (!activeId) return;
    const ok = confirm('Clear current sheet to an empty canvas? This will remove all nodes and edges in this sheet.');
    if (!ok) return;
    clearActiveSheet();
  };

  const handleRename = () => {
    if (!activeId) return;
    const name = prompt('Rename sheet to:');
    if (!name) return;
    renameSheet(activeId, name);
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
        Toast.success({ content: 'Step Sim: setup complete. Backend moved to Start.' });
      } else {
        Toast.error({ content: `Setup failed: ${resp.error?.message || 'unknown error'}` });
      }
    } catch (e) {
      console.error('[SheetsMenu] setup-step-sim error', e);
      Toast.error({ content: 'Setup step sim error' });
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
        Toast.error({ content: `Step failed: ${resp.error?.message || 'unknown error'}` });
      }
    } catch (e) {
      console.error('[SheetsMenu] step-sim error', e);
      Toast.error({ content: 'Step sim error' });
    } finally {
      setVisible(false);
    }
  };

  return (
    <Dropdown
      position="bottomLeft"
      trigger="custom"
      visible={visible}
      onClickOutSide={() => setVisible(false)}
      render={
        <Dropdown.Menu>
          <Dropdown.Item icon={<IconPlus />} onClick={handleInsertSheetCall}>Insert Sheet Call…</Dropdown.Item>
          <Dropdown.Item icon={<IconPlus />} onClick={handleNew}>New Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconFolderOpen />} onClick={handleOpen}>Open Sheet by ID</Dropdown.Item>
          <Dropdown.Item disabled>
            <span style={{ fontWeight: 600, color: '#666' }}>Open Sheet…</span>
          </Dropdown.Item>
          {/* Auto-generated list of available sheets */}
          {(sheetList || []).map((s) => (
            <Dropdown.Item key={s.id} onClick={() => { openSheet(s.id); setVisible(false); }}>
              {s.name || s.id} <span style={{ color: '#999' }}>({s.id})</span>
            </Dropdown.Item>
          ))}
          <Dropdown.Item icon={<IconEdit />} onClick={handleRename} disabled={!activeId}>Rename Active Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleClear} disabled={!activeId}>Clear Sheet (blank)</Dropdown.Item>
          <Dropdown.Item icon={<IconExit />} onClick={handleClose} disabled={!activeId}>Close Active Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleDelete} disabled={!activeId}>Delete Active Sheet</Dropdown.Item>
          <Dropdown.Divider />
          <Dropdown.Item icon={<IconEdit />} onClick={handleSetupStepSim}>[DEV] setup-step-sim</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleStepSim}>[DEV] step-sim</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleTestLanggraph2Flowgram}>[DEV] test langgraph2flowgram</Dropdown.Item>
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
  );
};
