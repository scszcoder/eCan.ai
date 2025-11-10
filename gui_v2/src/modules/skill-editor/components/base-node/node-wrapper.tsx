/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useContext, useCallback, useEffect } from 'react';

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
  const isRunLike = (runtimeStatus === 'running' || runtimeStatus === 'resumed');
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

  // Read hFlip flag from form state first (menu writes here), fallback to node raw
  const hFlip = (() => {
    try {
      // @ts-ignore
      const fromForm = (form as any)?.state?.values?.data?.hFlip;
      if (typeof fromForm === 'boolean') return fromForm;
    } catch {}
    try {
      return !!(node as any)?.raw?.data?.hFlip;
    } catch {
      return false;
    }
  })();

  // Services for forcing visual refresh after anchor corrections
  const linesMgr = useService(WorkflowLinesManager);
  const documentSvc = useService(WorkflowDocument);

  // Stabilize port anchor sides according to hFlip after renders to prevent library resets
  useEffect(() => {
    const applyOnce = () => {
      try {
        (ports || []).forEach((p: any) => {
          const pid: string = p?.id || '';
          const isIn = pid.includes('port_input_');
          const isOut = pid.includes('port_output_');
          const targetLoc = hFlip
            ? (isIn ? 'right' : isOut ? 'left' : undefined)
            : (isIn ? 'left' : isOut ? 'right' : undefined);
          if (!targetLoc) return;
          const curr = (p as any)?.location ?? (p as any)?.position ?? (p as any)?.side;
          if (typeof (p as any)?.update === 'function' && curr !== targetLoc) {
            (p as any).update({ location: targetLoc, position: targetLoc, side: targetLoc });
          }
        });
        // For Condition nodes, make sure dynamic outputs are bound to their markers
        if (registry?.type === WorkflowNodeType.Condition) {
          const root = document.querySelector(`[data-node-id="${node.id}"]`);
          if (root) {
            const markerIf = root.querySelector('[data-port-id="if_out"]') as HTMLElement | null;
            const markerElse = root.querySelector('[data-port-id="else_out"]') as HTMLElement | null;
            (ports || []).forEach((p: any) => {
              const portKey = String((p?.portID ?? p?.portId) || '').toLowerCase();
              if (!p?.targetElement) {
                if (portKey === 'if_out' && markerIf) {
                  if (typeof p.setTargetElement === 'function') p.setTargetElement(markerIf);
                  else if (typeof p.update === 'function') p.update({ targetElement: markerIf });
                } else if (portKey === 'else_out' && markerElse) {
                  if (typeof p.setTargetElement === 'function') p.setTargetElement(markerElse);
                  else if (typeof p.update === 'function') p.update({ targetElement: markerElse });
                }
              }
            });
          }
        }
      } catch {}
      // Condition nodes handle their own port positioning via form-meta markers
      try { (linesMgr as any)?.forceUpdate?.(); } catch {}
      try { (documentSvc as any)?.fireRender?.(); } catch {}
    };

    // Apply now and again shortly after to override any late resets in the library
    applyOnce();
    const t1 = setTimeout(applyOnce, 60);
    const t2 = setTimeout(applyOnce, 160);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [hFlip, ports, node?.id]);

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
    
    const isCondOut = role === 'output' && portKey && (portKey.startsWith('if_') || portKey.startsWith('else_') || portKey.startsWith('elif_'));
    
    // Determine current anchor side from port entity
    const loc = (p as any)?.location ?? (p as any)?.position; // 'left' | 'right' | 'top' | 'bottom'
    const flipPort = (isInput && loc === 'right') || (isOutput && loc === 'left');
    const flipClass = flipPort ? 'se-port--hflip' : '';
    // Render all ports, including Condition outputs. For Condition, the port will portal into markers via targetElement.
    
    let wrapperStyle: React.CSSProperties | undefined;
    // For Condition outputs, the actual clickable port renders into the marker via portal,
    // so prevent the wrapper from catching mouse events.
    if (registry?.type === WorkflowNodeType.Condition && isOutput) {
      wrapperStyle = { pointerEvents: 'none' };
    }
    // Render real port elements for all ports; triangles overlay via CSS
    return (
      <div
        key={pid}
        className={`se-port se-port--${role} ${flipClass}`}
        data-se-port-id={pid}
        data-se-port-key={portKey}
        data-port-type={role}
        style={wrapperStyle}
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
