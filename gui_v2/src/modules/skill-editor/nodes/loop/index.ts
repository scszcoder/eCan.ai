/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { nanoid } from 'nanoid';
import {
  WorkflowNodeEntity,
  PositionSchema,
  FlowNodeTransformData,
} from '@flowgram.ai/free-layout-editor';

import { FlowNodeRegistry } from '../../typings';
import iconLoop from '../../assets/icon-loop.jpg';
import { formMeta } from './form-meta';
import { WorkflowNodeType } from '../constants';

let index = 0;
export const LoopNodeRegistry: FlowNodeRegistry = {
  type: WorkflowNodeType.Loop,
  info: {
    icon: iconLoop,
    description:
      'Used to repeatedly execute a series of tasks by setting the number of iterations and logic.',
  },
  meta: {
    /**
     * Mark as subcanvas
     * 子画布标记
     */
    isContainer: true,
    /**
     * Enable expand/collapse - default to expanded
     * EnabledExpand/折叠 - DefaultExpand
     */
    expandable: true,
    defaultExpanded: true,
    /**
     * Enable manual resizing
     * Enabled手动调整Size
     */
    resizable: true,
    /**
     * Auto fit to children - container grows to include all child nodes
     * 自动适应子节点 - Container自动增长以IncludeAll子节点
     */
    autoFit: true,
    /**
     * The subcanvas default size setting
     * 子画布DefaultSizeSettings
     */
    size: {
      width: 500,
      height: 300,
    },
    /**
     * Minimum size when resizing
     * 调整Size时的Minimum尺寸
     */
    minSize: {
      width: 300,
      height: 200,
    },
    /**
     * The subcanvas padding setting
     * 子画布 padding Settings
     */
    padding: () => ({
      top: 180,
      bottom: 60,
      left: 60,
      right: 60,
    }),
    /**
     * Controls the node selection status within the subcanvas
     * 控制子画布内的节点选中Status
     */
    selectable(node: WorkflowNodeEntity, mousePos?: PositionSchema): boolean {
      if (!mousePos) {
        return true;
      }
      const transform = node.getData<FlowNodeTransformData>(FlowNodeTransformData);
      // 鼠标开始时所在Position不包括When前节点时才Optional中
      return !transform.bounds.contains(mousePos.x, mousePos.y);
    },
    wrapperStyle: {
      minWidth: 'unset',
      width: '100%',
    },
  },
  onAdd() {
    const containerWidth = 500;
    const containerHeight = 300;
    const padding = { top: 180, bottom: 60, left: 60, right: 60 };
    
    // Calculate internal canvas size
    const canvasWidth = containerWidth - padding.left - padding.right; // 380
    const canvasHeight = containerHeight - padding.top - padding.bottom; // 120
    
    // Calculate vertical center of internal canvas
    const verticalCenter = canvasHeight / 2; // 60
    
    // Calculate horizontal positions in internal canvas coordinate system
    const leftX = 0; // Input port: left edge of canvas
    const rightX = canvasWidth; // Output port: right edge of canvas (380)
    
    return {
      id: `loop_${nanoid(5)}`,
      type: WorkflowNodeType.Loop,
      meta: {
        collapsed: false, // Start in expanded state
        expanded: true,   // Explicitly set expanded=true
      },
      data: {
        title: `Loop_${++index}`,
        // loop settings
        loopMode: 'loopFor', // 'loopFor' | 'loopWhile'
        loopCountExpr: '',   // used when loopMode === 'loopFor'
        loopWhileExpr: '',   // used when loopMode === 'loopWhile'
      },
      blocks: [
        {
          id: `block_start_${nanoid(5)}`,
          type: WorkflowNodeType.BlockStart,
          meta: {
            position: {
              x: leftX,  // 0: at left edge (input port)
              y: verticalCenter,   // 122: vertically centered
            },
          },
          data: {},
        },
        {
          id: `block_end_${nanoid(5)}`,
          type: WorkflowNodeType.BlockEnd,
          meta: {
            position: {
              x: rightX,   // 424: at right edge (output port)
              y: verticalCenter,   // 122: vertically centered (same as block_start)
            },
          },
          data: {},
        },
      ],
    };
  },
  formMeta,
};
