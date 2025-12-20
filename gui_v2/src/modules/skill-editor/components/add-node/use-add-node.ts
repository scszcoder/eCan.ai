/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */
import { useCallback, useRef } from 'react';

import { NodePanelResult, WorkflowNodePanelService } from '@flowgram.ai/free-node-panel-plugin';
import {
  useService,
  WorkflowDocument,
  usePlayground,
  PositionSchema,
  WorkflowNodeEntity,
  WorkflowSelectService,
  WorkflowNodeJSON,
  getAntiOverlapPosition,
  WorkflowNodeMeta,
  FlowNodeBaseType,
} from '@flowgram.ai/free-layout-editor';
import { nodeRegistries } from '../../nodes';

// hook to get panel position from mouse event - 从鼠标EventGet面板Position的 hook
const useGetPanelPosition = () => {
  const playground = usePlayground();
  return useCallback(
    (targetBoundingRect: DOMRect): PositionSchema =>
      // convert mouse position to canvas position - 将鼠标PositionConvert为画布Position
      playground.config.getPosFromMouseEvent({
        clientX: targetBoundingRect.left + 64,
        clientY: targetBoundingRect.top - 7,
      }),
    [playground]
  );
};
// hook to handle node selection - Process节点Select的 hook
const useSelectNode = () => {
  const selectService = useService(WorkflowSelectService);
  return useCallback(
    (node?: WorkflowNodeEntity) => {
      if (!node) {
        return;
      }
      // select the target node - Select目标节点
      selectService.selectNode(node);
    },
    [selectService]
  );
};

const getContainerNode = (selectService: WorkflowSelectService) => {
  const { activatedNode } = selectService;
  if (!activatedNode) {
    return;
  }
  const { isContainer } = activatedNode.getNodeMeta<WorkflowNodeMeta>();
  if (isContainer) {
    return activatedNode;
  }
  const parentNode = activatedNode.parent;
  if (!parentNode || parentNode.flowNodeType === FlowNodeBaseType.ROOT) {
    return;
  }
  return parentNode;
};

// main hook for adding new nodes - Add新节点的主 hook
export const useAddNode = () => {
  const workflowDocument = useService(WorkflowDocument);
  const nodePanelService = useService<WorkflowNodePanelService>(WorkflowNodePanelService);
  const selectService = useService(WorkflowSelectService);
  const playground = usePlayground();
  const getPanelPosition = useGetPanelPosition();
  const select = useSelectNode();
  const placingRef = useRef<null | { nodeType: string; nodeJSON?: WorkflowNodeJSON; containerNodeId?: string }>(null);
  const lastMouseRef = useRef<{ clientX: number; clientY: number } | null>(null);
  const ghostElRef = useRef<HTMLDivElement | null>(null);
  const ghostTitleRef = useRef<HTMLDivElement | null>(null);
  const ghostIconRef = useRef<HTMLImageElement | null>(null);

  const getGridSize = () => {
    const anyCfg: any = playground.config as any;
    const base = typeof anyCfg?.gridSize === 'number' ? anyCfg.gridSize : 16;
    const zoom = typeof playground.config.zoom === 'number' ? playground.config.zoom : 1;
    return Math.max(4, base * zoom);
  };

  const cancelPlacing = () => {
    placingRef.current = null;
    try {
      window.removeEventListener('mousemove', trackMouse, true);
      window.removeEventListener('click', placeOnClick, true);
      window.removeEventListener('keydown', onKeyDown, true);
      window.removeEventListener('contextmenu', onContextMenu, true);
      document.body.style.cursor = '';
      if (ghostElRef.current && ghostElRef.current.parentElement) {
        ghostElRef.current.parentElement.removeChild(ghostElRef.current);
      }
      ghostElRef.current = null;
    } catch {}
  };

  const trackMouse = (e: MouseEvent) => {
    lastMouseRef.current = { clientX: e.clientX, clientY: e.clientY };
    updateGhostPos(e.clientX, e.clientY);
  };

  const placeOnClick = (e: MouseEvent) => {
    if (!placingRef.current) return;
    // Avoid placing when clicking inside the node-type panel or other UI overlays
    const target = e.target as HTMLElement | null;
    const inNodePanel = !!target?.closest?.('.node-panel, [data-node-panel]');
    if (inNodePanel) return;
    // Map click to canvas coordinates
    const pos = playground.config.getPosFromMouseEvent({ clientX: e.clientX, clientY: e.clientY });
    const { nodeType, nodeJSON, containerNodeId } = placingRef.current;
    const node: WorkflowNodeEntity = workflowDocument.createWorkflowNodeByType(
      nodeType,
      pos,
      nodeJSON ?? ({} as WorkflowNodeJSON),
      containerNodeId
    );
    // Do NOT auto-select to avoid popping sidebar instantly
    // Users can click the node afterwards to select/open editor.
    cancelPlacing();
    e.preventDefault();
    e.stopPropagation();
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (!placingRef.current) return;
    if (e.key === 'Escape') {
      cancelPlacing();
      e.preventDefault();
      e.stopPropagation();
    }
  };

  const onContextMenu = (e: MouseEvent) => {
    if (!placingRef.current) return;
    // Right-click cancels placement
    cancelPlacing();
    e.preventDefault();
    e.stopPropagation();
  };

  const ensureGhost = () => {
    if (ghostElRef.current) return ghostElRef.current;
    const el = document.createElement('div');
    el.style.position = 'fixed';
    el.style.left = '0px';
    el.style.top = '0px';
    el.style.transform = 'translate(-50%, -50%)';
    el.style.pointerEvents = 'none';
    el.style.zIndex = '1500'; // Drag预览层级
    el.style.width = '280px';
    el.style.height = '120px';
    el.style.border = '1px dashed rgba(82,100,154,0.5)';
    el.style.borderRadius = '8px';
    el.style.background = 'rgba(255,255,255,0.5)';
    el.style.boxShadow = '0 2px 8px rgba(0,0,0,0.12)';
    el.style.display = 'flex';
    el.style.flexDirection = 'column';
    // simple pulse animation
    el.style.animation = 'ghostPulse 1.2s ease-in-out infinite';
    const style = document.createElement('style');
    style.textContent = `@keyframes ghostPulse { 0% { opacity: 0.6 } 50% { opacity: 0.9 } 100% { opacity: 0.6 } }`;
    document.head.appendChild(style);
    // header
    const header = document.createElement('div');
    header.style.height = '28px';
    header.style.borderTopLeftRadius = '8px';
    header.style.borderTopRightRadius = '8px';
    header.style.background = '#fff';
    header.style.borderBottom = '1px solid rgba(82,100,154,0.3)';
    header.style.display = 'flex';
    header.style.alignItems = 'center';
    header.style.gap = '6px';
    header.style.padding = '0 8px';
    const icon = document.createElement('img');
    icon.style.width = '14px';
    icon.style.height = '14px';
    icon.style.borderRadius = '3px';
    icon.style.objectFit = 'cover';
    const title = document.createElement('div');
    title.style.fontSize = '12px';
    title.style.fontWeight = '600';
    title.style.color = '#334155';
    title.textContent = placingRef.current?.nodeType || 'Node';
    header.appendChild(icon);
    header.appendChild(title);
    ghostTitleRef.current = title;
    ghostIconRef.current = icon as HTMLImageElement;
    // body hint
    const body = document.createElement('div');
    body.style.flex = '1';
    body.style.display = 'flex';
    body.style.alignItems = 'center';
    body.style.justifyContent = 'center';
    body.style.color = '#52649a';
    body.style.fontSize = '12px';
    body.style.fontWeight = '600';
    body.textContent = 'Click to place';
    el.appendChild(header);
    el.appendChild(body);
    document.body.appendChild(el);
    ghostElRef.current = el;
    return el;
  };

  const updateGhostPos = (clientX: number, clientY: number) => {
    const el = ensureGhost();
    // snap to grid in screen space (grid * zoom)
    const g = getGridSize();
    const sx = Math.round(clientX / g) * g;
    const sy = Math.round(clientY / g) * g;
    el.style.left = `${sx}px`;
    el.style.top = `${sy}px`;
  };

  return useCallback(
    async (targetBoundingRect: DOMRect): Promise<void> => {
      // calculate panel position based on target element - 根据目标元素计算面板Position
      const panelPosition = getPanelPosition(targetBoundingRect);
      const containerNode = getContainerNode(selectService);
      await new Promise<void>((resolve) => {
        // call the node panel service to show the panel - 调用节点面板Service来Display面板
        nodePanelService.callNodePanel({
          position: panelPosition,
          enableMultiAdd: true,
          containerNode,
          panelProps: {},
          // handle node selection from panel - Process从面板中Select节点
          onSelect: async (panelParams?: NodePanelResult) => {
            if (!panelParams) {
              return;
            }
            const { nodeType, nodeJSON } = panelParams;
            // Enter click-to-place mode: next canvas click will drop the node at mouse position
            placingRef.current = { nodeType, nodeJSON, containerNodeId: containerNode?.id };
            try {
              window.addEventListener('mousemove', trackMouse, true);
              window.addEventListener('click', placeOnClick, true);
              window.addEventListener('keydown', onKeyDown, true);
              window.addEventListener('contextmenu', onContextMenu, true);
              document.body.style.cursor = 'grabbing';
              // initialize ghost at current mouse pos if available
              const ghost = ensureGhost();
              if (ghostTitleRef.current) ghostTitleRef.current.textContent = nodeType;
              try {
                const reg = nodeRegistries.find(r => r.type === nodeType);
                if (reg?.info?.icon && ghostIconRef.current) {
                  ghostIconRef.current.src = reg.info.icon as any;
                } else if (ghostIconRef.current) {
                  ghostIconRef.current.removeAttribute('src');
                }
              } catch {}
              const last = lastMouseRef.current;
              if (last) {
                updateGhostPos(last.clientX, last.clientY);
              } else {
                // fallback to center until the first mouse move
                updateGhostPos(Math.round(window.innerWidth / 2), Math.round(window.innerHeight / 2));
              }
            } catch {}
          },
          // handle panel close - Process面板Close
          onClose: () => {
            resolve();
          },
        });
      });
    },
    [getPanelPosition, nodePanelService, playground.config.zoom, workflowDocument]
  );
};
