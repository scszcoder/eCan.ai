/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useContext, useCallback } from 'react';

import { WorkflowPortRender } from '@flowgram.ai/free-layout-editor';
import { useClientContext, useNode } from '@flowgram.ai/free-layout-editor';
import classnames from 'classnames';

import { FlowNodeMeta } from '../../typings';
import { useNodeRenderContext, usePortClick } from '../../hooks';
import { SidebarContext } from '../../context';
import { scrollToView } from './utils';
import { NodeWrapperStyle, BreakpointIcon, RunningIcon } from './styles';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useRunningNodeStore } from '../../stores/running-node-store';

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
  const { runningNodeId } = useRunningNodeStore();
  const isBreakpoint = breakpoints.includes(node.id);
  const isRunning = runningNodeId === node.id;

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
          selectNode(e);
          if (!isDragging) {
            sidebar.setNodeId(nodeRender.node.id);
            // 可选：将 isScrollToView 设为 true，可以让节点选中后滚动到画布中间
            // Optional: Set isScrollToView to true to scroll the node to the center of the canvas after it is selected.
            if (isScrollToView) {
              scrollToView(ctx, nodeRender.node);
            }
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
        }}
      >
        <RunningIcon />
        {children}
        {isBreakpoint && <BreakpointIcon />}
      </NodeWrapperStyle>
      {portsRender}
    </>
  );
};
