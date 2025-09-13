/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useCallback, useContext, useEffect, useMemo, startTransition, useRef } from 'react';

import {
  PlaygroundEntityContext,
  useRefresh,
  useClientContext,
} from '@flowgram.ai/free-layout-editor';
import { SideSheet } from '@douyinfe/semi-ui';

import { FlowNodeMeta } from '../../typings';
import { SidebarContext, IsSidebarContext } from '../../context';
import { SidebarNodeRenderer } from './sidebar-node-renderer';

export const SidebarRenderer = () => {
  const { nodeId, setNodeId } = useContext(SidebarContext);
  // Prevent immediate close after open due to rapid selection/change events
  const lastOpenAtRef = useRef<number>(0);
  const LOCK_MS = 300;
  const { selection, playground, document } = useClientContext();
  const refresh = useRefresh();
  const handleClose = useCallback(() => {
    // Sidebar delayed closing
    startTransition(() => {
      setNodeId(undefined);
    });
  }, []);
  const node = nodeId ? document.getNode(nodeId) : undefined;
  /**
   * Listen readonly
   */
  useEffect(() => {
    const disposable = playground.config.onReadonlyOrDisabledChange(() => {
      // Do not auto-close the sidebar here; readonly/disabled flips can be transient
      refresh();
    });
    return () => disposable.dispose();
  }, [playground]);
  /**
   * Listen selection
   */
  useEffect(() => {
    const toDispose = selection.onSelectionChanged(() => {
      // If no node is selected, close the sidebar
      if (selection.selection.length === 0) {
        const now = Date.now();
        if (now - lastOpenAtRef.current > LOCK_MS) {
          handleClose();
        }
        return;
      }
      // If exactly one node is selected, sync the sidebar to that node instead of closing
      if (selection.selection.length === 1) {
        const sel = selection.selection[0];
        if (sel && sel.id !== nodeId) {
          startTransition(() => setNodeId(sel.id));
          lastOpenAtRef.current = Date.now();
        }
        return;
      }
      // For multi-selection, close by default
      const now = Date.now();
      if (now - lastOpenAtRef.current > LOCK_MS) {
        handleClose();
      }
    });
    return () => toDispose.dispose();
  }, [selection, handleClose, nodeId]);
  /**
   * Close when node disposed
   */
  useEffect(() => {
    if (node) {
      const toDispose = node.onDispose(() => {
        setNodeId(undefined);
      });
      return () => toDispose.dispose();
    }
    return () => {};
  }, [node]);

  const visible = useMemo(() => {
    if (!node) {
      return false;
    }
    const { sidebarDisabled = false } = node.getNodeMeta<FlowNodeMeta>();
    return !sidebarDisabled;
  }, [node]);

  if (playground.config.readonly) {
    return null;
  }
  /**
   * Add "key" to rerender the sidebar when the node changes
   */
  const content =
    node && visible ? (
      <PlaygroundEntityContext.Provider key={node.id} value={node}>
        <SidebarNodeRenderer node={node} />
      </PlaygroundEntityContext.Provider>
    ) : null;

  return (
    <SideSheet
      mask={false}
      visible={visible}
      onCancel={handleClose}
      closable={false}
      motion={false}
      width={500}
      headerStyle={{
        display: 'none',
      }}
      bodyStyle={{
        padding: 0,
      }}
      style={{
        background: 'none',
        boxShadow: 'none',
      }}
    >
      <IsSidebarContext.Provider value={true}>{content}</IsSidebarContext.Provider>
    </SideSheet>
  );
};
