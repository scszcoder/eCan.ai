import React from 'react';
import { Dropdown, IconButton } from '@douyinfe/semi-ui';
import { IconFolderOpen, IconDeleteStroked, IconExit, IconPlus, IconLayers, IconSave, IconEdit } from '@douyinfe/semi-icons';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { saveSheetsBundle, loadSheetsBundle } from '../../services/sheets-persistence';
import { useSheetsStore } from '../../stores/sheets-store';

/**
 * Minimal sheet menu - opens on click of a toolbar icon, similar to Add Node.
 * Actions: Open Sheet (by id), Close Active, Delete Active, New Sheet.
 * MVP uses prompt dialogs for simplicity.
 */
export const SheetsMenu: React.FC = () => {
  const ctx = useClientContext();
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

  const handleSaveAll = async () => {
    try {
      // Persist the current canvas to active sheet first
      if (ctx?.document) {
        const json = ctx.document.toJSON();
        saveActiveDocument(json);
      }
      const bundle = getAllSheets();
      await saveSheetsBundle(bundle, 'skill-bundle');
    } catch (e) {
      console.error('Save All failed', e);
      alert('Save All failed: ' + (e as Error).message);
    }
  };

  const handleLoadBundle = async () => {
    try {
      const result = await loadSheetsBundle();
      // @ts-ignore
      if (result && !result.cancelled) {
        // @ts-ignore
        loadBundle(result);
      }
    } catch (e) {
      console.error('Load Bundle failed', e);
      alert('Load Bundle failed: ' + (e as Error).message);
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
          <Dropdown.Item icon={<IconPlus />} onClick={handleNew}>New Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconFolderOpen />} onClick={handleOpen}>Open Sheet by ID</Dropdown.Item>
          <Dropdown.Item icon={<IconEdit />} onClick={handleRename} disabled={!activeId}>Rename Active Sheet</Dropdown.Item>
          <Dropdown.Item icon={<IconSave />} onClick={handleSaveAll}>Save All Sheets (bundle)</Dropdown.Item>
          <Dropdown.Item icon={<IconFolderOpen />} onClick={handleLoadBundle}>Load Bundle…</Dropdown.Item>
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
