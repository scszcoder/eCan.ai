/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { WorkflowNodeEntity, WorkflowNodeLinesData, FlowNodeTransformData } from '@flowgram.ai/free-layout-editor';

// Collapsed size constants - must match form-meta.tsx
// 折叠尺寸常量 - Must与 form-meta.tsx 中的Definition一致
export const LOOP_COLLAPSED_WIDTH = 400;

// Expanded size constants
export const LOOP_EXPANDED_WIDTH = 500;
export const LOOP_EXPANDED_HEIGHT = 300;

// Padding constants
export const LOOP_PADDING = { top: 120, bottom: 60, left: 60, right: 60 };

// Store original block positions and expanded size for each loop node
const originalBlockPositions = new Map<string, { blockStartPos: { x: number; y: number }, blockEndPos: { x: number; y: number } }>();
const originalExpandedSize = new Map<string, { width: number; height: number }>();

export function toggleLoopExpanded(
  node: WorkflowNodeEntity,
  expanded: boolean = node.transform.collapsed
) {
  const prePosition = {
    x: node.transform.position.x,
    y: node.transform.position.y,
  };
  node.transform.collapsed = !expanded;

  // Get transform data and meta to update size
  const transform = node.getData(FlowNodeTransformData);
  const meta = node.getNodeMeta?.();

  // Save original block positions and expanded size before collapsing
  if (!expanded && node.blocks && node.blocks.length >= 2) {
    const blockStart = node.blocks[0];
    const blockEnd = node.blocks[1];

    // Only save if not already saved (to preserve the original expanded positions)
    if (!originalBlockPositions.has(node.id)) {
      originalBlockPositions.set(node.id, {
        blockStartPos: {
          x: blockStart.transform.position.x,
          y: blockStart.transform.position.y,
        },
        blockEndPos: {
          x: blockEnd.transform.position.x,
          y: blockEnd.transform.position.y,
        },
      });
    }

    // Save the current expanded size (actual size before collapsing)
    if (!originalExpandedSize.has(node.id)) {
      originalExpandedSize.set(node.id, {
        width: transform.bounds?.width || LOOP_EXPANDED_WIDTH,
        height: transform.bounds?.height || LOOP_EXPANDED_HEIGHT,
      });
    }
  }

  if (!expanded) {
    // Collapsing
    // Get current height to preserve it during collapse
    const currentHeight = transform?.bounds?.height || LOOP_EXPANDED_HEIGHT;
    
    // Disable autoFit first to prevent auto-resizing
    if (meta) {
      meta.autoFit = false;

      // Update wrapper style to fixed width
      if (meta.wrapperStyle) {
        meta.wrapperStyle.width = `${LOOP_COLLAPSED_WIDTH}px`;
        meta.wrapperStyle.minWidth = `${LOOP_COLLAPSED_WIDTH}px`;
        meta.wrapperStyle.maxWidth = `${LOOP_COLLAPSED_WIDTH}px`;
      }
    }

    // Update meta size first
    if (meta && meta.size) {
      meta.size.width = LOOP_COLLAPSED_WIDTH;
      meta.size.height = currentHeight;
    }

    // Update position and size - framework should handle port and line updates automatically
    node.transform.transform.update({
      position: {
        x: prePosition.x - node.transform.padding.left,
        y: prePosition.y - node.transform.padding.top,
      },
      size: {
        width: LOOP_COLLAPSED_WIDTH,
        height: currentHeight,
      },
      origin: {
        x: 0,
        y: 0,
      },
    });
  } else {
    // Expanding
    // Restore the original expanded size (before it was collapsed)
    const savedSize = originalExpandedSize.get(node.id);
    const expandedWidth = savedSize?.width || LOOP_EXPANDED_WIDTH;
    const expandedHeight = savedSize?.height || LOOP_EXPANDED_HEIGHT;

    // Keep autoFit disabled to avoid double resize animation
    if (meta) {
      meta.autoFit = false;

      // Update wrapper style to 100% width
      if (meta.wrapperStyle) {
        meta.wrapperStyle.width = '100%';
        meta.wrapperStyle.minWidth = 'unset';
        meta.wrapperStyle.maxWidth = 'unset';
      }
    }

    // Single update: position and size together to minimize reflows
    // This will automatically update bounds and trigger only ONE reflow
    node.transform.transform.update({
      position: {
        x: prePosition.x + node.transform.padding.left,
        y: prePosition.y + node.transform.padding.top,
      },
      size: {
        width: expandedWidth,
        height: expandedHeight,
      },
      origin: {
        x: 0,
        y: 0,
      },
    });

    // Clear saved size after restoring
    if (savedSize) {
      originalExpandedSize.delete(node.id);
    }
  }

  // Hide子节点线条
  // Hide the child node lines
  node.blocks.forEach((block) => {
    block.getData(WorkflowNodeLinesData).allLines.forEach((line) => {
      line.updateUIState({
        style: !expanded ? { display: 'none' } : {},
      });
    });
  });

  // Force update port positions and block positions after DOM updates complete
  // Use requestAnimationFrame to ensure DOM has been updated
  requestAnimationFrame(() => {
    setTimeout(() => {
      // Update block positions based on collapsed/expanded state
      if (node.blocks && node.blocks.length >= 2) {
        const blockStart = node.blocks[0];
        const blockEnd = node.blocks[1];

        if (!expanded) {
          // Collapsed: Update block positions based on actual rendered size
          const nodeElement = (node as any).renderData?.node;
          let actualHeight = 150;

          if (nodeElement) {
            // The first child is the actual content container (form/header)
            const contentContainer = nodeElement.children[0] as HTMLElement;
            if (contentContainer) {
              actualHeight = contentContainer.offsetHeight;
            } else {
              // Fallback
              const rect = nodeElement.getBoundingClientRect();
              actualHeight = rect.height;
            }
          }

          // CRITICAL: Force update node size BEFORE updating block positions
          // because block position update triggers port recalculation based on node size
          const transform = node.getData(FlowNodeTransformData);
          if (transform) {
            if (transform.bounds) {
              transform.bounds.width = LOOP_COLLAPSED_WIDTH;
              transform.bounds.height = actualHeight;
            }
            if (transform.size) {
              transform.size.width = LOOP_COLLAPSED_WIDTH;
              transform.size.height = actualHeight;
            }
          }

          // Calculate canvas dimensions (internal visible area)
          const canvasWidth = LOOP_COLLAPSED_WIDTH - node.transform.padding.left - node.transform.padding.right;
          
          // Port should be at the visual center of the collapsed node
          // Block position is relative to canvas (after top padding)
          const nodeVisualCenterY = actualHeight / 2;
          const finalPortY = nodeVisualCenterY - node.transform.padding.top;

          // Now update block positions - port positions should be calculated correctly
          blockStart.transform?.transform?.update({
            position: { x: 0, y: finalPortY },
          });

          blockEnd.transform?.transform?.update({
            position: { x: canvasWidth, y: finalPortY },
          });
        } else {
        // Expanded: restore original positions
        const savedPositions = originalBlockPositions.get(node.id);

        if (savedPositions) {
          // Restore saved positions
          blockStart.transform?.transform?.update({
            position: savedPositions.blockStartPos,
          });

          blockEnd.transform?.transform?.update({
            position: savedPositions.blockEndPos,
          });

          // Clear saved positions after restoring
          originalBlockPositions.delete(node.id);
        } else {
          // Fallback: use default positions if no saved positions found
          const savedSize = originalExpandedSize.get(node.id);
          const expandedWidth = savedSize?.width || LOOP_EXPANDED_WIDTH;
          const expandedHeight = savedSize?.height || LOOP_EXPANDED_HEIGHT;

          const expandedCanvasHeight = expandedHeight - node.transform.padding.top - node.transform.padding.bottom;
          const expandedCanvasWidth = expandedWidth - node.transform.padding.left - node.transform.padding.right;
          const expandedVerticalCenter = expandedCanvasHeight / 2;

          blockStart.transform?.transform?.update({
            position: {
              x: 0,
              y: expandedVerticalCenter,
            },
          });

          blockEnd.transform?.transform?.update({
            position: {
              x: expandedCanvasWidth,
              y: expandedVerticalCenter,
            },
          });
        }
      }
    }

    // Single notify change to update UI and port positions
    (node as any).notifyChange?.();

    // Update blocks to recalculate their port positions
    if (node.blocks) {
      node.blocks.forEach((block: any) => {
        block.notifyChange?.();
      });
    }
  }, 50);
  });
}
