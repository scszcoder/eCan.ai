/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */
import {
    FlowNodeBaseType,
    WorkflowNodeEntity,
    PositionSchema,
    FlowNodeTransformData,
    nanoid,
  } from '@flowgram.ai/free-layout-editor';
  
  import { FlowNodeRegistry } from '../../typings';
  import { WorkflowNodeType } from '../constants';
  import iconBasic from '../../assets/icon-basic.png';
  
  let index = 0;
  export const GroupNodeRegistry: FlowNodeRegistry = {
    type: 'group',
    info: {
      icon: iconBasic,
      description: 'A container node used to group related nodes together.',
    },
    meta: {
      //renderKey: FlowNodeBaseType.GROUP,
      renderKey: FlowNodeBaseType.GROUP,
      defaultPorts: [],
      isContainer: true,
      disableSideBar: false,
      // Enable context menu by allowing delete and copy
      deleteDisable: false,
      copyDisable: false,
      // Make the group resizable
      resizable: true,
      size: {
        width: 560,
        height: 400,
      },
      // Set minimum size for resizing
      minSize: {
        width: 200,
        height: 150,
      },
      padding: () => ({
        top: 80,
        bottom: 40,
        left: 65,
        right: 65,
      }),
      selectable(node: WorkflowNodeEntity, mousePos?: PositionSchema): boolean {
        if (!mousePos) {
          return true;
        }
        const transform = node.getData<FlowNodeTransformData>(FlowNodeTransformData);
        const bounds = transform.bounds;

        // Check if mouse is in the header area (top 80px for dragging)
        const headerHeight = 80;
        const isInHeader = mousePos.y >= bounds.y && mousePos.y <= bounds.y + headerHeight;

        // Allow selection if in header area or if clicking outside content area
        if (isInHeader) {
          return true;
        }

        // Allow selection if clicking on the border/edge areas
        const borderWidth = 10;
        const isOnBorder =
          mousePos.x <= bounds.x + borderWidth ||
          mousePos.x >= bounds.x + bounds.width - borderWidth ||
          mousePos.y <= bounds.y + borderWidth ||
          mousePos.y >= bounds.y + bounds.height - borderWidth;

        if (isOnBorder) {
          return true;
        }

        // Don't select if clicking in the content area (to allow selecting child nodes)
        return !bounds.contains(mousePos.x, mousePos.y);
      },
      expandable: false,
    },
    formMeta: {
      render: () => <></>,
    },
    onAdd() {
      return {
        //type: FlowNodeBaseType.GROUP,
        type: 'group',
        id: `group_${nanoid(5)}`,
        meta: {
//           position: {
//             x: 0,
//             y: 0,
//           },
        },
        data: {
          color: 'Green',
          title: `Group_${++index}`,
        },
      };
    },
  };