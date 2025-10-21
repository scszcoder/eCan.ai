/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useContext, useCallback, useEffect } from 'react';

import { WorkflowPortRender } from '@flowgram.ai/free-layout-editor';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import classnames from 'classnames';

import { FlowNodeMeta } from '../../typings';
import { useNodeRenderContext, usePortClick } from '../../hooks';
import { SidebarContext } from '../../context';
import { scrollToView } from './utils';
import { NodeWrapperStyle, BreakpointIcon, RunningIcon } from './styles';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRunningNodeStore } from '../../stores/running-node-store';
import { useNodeStatusStore } from '../../stores/node-status-store';

export interface NodeWrapperProps {
  isScrollToView?: boolean;
  children: React.ReactNode;
}

/**
 * Used for drag-and-drop/click events and ports rendering of nodes
 * 用于节点的拖拽/点击事件和点位渲染
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
  const { breakpoints } = useSkillInfoStore();
  const runningNodeId = useRunningNodeStore((state) => state.runningNodeId);
  const isBreakpoint = breakpoints.includes(node.id);
  const isRunning = runningNodeId === node.id;
  const endNodeId = useNodeStatusStore((s) => s.endNodeId);
  const endStatus = useNodeStatusStore((s) => s.endStatus);
  const isEndNode = endNodeId === node.id && !!endStatus;
  
  // Debug: Log when running state changes for this node
  useEffect(() => {
    if (isRunning) {
      console.log(`[NodeWrapper] Node '${node.id}' is now RUNNING`);
    }
  }, [isRunning, node.id]);

  const portsRender = ports.map((p) => (
    <WorkflowPortRender key={p.id} entity={p} onClick={!readonly ? onPortClick : undefined} />
  ));

  const handleMouseEnter = useCallback(() => {
    if (readonly) {
      return;
    }
  }, [readonly]);

  const handleMouseLeave = useCallback(() => {}, []);

  return (
    <>
      <NodeWrapperStyle
        className={classnames(selected ? 'selected' : '', { 'is-running': isRunning })}
        ref={nodeRef}
        draggable
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
            // 可选：将 isScrollToView 设为 true，可以让节点选中后滚动到画布中间
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
          // Thick red border to emphasize currently running node
          border: isRunning ? '3px solid #ff4d4f' : meta.wrapperStyle?.border,
          position: 'relative',
        }}
      >
        <RunningIcon />
        {children}
        {isBreakpoint && <BreakpointIcon />}
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
      </NodeWrapperStyle>
      {portsRender}
    </>
  );
};
