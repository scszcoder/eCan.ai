/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { MouseEvent, useState, useCallback } from 'react';

import {
  FlowNodeFormData,
  Form,
  FormModelV2,
  useNodeRender,
  FlowNodeTransformData,
  useClientContext,
  CommandService,
} from '@flowgram.ai/free-layout-editor';
import { useNodeSize } from '@flowgram.ai/free-container-plugin';

import { HEADER_HEIGHT, HEADER_PADDING } from '../constant';
import { UngroupButton } from './ungroup';
import { GroupTools } from './tools';
import { GroupTips } from './tips';
import { GroupHeader } from './header';
import { GroupBackground } from './background';

export const GroupNodeRender = () => {
  const { node, selected, selectNode, nodeRef, startDrag, onFocus, onBlur } = useNodeRender();
  const nodeSize = useNodeSize();
  const formModel = node.getData(FlowNodeFormData).getFormModel<FormModelV2>();
  const formControl = formModel?.formControl;
  const ctx = useClientContext();

  const { height, width } = nodeSize ?? {};
  const nodeHeight = height ?? 0;

  const [isResizing, setIsResizing] = useState(false);
  const [resizeDirection, setResizeDirection] = useState<string>('');
  const [currentWidth, setCurrentWidth] = useState(width || 560);
  const [currentHeight, setCurrentHeight] = useState(height || 400);

  // Use engine-provided size when not manually resizing to support auto-expansion
  const finalWidth = isResizing ? currentWidth : (width || 560);
  const finalHeight = isResizing ? currentHeight : (height || 400);

  const handleResizeStart = useCallback((direction: string) => (e: React.MouseEvent) => {
    console.log('Resize start:', direction, e.type, e.target); // Debug log
    e.stopPropagation();
    e.preventDefault();
    e.nativeEvent.stopImmediatePropagation();
    setIsResizing(true);
    setResizeDirection(direction);

    const startX = e.clientX;
    const startY = e.clientY;
    const startWidth = width || 560;
    const startHeight = height || 400;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      moveEvent.preventDefault();
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      let newWidth = startWidth;
      let newHeight = startHeight;

      // Calculate new dimensions based on resize direction
      if (direction.includes('e')) newWidth = Math.max(200, startWidth + deltaX);
      if (direction.includes('w')) newWidth = Math.max(200, startWidth - deltaX);
      if (direction.includes('s')) newHeight = Math.max(150, startHeight + deltaY);
      if (direction.includes('n')) newHeight = Math.max(150, startHeight - deltaY);

      // Update node size using direct DOM manipulation and local state
      if (nodeRef.current) {
        nodeRef.current.style.width = `${newWidth}px`;
        nodeRef.current.style.height = `${newHeight}px`;
        setCurrentWidth(newWidth);
        setCurrentHeight(newHeight);
        console.log(`Resizing to: ${newWidth}x${newHeight}`); // Debug log
      }
    };

    const handleMouseUp = (upEvent: globalThis.MouseEvent) => {
      console.log('Resize end'); // Debug log
      upEvent.preventDefault();
      setIsResizing(false);
      setResizeDirection('');
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  }, [node, width, height]);

  const renderResizeHandles = () => {
    if (!selected) return null;

    return (
      <>
        {/* Corner handles */}
        <div 
          className="workflow-group-resize-handle corner nw" 
          onMouseDown={handleResizeStart('nw')}
          onClick={(e) => {
            console.log('Handle clicked!', e);
            e.stopPropagation();
          }}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle corner ne" 
          onMouseDown={handleResizeStart('ne')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle corner sw" 
          onMouseDown={handleResizeStart('sw')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle corner se" 
          onMouseDown={handleResizeStart('se')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        
        {/* Edge handles */}
        <div 
          className="workflow-group-resize-handle edge n" 
          onMouseDown={handleResizeStart('n')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle edge s" 
          onMouseDown={handleResizeStart('s')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle edge w" 
          onMouseDown={handleResizeStart('w')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
        <div 
          className="workflow-group-resize-handle edge e" 
          onMouseDown={handleResizeStart('e')}
          data-flow-editor-selectable="false"
          style={{ pointerEvents: 'auto' }}
        />
      </>
    );
  };

  // Allow the group container to receive pointer events so it can be dragged by background/header

  return (
    <div
      className={`workflow-group-render ${selected ? 'selected' : ''}`}
      ref={nodeRef}
      data-group-id={node.id}
      data-node-selected={String(selected)}
      onMouseDown={selectNode}
      onClick={(e) => {
        selectNode(e);
      }}
      style={{
        width: finalWidth,
        height: finalHeight,
      }}
    >
      {/* Top-left drag handle to mimic other nodes' handle */}
      <div
        className="workflow-group-drag-handle"
        data-flow-editor-selectable="false"
        onMouseDown={(e) => {
          e.stopPropagation();
          e.preventDefault();
          startDrag(e as MouseEvent);
        }}
        title="Drag Group"
      />
      <Form control={formControl}>
        <>
          <GroupHeader
            onDrag={(e) => {
              startDrag(e as MouseEvent);
            }}
            onFocus={onFocus}
            onBlur={onBlur}
            style={{
              height: HEADER_HEIGHT,
            }}
          >
            <GroupTools />
          </GroupHeader>
          <GroupTips />
          <UngroupButton node={node} />
          <GroupBackground
            node={node}
            onDrag={(e) => startDrag(e as MouseEvent)}
            style={{
              top: HEADER_HEIGHT + HEADER_PADDING,
              height: finalHeight - HEADER_HEIGHT - HEADER_PADDING,
            }}
          />
        </>
      </Form>
      {/* Render resize handles when selected */}
      {renderResizeHandles()}
    </div>
  );
};
