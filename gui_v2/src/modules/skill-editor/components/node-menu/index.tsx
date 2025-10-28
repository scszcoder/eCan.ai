/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC, useCallback, useState, type MouseEvent } from 'react';

import {
  delay,
  useClientContext,
  useService,
  WorkflowDragService,
  WorkflowNodeEntity,
  WorkflowSelectService,
  FlowNodeFormData,
} from '@flowgram.ai/free-layout-editor';
import { NodeIntoContainerService } from '@flowgram.ai/free-container-plugin';
import { IconButton, Dropdown } from '@douyinfe/semi-ui';
import { IconMore } from '@douyinfe/semi-icons';

import { FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../../nodes/constants';
import { PasteShortcut } from '../../shortcuts/paste';
import { CopyShortcut } from '../../shortcuts/copy';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { IPCAPI } from '../../../../services/ipc/api';
import { useUserStore } from '../../../../stores/userStore';

interface NodeMenuProps {
  node: WorkflowNodeEntity;
  updateTitleEdit: (setEditing: boolean) => void;
  deleteNode: () => void;
}

export const NodeMenu: FC<NodeMenuProps> = ({ node, deleteNode, updateTitleEdit }) => {
  const [visible, setVisible] = useState(true);
  const clientContext = useClientContext();
  const registry = node.getNodeRegistry<FlowNodeRegistry>();
  const nodeIntoContainerService = useService(NodeIntoContainerService);
  const selectService = useService(WorkflowSelectService);
  const dragService = useService(WorkflowDragService);
  const canMoveOut = nodeIntoContainerService.canMoveOutContainer(node);
  const { breakpoints, addBreakpoint, removeBreakpoint } = useSkillInfoStore();
  const isBreakpoint = breakpoints.includes(node.id);
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);

  const rerenderMenu = useCallback(() => {
    // force destroy component - 强制销毁ComponentTrigger重新Render
    setVisible(false);
    requestAnimationFrame(() => {
      setVisible(true);
    });
  }, []);

  const handleMoveOut = useCallback(
    async (e: MouseEvent) => {
      e.stopPropagation();
      const sourceParent = node.parent;
      // move out of container - 移出Container
      nodeIntoContainerService.moveOutContainer({ node });
      await delay(16);
      // clear invalid lines - 清除非法线条
      await nodeIntoContainerService.clearInvalidLines({
        dragNode: node,
        sourceParent,
      });
      rerenderMenu();
      // select node - 选中节点
      selectService.selectNode(node);
      // start drag node - 开始Drag
      dragService.startDragSelectedNodes(e);
    },
    [nodeIntoContainerService, node, rerenderMenu]
  );

  const handleCopy = useCallback(
    (e: React.MouseEvent) => {
      const copyShortcut = new CopyShortcut(clientContext);
      const pasteShortcut = new PasteShortcut(clientContext);
      const data = copyShortcut.toClipboardData([node]);
      pasteShortcut.apply(data);
      e.stopPropagation(); // Disable clicking prevents the sidebar from opening
    },
    [clientContext, node]
  );

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      deleteNode();
      e.stopPropagation(); // Disable clicking prevents the sidebar from opening
    },
    [clientContext, node]
  );
  const handleEditTitle = useCallback(() => {
    updateTitleEdit(true);
  }, [updateTitleEdit]);

  const handleBreakpointToggle = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation(); // keep sidebar closed
    const targetId = node.id;
    // compute current state from store at click-time to avoid stale closure
    const currIsBp = useSkillInfoStore.getState().breakpoints.includes(targetId);
    const nextIsBp = !currIsBp;

    // 1) Optimistic UI update: store + node JSON
    try {
      if (nextIsBp) addBreakpoint(targetId); else removeBreakpoint(targetId);
      // update node form json if available
      const formData = node.getData?.(FlowNodeFormData);
      const formModel = formData?.getFormModel?.();
      const formControl = formModel?.formControl as any;
      if (formControl?.setFieldValue) {
        formControl.setFieldValue('data.breakpoint', nextIsBp);
      } else {
        // fallback: patch raw data
        try { (node as any).raw = { ...(node as any).raw, data: { ...((node as any).raw?.data || {}), breakpoint: nextIsBp } }; } catch {}
      }
    } catch {}
    // refresh menu label
    rerenderMenu();

    // 2) Backend sync (best-effort). No rollback on failure; keep UI responsive.
    try {
      if (!username) return;
      const node_name = targetId;
      const resp = nextIsBp
        ? await ipcApi.setSkillBreakpoints(username, node_name)
        : await ipcApi.clearSkillBreakpoints(username, node_name);
      if (!resp.success) {
        console.warn('[Breakpoint] backend rejected toggle for', node_name);
      }
    } catch {
      console.warn('[Breakpoint] network error during toggle');
    }
  }, [node, username, ipcApi, addBreakpoint, removeBreakpoint, rerenderMenu]);

  const handleUngroup = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    // TODO: Implement ungroup functionality
    // For now, just delete the group (same as delete)
    deleteNode();
  }, [deleteNode]);

  if (!visible) {
    return <></>;
  }

  return (
    <Dropdown
      trigger="hover"
      position="bottomRight"
      render={
        <Dropdown.Menu>
          {/* Special menu for Group nodes */}
          {registry.type === 'group' ? (
            <>
              <Dropdown.Item onClick={handleUngroup}>Ungroup</Dropdown.Item>
              <Dropdown.Item onClick={handleDelete}>Delete</Dropdown.Item>
            </>
          ) : (
            <>
              <Dropdown.Item onClick={handleEditTitle}>Edit Title</Dropdown.Item>
              {canMoveOut && <Dropdown.Item onClick={handleMoveOut}>Move out</Dropdown.Item>}
              <Dropdown.Item onClick={handleCopy} disabled={registry.meta!.copyDisable === true}>
                Create Copy
              </Dropdown.Item>
              {![WorkflowNodeType.Condition, WorkflowNodeType.Loop].includes(registry.type as any) && (
                <Dropdown.Item onClick={(e) => handleBreakpointToggle(e)}>
                  {isBreakpoint ? 'Clear Breakpoint' : 'Set Breakpoint'}
                </Dropdown.Item>
              )}
              <Dropdown.Item
                onClick={handleDelete}
                disabled={!!(registry.canDelete?.(clientContext, node) || registry.meta!.deleteDisable)}
              >
                Delete
              </Dropdown.Item>
            </>
          )}
        </Dropdown.Menu>
      }
    >
      <IconButton
        color="secondary"
        size="small"
        theme="borderless"
        icon={<IconMore />}
        onClick={(e) => e.stopPropagation()}
      />
    </Dropdown>
  );
};
