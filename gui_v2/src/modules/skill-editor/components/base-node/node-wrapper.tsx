/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useContext, useCallback, useEffect, useMemo } from 'react';

import { WorkflowPortRender } from '@flowgram.ai/free-layout-editor';
import { useClientContext, useService, WorkflowDocument, WorkflowLinesManager } from '@flowgram.ai/free-layout-editor';
import classnames from 'classnames';

import { FlowNodeMeta, FlowNodeRegistry } from '../../typings';
import { WorkflowNodeType } from '../../nodes/constants';
import { useNodeRenderContext, usePortClick } from '../../hooks';
import { SidebarContext } from '../../context';
import { scrollToView } from './utils';
import { NodeWrapperStyle, BreakpointIcon, RunningIcon, PausedIcon, StatusBadgeContainer } from './styles';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRunningNodeStore } from '../../stores/running-node-store';
import { useNodeStatusStore } from '../../stores/node-status-store';
import { useRuntimeStateStore } from '../../stores/runtime-state-store';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { usePortSideService } from '../../services/port-side';

export interface NodeWrapperProps {
  isScrollToView?: boolean;
  children: React.ReactNode;
}

/**
 * Used for drag-and-drop/click events and ports rendering of nodes
 * Used for节点的Drag/ClickEvent和点位Render
 */
export const NodeWrapper: React.FC<NodeWrapperProps> = (props) => {
  const { children, isScrollToView = false } = props;
  const nodeRender = useNodeRenderContext();
  const { node, selected, startDrag, ports, selectNode, nodeRef, onFocus, onBlur, readonly } =
    nodeRender;
  const [isDragging, setIsDragging] = useState(false);
  const sidebar = useContext(SidebarContext);
  const form = nodeRender.form;
  const ctx = useClientContext();
  const onPortClick = usePortClick();
  const meta = node.getNodeMeta<FlowNodeMeta>();
  const registry = node.getNodeRegistry<FlowNodeRegistry>();
  const { breakpoints } = useSkillInfoStore();
  const runningNodeId = useRunningNodeStore((state) => state.runningNodeId);
  const isBreakpoint = breakpoints.includes(node.id);
  const isRunning = runningNodeId === node.id;
  const endNodeId = useNodeStatusStore((s) => s.endNodeId);
  const endStatus = useNodeStatusStore((s) => s.endStatus);
  const isEndNode = endNodeId === node.id && !!endStatus;
  const runtimeEntry = useRuntimeStateStore((s) => s.getNodeRuntimeState(node.id));
  const runtimeStatus = runtimeEntry?.status;
  const stateObj: any = runtimeEntry?.state || {};

  // Determine paused vs running from runtime status
  const isPausedLike = (runtimeStatus === 'paused' || runtimeStatus === 'breakpoint' || runtimeStatus === 'stalled');
  const _isRunLike = (runtimeStatus === 'running' || runtimeStatus === 'resumed'); // Reserved for future use
  // For glow class we keep coupling to runningNodeId to avoid global blinking
  const isBreakpointStalled = isRunning && isPausedLike;

  // Compute result badge severity
  let resultSeverity: 'error' | 'warning' | 'success' | 'none' = 'none';
  if (stateObj?.errors?.length || stateObj?.error) {
    resultSeverity = 'error';
  } else if (stateObj?.warnings?.length || stateObj?.warning) {
    resultSeverity = 'warning';
  } else if (runtimeStatus === 'completed' || stateObj?.success === true) {
    resultSeverity = 'success';
  }
  
  // // Debug: Log when running state changes for this node
  // useEffect(() => {
  //   if (isRunning) {
  //     console.log(`[NodeWrapper] Node '${node.id}' is now RUNNING`);
  //   }
  // }, [isRunning, node.id]);

  const storeFlip = useNodeFlipStore(
    useCallback((state) => state.flippedNodes.has(node.id), [node.id])
  );

  const persistedFlip = (() => {
    try {
      // @ts-ignore
      const fromForm = (form as any)?.state?.values?.data?.hFlip;
      if (typeof fromForm === 'boolean') return fromForm;
    } catch {}
    try {
      const fromJson = (node as any)?.json?.data?.hFlip;
      if (typeof fromJson === 'boolean') return fromJson;
    } catch {}
    try {
      const fromRaw = (node as any)?.raw?.data?.hFlip;
      if (typeof fromRaw === 'boolean') return fromRaw;
    } catch {}
    return false;
  })();

  const hFlip = storeFlip || persistedFlip;

  // Ensure store reflects persisted flip state (e.g. when loading from disk)
  useEffect(() => {
    if (persistedFlip && !storeFlip) {
      try {
        useNodeFlipStore.getState().setFlipped(node.id, true);
      } catch {}
    }
  }, [persistedFlip, storeFlip, node.id]);

  // Services for forcing visual refresh after anchor corrections
  const linesMgr = useService(WorkflowLinesManager);
  const documentSvc = useService(WorkflowDocument);
  const { canFlipAnchors, applyHFlipAnchors } = usePortSideService();

  const flipDebug = useMemo(() => {
    try {
      // @ts-ignore
      return (window as any).__SE_DEBUG_FLIP__ === true;
    } catch {
      return false;
    }
  }, []);

  // Stabilize port anchor sides according to hFlip after renders to prevent library resets
  useEffect(() => {
    let cancelled = false;
    let rafId: number | null = null;

    const resolvePorts = (): any[] => {
      if (ports?.length) return ports as any[];
      try {
        const all = (documentSvc as any)?.getAllPorts?.() || [];
        return all.filter((p: any) => p?.node?.id === node.id);
      } catch {
        return [];
      }
    };

    const applyOnce = async () => {
      const portEntities = resolvePorts();
      if (!portEntities.length) {
        // Try again on next frame; ports may not be ready yet
        if (flipDebug) {
          try {
            console.log('[Flip][NodeWrapper] Ports not ready, retrying', { nodeId: node.id, hFlip });
          } catch {}
        }
        rafId = window.requestAnimationFrame(applyOnce);
        return;
      }

      try {
        if (registry?.type !== WorkflowNodeType.Condition && canFlipAnchors()) {
          if (flipDebug) {
            try {
              console.log('[Flip][NodeWrapper] Applying anchor command', { nodeId: node.id, hFlip });
            } catch {}
          }
          await applyHFlipAnchors(node, hFlip);
          if (cancelled) {
            return;
          }
        }
      } catch {}

      try {
        portEntities.forEach((p: any) => {
          const pid: string = p?.id || '';
          const isIn = pid.includes('port_input_');
          const isOut = pid.includes('port_output_');
          if (registry?.type === WorkflowNodeType.Condition && isOut) return;
          const targetLoc = hFlip
            ? (isIn ? 'right' : isOut ? 'left' : undefined)
            : (isIn ? 'left' : isOut ? 'right' : undefined);
          if (!targetLoc) return;
          const curr = (p as any)?.location ?? (p as any)?.position ?? (p as any)?.side;
          if (typeof (p as any)?.update === 'function' && curr !== targetLoc) {
            (p as any).update({ location: targetLoc, position: targetLoc, side: targetLoc });
          }
          try { p.validate?.(); } catch {}
          try {
            const lines = (p as any)?.allLines ?? (p as any)?.lines;
            if (lines && typeof lines.forEach === 'function') {
              lines.forEach((ln: any) => {
                try { ln.validate?.(); } catch {}
                // Force update line render data to fix add button position after flip
                try {
                  // Try to get renderData from line's data map
                  const dataMap = (ln as any)?._dataMap ?? (ln as any)?.dataMap;
                  if (dataMap) {
                    dataMap.forEach?.((data: any) => {
                      if (data?.update && typeof data.update === 'function') {
                        data.update();
                      }
                    });
                  }
                } catch {}
              });
            }
          } catch {}
          if (flipDebug) {
            try {
              console.log('[Flip][NodeWrapper] Port updated', {
                nodeId: node.id,
                portId: pid,
                isInput: !!isIn,
                isOutput: !!isOut,
                targetLoc,
                prevLoc: curr,
                nextLoc: (p as any)?.location ?? (p as any)?.position ?? (p as any)?.side,
              });
            } catch {}
          }
        });

        // Condition Node ports are now dynamically rendered via form-meta.tsx
        // No legacy port binding needed
      } catch {}

      try { (linesMgr as any)?.forceUpdate?.(); } catch {}
      try { (documentSvc as any)?.fireContentChange?.(); } catch {}
      if (flipDebug) {
        try {
          console.log('[Flip][NodeWrapper] Stabilization complete', { nodeId: node.id, hFlip });
        } catch {}
      }
    };

    rafId = window.requestAnimationFrame(applyOnce);

    return () => {
      cancelled = true;
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
      }
    };
  }, [hFlip, ports, node?.id, registry?.type, canFlipAnchors, applyHFlipAnchors, linesMgr, documentSvc]);

  // Ensure DOM port wrappers carry hflip class after anchor updates (handles late rerenders)
  useEffect(() => {
    const applyDomFlipClass = () => {
      try {
        const nodeEl = document.querySelector(`[data-node-id="${node.id}"]`);
        if (!nodeEl) return;
        const wrapperEls = nodeEl.querySelectorAll('.se-port');
        wrapperEls.forEach((el) => {
          const role = el.classList.contains('se-port--input') ? 'input' : el.classList.contains('se-port--output') ? 'output' : 'unknown';
          if (!['input', 'output'].includes(role)) return;
          if (hFlip) {
            el.classList.add('se-port--hflip');
          } else {
            el.classList.remove('se-port--hflip');
          }
        });
      } catch {}
    };

    const raf = window.requestAnimationFrame(() => {
      applyDomFlipClass();
      window.requestAnimationFrame(applyDomFlipClass);
    });

    return () => {
      window.cancelAnimationFrame(raf);
    };
  }, [node.id, hFlip, ports]);

  const portsRender = ports.map((p) => {
    const pid = (p as any)?.id as string;
    const isInput = typeof pid === 'string' && pid.includes('port_input_');
    const isOutput = typeof pid === 'string' && pid.includes('port_output_');
    const role = isInput ? 'input' : isOutput ? 'output' : 'unknown';
    
    // Extract port key from the ID if not directly available
    let portKey = (p as any)?.portID ?? (p as any)?.portId ?? (p as any)?.key;
    if (!portKey && pid) {
      // Try to extract key from port id like "port_output_condition_xyz_else_abc123"
      const parts = pid.split('_');
      if (parts.length > 3) {
        // Get everything after "port_output_condition_nodeId_"
        const nodeIdParts = pid.match(/port_output_condition_[^_]+_(.*)/);
        if (nodeIdParts && nodeIdParts[1]) {
          portKey = nodeIdParts[1];
        }
      }
    }
    
    // Note: isCondOut was used for legacy condition port handling, now handled via form-meta.tsx
    
    // Determine flip class based on horizontal flip state
    const desiredFlip = hFlip && (isInput || isOutput);
    const flipClass = desiredFlip ? 'se-port--hflip' : '';
    // For Condition outputs, avoid rendering until bound to a marker; render only the portalized port
    if (registry?.type === WorkflowNodeType.Condition && isOutput) {
      const te = (p as any)?.targetElement;
      if (!te) {
        return null;
      }
      return (
        <div
          key={pid}
          className={`se-port se-port--output ${flipClass} se-port--has-icon`}
          data-se-port-id={pid}
          data-se-port-key={portKey}
          data-port-type="output"
        >
          <WorkflowPortRender
            entity={p}
            onClick={!readonly ? onPortClick : undefined}
          />
        </div>
      );
    }
    // Default: render wrapper + port
    const showPortIcon = isInput || isOutput;
    const hasIconClass = showPortIcon ? 'se-port--has-icon' : '';

    return (
      <div
        key={pid}
        className={`se-port se-port--${role} ${flipClass} ${hasIconClass}`}
        data-se-port-id={pid}
        data-se-port-key={portKey}
        data-port-type={role}
      >
        <WorkflowPortRender
          entity={p}
          onClick={!readonly ? onPortClick : undefined}
        />
      </div>
    );
  });


  // Phase 0 diagnostics: log port entities when selected (toggle with window.__SE_DEBUG_PORTS__ = true in devtools)
  useEffect(() => {
    try {
      // @ts-ignore
      const dbg = (window as any).__SE_DEBUG_PORTS__ === true;
      if (dbg && selected && ports?.length) {
        // Shallow snapshot to avoid circular refs flooding console
        const snapshot = ports.map((p: any) => ({
          id: p?.id,
          type: p?.type,
          direction: p?.direction,
          side: p?.side,
          position: p?.position,
          inout: p?.inout,
          cls: p?.className,
          meta: p?.meta,
        }));
        // Minimal node info
        console.log('[SkillEditor][Phase0] Ports for node', node.id, snapshot);

        // Also log DOM info for our wrappers to capture class and size
        const wrappers = Array.from(document.querySelectorAll(`.se-port[data-se-port-id]`)) as HTMLElement[];
        const domInfo = wrappers.map((el) => ({
          id: el.getAttribute('data-se-port-id'),
          classList: Array.from(el.classList),
          bbox: el.getBoundingClientRect(),
          child: el.firstElementChild ? {
            tag: el.firstElementChild.tagName,
            classList: Array.from(el.firstElementChild.classList || []),
          } : null,
        }));
        console.log('[SkillEditor][Phase0] Port DOM wrappers', domInfo);
      }
    } catch {}
  }, [selected, ports, node?.id]);

  const handleMouseEnter = useCallback(() => {
    if (readonly) {
      return;
    }
  }, [readonly]);

  const handleMouseLeave = useCallback(() => {}, []);

  return (
    <>
      <NodeWrapperStyle
        className={classnames(
          selected ? 'selected' : '',
          hFlip ? 'se-node--hflip' : '',
          {
            'is-running': isRunning && !isBreakpointStalled,
            'is-breakpoint-stalled': isBreakpointStalled,
          }
        )}
        ref={nodeRef}
        draggable
        data-node-id={node.id}
        onDragStart={(e) => {
          startDrag(e);
          setIsDragging(true);
        }}
        onTouchStart={(e) => {
          startDrag(e as unknown as React.MouseEvent);
          setIsDragging(true);
        }}
        onClick={(e) => {
          // Prevent upstream click handlers from racing selection/close behavior
          e.stopPropagation();
          // Single-click only handles node selection, not sidebar opening
          selectNode(e);
          if (!isDragging && isScrollToView) {
            // Optional：将 isScrollToView 设为 true，Can让节点选中后Scroll到画布中间
            // Optional: Set isScrollToView to true to scroll the node to the center of the canvas after it is selected.
            scrollToView(ctx, nodeRender.node);
          }
        }}
        onDoubleClick={(e) => {
          // Double-click opens the node editor/sidebar
          e.stopPropagation();
          if (!isDragging) {
            sidebar.setNodeId(nodeRender.node.id);
          }
        }}
        onMouseUp={() => setIsDragging(false)}
        onFocus={onFocus}
        onBlur={onBlur}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        data-node-selected={String(selected)}
        style={{
          ...meta.wrapperStyle,
          outline: form?.state.invalid ? '1px solid red' : 'none',
          // Let animations control border color and glow; avoid forcing red border when running
          border: meta.wrapperStyle?.border,
          position: 'relative',
        }}
      >
        {/* Stickman: explicit render based on runtimeStatus with display override (bypasses CSS class timing) */}
        {!isEndNode && (
          isRunning && isPausedLike
            ? <PausedIcon key={`${node.id}-paused`} style={{ display: 'block' }} />
            : (isRunning && !isPausedLike) ? (
              <RunningIcon key={`${node.id}-running`} style={{ display: 'block' }} />
            ) : null
        )}

        {children}
        {isBreakpoint && <BreakpointIcon />}

        {/* Top-right result badge */}
        {resultSeverity !== 'none' && !isEndNode && (
          <StatusBadgeContainer
            title={
              resultSeverity === 'error'
                ? 'Node has errors'
                : resultSeverity === 'warning'
                ? 'Node has warnings'
                : 'Node succeeded'
            }
          >
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: 8,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 12,
                fontWeight: 700,
                color: '#fff',
                background:
                  resultSeverity === 'error'
                    ? '#e53935' // red
                    : resultSeverity === 'warning'
                    ? '#fb8c00' // orange
                    : '#43a047', // green
              }}
            >
              {resultSeverity === 'error' ? '✕' : resultSeverity === 'warning' ? '!' : '✓'}
            </div>
          </StatusBadgeContainer>
        )}

        {isEndNode && (
          <div
            style={{
              position: 'absolute',
              top: -8,
              right: -8,
              width: 22,
              height: 22,
              borderRadius: 11,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: endStatus === 'completed' ? '#52c41a' : '#ff4d4f',
              color: 'white',
              fontSize: 14,
              fontWeight: 700,
              border: '2px solid white',
              boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
              zIndex: 2,
            }}
            title={endStatus === 'completed' ? 'Completed' : 'Failed'}
          >
            {endStatus === 'completed' ? '✓' : '✕'}
          </div>
        )}
        {/* condition output triangles are rendered in form-meta markers */}
      </NodeWrapperStyle>
      {portsRender}
    </>
  );
}
