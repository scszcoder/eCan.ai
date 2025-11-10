/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { FC, useCallback, useState, type MouseEvent } from 'react';

import {
  delay,
  useClientContext,
  useService,
  WorkflowDragService,
  WorkflowNodeEntity,
  WorkflowSelectService,
  FlowNodeFormData,
  WorkflowDocument,
  WorkflowLinesManager,
  WorkflowNodePortsData,
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
import { usePortSideService } from '../../services/port-side';
import { useNodeFlipStore } from '../../stores/node-flip-store';

interface NodeMenuProps {
  node: WorkflowNodeEntity;
  updateTitleEdit: (setEditing: boolean) => void;
  deleteNode: () => void;
}

export const NodeMenu: FC<NodeMenuProps> = ({ node, deleteNode, updateTitleEdit }) => {
  const [visible, setVisible] = useState(true);
  const hFlipInProgress = React.useRef(false);
  const lastHFlipAt = React.useRef(0);
  const clientContext = useClientContext();
  const registry = node.getNodeRegistry<FlowNodeRegistry>();
  const nodeIntoContainerService = useService(NodeIntoContainerService);
  const selectService = useService(WorkflowSelectService);
  const dragService = useService(WorkflowDragService);
  const documentSvc = useService(WorkflowDocument);
  const linesMgr = useService(WorkflowLinesManager);
  const canMoveOut = nodeIntoContainerService.canMoveOutContainer(node);
  const { breakpoints, addBreakpoint, removeBreakpoint } = useSkillInfoStore();
  const isBreakpoint = breakpoints.includes(node.id);
  const ipcApi = IPCAPI.getInstance();
  const username = useUserStore((state) => state.username);
  const { canFlipAnchors, applyHFlipAnchors } = usePortSideService();
  const { setFlipped, isFlipped, setBusy, isBusy } = useNodeFlipStore();

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

  // Toggle horizontal flip for ports. Persist on node data.
  const handleHFlipToggle = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    const now = Date.now();
    if (now - lastHFlipAt.current < 300) {
      console.log('[H-flip] Ignored due to timestamp guard');
      return;
    }
    lastHFlipAt.current = now;
    
    // Prevent double-firing from menu click propagation
    if (hFlipInProgress.current || isBusy(node.id)) {
      console.log('[H-flip] Ignoring duplicate call');
      return;
    }
    hFlipInProgress.current = true;
    setBusy(node.id, true);
    
    try {
      const curr = isFlipped(node.id);
      const next = !curr;
      console.log('[H-flip] Toggling from', curr, 'to', next);
      // Update persistent store
      setFlipped(node.id, next);
      // Update both form and raw data to ensure persistence
      const formData = node.getData?.(FlowNodeFormData);
      const formModel = formData?.getFormModel?.();
      const formControl = formModel?.formControl as any;
      if (formControl?.setFieldValue) {
        formControl.setFieldValue('data.hFlip', next);
      }
      // Always patch raw as well for non-form reads
      try {
        if (!(node as any).raw) (node as any).raw = {};
        if (!(node as any).raw.data) (node as any).raw.data = {};
        (node as any).raw.data.hFlip = next;
      } catch {}
      // Also update the JSON directly
      try {
        const json = (node as any).json;
        if (json) {
          if (!json.data) json.data = {};
          json.data.hFlip = next;
        }
      } catch {}
      // do NOT force-remount the menu here; it resets the guard and double-triggers

      // Try behavioral anchor flip (skip for Condition to avoid engine resetting outputs)
      try {
        if (registry.type === WorkflowNodeType.Condition) {
          console.log('[H-flip] Condition node: skipping applyHFlipAnchors to preserve outputs');
        } else if (canFlipAnchors()) {
          await applyHFlipAnchors(node, next);
        } else {
          console.info('[H-flip] Visual-only: anchor flip not supported by current editor API');
        }
        // Sync classes and re-bind condition outputs (works regardless of branch above)
        const rebindNow = () => {
          let em: any;
          try {
            em = (documentSvc as any)?.entityManager;
            if (em) em.changeEntityLocked = true;
            // Ensure dynamic ports are up-to-date before we read ports from the document
            try {
              const portsData = (node as any)?.getData?.(WorkflowNodePortsData);
              portsData?.updateAllPorts?.();
            } catch {}
            const allPorts: any[] = (documentSvc as any)?.getAllPorts?.() || [];
            const portsOfNode = allPorts.filter((p) => p?.node?.id === node.id);
            for (const p of portsOfNode) {
              const pid: string = p?.id || '';
              const el = document.querySelector(`.se-port[data-se-port-id="${pid}"]`);
              if (!el) continue;
              const isIn = pid.includes('port_input_');
              const isOut = pid.includes('port_output_');
              const loc = (p as any)?.location ?? (p as any)?.position;
              const flip = (isIn && loc === 'right') || (isOut && loc === 'left');
              el.classList.toggle('se-port--hflip', !!flip);
            }
            // Re-bind condition outputs explicitly to IF/ELSE markers
            if (registry.type === WorkflowNodeType.Condition) {
              const root = document.querySelector(`[data-node-id="${node.id}"]`);
              if (root) {
                const markerIf = root.querySelector('[data-port-id="if_out"]') as HTMLElement | null;
                const markerElse = root.querySelector('[data-port-id="else_out"]') as HTMLElement | null;
                const sideOut = next ? 'left' : 'right';
                const sideIn = next ? 'right' : 'left';
                const getKey = (pp: any) => String((pp?.portID ?? pp?.portId ?? '')).toLowerCase();
                const pidLower = (pp: any) => String(pp?.id || '').toLowerCase();
                const outPorts = portsOfNode.filter((pp: any) => pidLower(pp).includes('port_output_') || (pp?.inout === 'output')) as any[];
                let pIf = outPorts.find((pp: any) => getKey(pp).includes('if') || pidLower(pp).includes('if_out') || pidLower(pp).includes('if_') || pidLower(pp).includes('elif_')) as any;
                let pElse = outPorts.find((pp: any) => getKey(pp).includes('else') || pidLower(pp).includes('else_out') || pidLower(pp).includes('else_')) as any;
                if (!pIf && outPorts.length) pIf = outPorts[0];
                if (!pElse && outPorts.length > 1) pElse = outPorts.find((pp: any) => pp !== pIf) || outPorts[1];
                const pIn = portsOfNode.find((pp: any) => pidLower(pp).includes('port_input_') || (pp?.inout === 'input')) as any;
                if (pIf) {
                  if (markerIf) {
                    if (typeof pIf.setTargetElement === 'function') pIf.setTargetElement(markerIf);
                    else if (typeof pIf.update === 'function') pIf.update({ targetElement: markerIf });
                  }
                  try { pIf.update?.({ location: sideOut, position: sideOut, side: sideOut }); } catch {}
                  try { pIf.validate?.(); } catch {}
                }
                if (pElse) {
                  if (markerElse) {
                    if (typeof pElse.setTargetElement === 'function') pElse.setTargetElement(markerElse);
                    else if (typeof pElse.update === 'function') pElse.update({ targetElement: markerElse });
                  }
                  try { pElse.update?.({ location: sideOut, position: sideOut, side: sideOut }); } catch {}
                  try { pElse.validate?.(); } catch {}
                }
                if (pIn) {
                  try { pIn.update?.({ location: sideIn, position: sideIn, side: sideIn }); } catch {}
                  try { pIn.validate?.(); } catch {}
                }
              }
            }
            // Validate ports and lines explicitly to sync geometry without needing a canvas click
            try {
              portsOfNode.forEach((pp: any) => {
                try { pp.validate?.(); } catch {}
                const lns = (pp as any)?.allLines ?? (pp as any)?.lines ?? [];
                if (lns && typeof lns.forEach === 'function') {
                  lns.forEach((ln: any) => { try { ln.validate?.(); } catch {} });
                }
              });
            } catch {}
            try { (linesMgr as any)?.forceUpdate?.(); } catch {}
            try { (documentSvc as any)?.fireContentChange?.(); } catch {}
            // Wait until markers settle on the correct side, then finalize validation to avoid needing a user click
            try {
              const root = document.querySelector(`[data-node-id="${node.id}"]`) as HTMLElement | null;
              const isStable = () => {
                if (!root) return false;
                const r = root.getBoundingClientRect();
                const mi = root.querySelector('[data-port-id="if_out"]') as HTMLElement | null;
                const me = root.querySelector('[data-port-id="else_out"]') as HTMLElement | null;
                if (!mi || !me) return false;
                const ri = mi.getBoundingClientRect();
                const re = me.getBoundingClientRect();
                const centerI = ri.left + ri.width / 2;
                const centerE = re.left + re.width / 2;
                const expectLeft = next === true;
                const iLeftSide = centerI < r.left + r.width / 2;
                const eLeftSide = centerE < r.left + r.width / 2;
                return expectLeft ? (iLeftSide && eLeftSide) : (!iLeftSide && !eLeftSide);
              };
              const finalize = () => {
                try {
                  const allPorts: any[] = (documentSvc as any)?.getAllPorts?.() || [];
                  const portsOfNode = allPorts.filter((p) => p?.node?.id === node.id);
                  // As a final guard, rebind IF/ELSE to markers and set sides again
                  try {
                    const markerIf = root?.querySelector('[data-port-id="if_out"]') as HTMLElement | null;
                    const markerElse = root?.querySelector('[data-port-id="else_out"]') as HTMLElement | null;
                    const sideOut = next ? 'left' : 'right';
                    const sideIn = next ? 'right' : 'left';
                    const getKey = (pp: any) => String((pp?.portID ?? pp?.portId ?? '')).toLowerCase();
                    const pidLower = (pp: any) => String(pp?.id || '').toLowerCase();
                    const outPorts = portsOfNode.filter((pp: any) => pidLower(pp).includes('port_output_') || (pp?.inout === 'output')) as any[];
                    let pIf = outPorts.find((pp: any) => getKey(pp).includes('if') || pidLower(pp).includes('if_out') || pidLower(pp).includes('if_') || pidLower(pp).includes('elif_')) as any;
                    let pElse = outPorts.find((pp: any) => getKey(pp).includes('else') || pidLower(pp).includes('else_out') || pidLower(pp).includes('else_')) as any;
                    if (!pIf && outPorts.length) pIf = outPorts[0];
                    if (!pElse && outPorts.length > 1) pElse = outPorts.find((pp: any) => pp !== pIf) || outPorts[1];
                    const pIn = portsOfNode.find((pp: any) => pidLower(pp).includes('port_input_') || (pp?.inout === 'input')) as any;
                    if (pIf && markerIf) {
                      if (typeof pIf.setTargetElement === 'function') pIf.setTargetElement(markerIf);
                      else if (typeof pIf.update === 'function') pIf.update({ targetElement: markerIf });
                      try { pIf.update?.({ location: sideOut, position: sideOut, side: sideOut }); } catch {}
                    }
                    if (pElse && markerElse) {
                      if (typeof pElse.setTargetElement === 'function') pElse.setTargetElement(markerElse);
                      else if (typeof pElse.update === 'function') pElse.update({ targetElement: markerElse });
                      try { pElse.update?.({ location: sideOut, position: sideOut, side: sideOut }); } catch {}
                    }
                    if (pIn) {
                      try { pIn.update?.({ location: sideIn, position: sideIn, side: sideIn }); } catch {}
                    }
                  } catch {}
                  // Now validate ports and all their lines
                  portsOfNode.forEach((pp: any) => {
                    try { pp.validate?.(); } catch {}
                    const lns = (pp as any)?.allLines ?? (pp as any)?.lines ?? [];
                    if (lns && typeof lns.forEach === 'function') {
                      lns.forEach((ln: any) => { try { ln.validate?.(); } catch {} });
                    }
                  });
                  try { (linesMgr as any)?.forceUpdate?.(); } catch {}
                  try { (documentSvc as any)?.fireContentChange?.(); } catch {}
                  // Finalize by emulating the user's required click:
                  // - odd flip (next=true): click on node
                  // - even flip (next=false): click outside node but inside editor canvas (.demo-editor)
                  try {
                    const rootEl = document.querySelector(`[data-node-id="${node.id}"]`) as HTMLElement | null;
                    const canvasEl = document.querySelector('.demo-editor') as HTMLElement | null;
                    const clickAt = (el: HTMLElement, x: number, y: number) => {
                      const opts: MouseEventInit = { bubbles: true, cancelable: true, clientX: Math.floor(x), clientY: Math.floor(y) };
                      el.dispatchEvent(new MouseEvent('click', opts));
                    };
                    requestAnimationFrame(() => {
                      requestAnimationFrame(() => {
                        try {
                          if (next && rootEl) {
                            const r = rootEl.getBoundingClientRect();
                            clickAt(rootEl, r.left + r.width / 2, r.top + r.height / 2);
                          } else if (canvasEl) {
                            const cr = canvasEl.getBoundingClientRect();
                            const nr = rootEl?.getBoundingClientRect();
                            const candidates = [
                              { x: cr.left + 8, y: cr.top + 8 },
                              { x: cr.right - 8, y: cr.top + 8 },
                              { x: cr.left + 8, y: cr.bottom - 8 },
                              { x: cr.right - 8, y: cr.bottom - 8 },
                            ];
                            const outside = (p: any) => !nr || p.x < nr.left || p.x > nr.right || p.y < nr.top || p.y > nr.bottom;
                            const pt = candidates.find(outside) || { x: cr.left + 8, y: cr.top + 8 };
                            clickAt(canvasEl, pt.x, pt.y);
                          }
                        } catch {}
                      });
                    });
                  } catch {}
                } catch {}
              };
              const waitStable = (attempt = 0) => {
                if (attempt > 10) { finalize(); return; }
                if (isStable()) { finalize(); return; }
                requestAnimationFrame(() => waitStable(attempt + 1));
              };
              requestAnimationFrame(() => waitStable(0));
            } catch {}
          } catch (err) {
            try { console.warn('[H-flip] rebindNow error', err); } catch {}
          } finally {
            try { if (em) em.changeEntityLocked = false; } catch {}
          }
        };
        // Apply immediately; stability check below will finalize and select the node
        rebindNow();
        // Synthetic outside click (opt-in only). Enable via: window.__SE_SYNTH_CLICK__ = true
        try {
          // @ts-ignore
          if ((window as any).__SE_SYNTH_CLICK__ === true) {
            const doSyntheticClick = () => {
              try {
                // Ensure we do one more rebind right before the click
                try { rebindNow(); } catch {}
                const root = document.querySelector(`[data-node-id="${node.id}"]`) as HTMLElement | null;
                if (!root) return;
                // Prefer viewport center as a robust outside target
                const center = { x: Math.floor(window.innerWidth / 2), y: Math.floor(window.innerHeight / 2) };
                const isInsideNode = (x: number, y: number) => {
                  const r = root.getBoundingClientRect();
                  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
                };
                let pt = !isInsideNode(center.x, center.y) ? center : { x: 10, y: 10 };
                if (isInsideNode(pt.x, pt.y)) {
                  // Fallback near bottom-right outside node
                  const r = root.getBoundingClientRect();
                  pt = { x: Math.min(window.innerWidth - 10, r.right + 30), y: Math.min(window.innerHeight - 10, r.bottom + 30) };
                }
                const target = document.elementFromPoint(pt.x, pt.y);
                if (!target || root.contains(target)) return;
                const opts: MouseEventInit = { bubbles: true, clientX: pt.x, clientY: pt.y };
                try { target.dispatchEvent(new MouseEvent('pointermove', opts)); } catch {}
                try { target.dispatchEvent(new MouseEvent('pointerdown', opts)); } catch {}
                try { target.dispatchEvent(new MouseEvent('mousedown', opts)); } catch {}
                try { target.dispatchEvent(new MouseEvent('mouseup', opts)); } catch {}
                try { target.dispatchEvent(new MouseEvent('click', opts)); } catch {}
              } catch {}
            };
            // Use a slightly longer delay for odd flips to cover slower reflow
            setTimeout(doSyntheticClick, next ? 650 : 500);
            // Re-select the node after synthetic click so the user focus remains
            setTimeout(() => { try { (selectService as any)?.selectNode?.(node); } catch {} }, next ? 800 : 650);
            // Fire a second synthetic click to catch any late settling in odd flips
            setTimeout(doSyntheticClick, next ? 1000 : 850);
            setTimeout(() => { try { (selectService as any)?.selectNode?.(node); } catch {} }, next ? 1150 : 1000);
          }
        } catch {}
      } catch (err) {
        console.warn('[H-flip] Flip handling encountered an error', err);
      }
    } catch {}
    finally {
      // Reset guard after short delay
      setTimeout(() => {
        hFlipInProgress.current = false;
        setBusy(node.id, false);
      }, 150);
    }
  }, [node, rerenderMenu, canFlipAnchors, applyHFlipAnchors, selectService, documentSvc, linesMgr, isFlipped, setFlipped]);

  const handleBreakpointToggle = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation(); // keep sidebar closed
    const targetId = node.id;
    // compute current state from store at click-time to avoid stale closure
    const currIsBp = useSkillInfoStore.getState().breakpoints.includes(targetId);
    const nextIsBp = !currIsBp;
    try { console.log('[Breakpoint][UI] toggle', { node: targetId, currIsBp, nextIsBp }); } catch {}

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
      if (nextIsBp) {
        try { console.log('[Breakpoint][UI] calling set_skill_breakpoints', { node: node_name, username }); } catch {}
        const resp = await ipcApi.setSkillBreakpoints(username, node_name);
        try { console.log('[Breakpoint][UI] set_skill_breakpoints response', resp); } catch {}
        if (!resp.success) {
          console.warn('[Breakpoint] backend rejected toggle for', node_name);
        }
      } else {
        try { console.log('[Breakpoint][UI] calling clear_skill_breakpoints', { node: node_name, username }); } catch {}
        const resp = await ipcApi.clearSkillBreakpoints(username, node_name);
        try { console.log('[Breakpoint][UI] clear_skill_breakpoints response', resp); } catch {}
        if (!resp.success) {
          console.warn('[Breakpoint] backend rejected toggle for', node_name);
        }
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
      trigger="click"
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
              <Dropdown.Item onClick={handleHFlipToggle}>
                H-flip
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
