/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { MouseEvent } from 'react';

import {
  FlowNodeFormData,
  Form,
  FormModelV2,
  useNodeRender,
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

  const { height, width } = nodeSize ?? {};
  const nodeHeight = height ?? 0;

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
        width,
        height,
      }}
    >
      {/* Top-left drag handle to mimic other nodes' handle */}
      <div
        className="workflow-group-drag-handle"
        data-flow-editor-selectable="false"
        onMouseDown={(e) => {
          if (e.altKey) {
            e.stopPropagation();
            e.preventDefault();
            startDrag(e as MouseEvent);
          }
        }}
        title="Drag Group"
      />
      <Form control={formControl}>
        <>
          <GroupHeader
            onDrag={(e) => {
              if ((e as any).altKey) {
                startDrag(e as MouseEvent);
              }
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
              height: nodeHeight - HEADER_HEIGHT - HEADER_PADDING,
            }}
          />
        </>
      </Form>
    </div>
  );
};
