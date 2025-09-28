import React from 'react';
import { Dropdown, IconButton } from '@douyinfe/semi-ui';
import { IconFolderOpen, IconDeleteStroked, IconExit, IconPlus, IconLayers, IconSave, IconEdit } from '@douyinfe/semi-icons';
import { useClientContext, usePlayground, WorkflowSelectService, WorkflowDocument, useService } from '@flowgram.ai/free-layout-editor';
import { useSheetsStore } from '../../stores/sheets-store';

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
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const loadBundle = useSheetsStore((s) => s.loadBundle);
  const renameSheet = useSheetsStore((s) => s.renameSheet);

  const [visible, setVisible] = React.useState(false);

  const handleOpen = () => {
    const id = window.prompt('Open sheet by ID:');
    if (id) openSheet(id);
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
          <Dropdown.Item icon={<IconEdit />} onClick={handleRename} disabled={!activeId}>Rename Active Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleClear} disabled={!activeId}>Clear Sheet (blank)</Dropdown.Item>
          <Dropdown.Item icon={<IconExit />} onClick={handleClose} disabled={!activeId}>Close Active Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconDeleteStroked />} onClick={handleDelete} disabled={!activeId}>Delete Active Sheet</Dropdown.Item>
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
