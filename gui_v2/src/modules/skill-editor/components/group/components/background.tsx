/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { CSSProperties, FC, useEffect, MouseEvent as ReactMouseEvent } from 'react';

import { useWatch, WorkflowNodeEntity } from '@flowgram.ai/free-layout-editor';

import { GroupField } from '../constant';
import { defaultColor, groupColors } from '../color';

interface GroupBackgroundProps {
  node: WorkflowNodeEntity;
  style?: CSSProperties;
  onDrag?: (e: ReactMouseEvent) => void;
}

export const GroupBackground: FC<GroupBackgroundProps> = ({ node, style, onDrag }) => {
  const colorName = useWatch<string>(GroupField.Color) ?? defaultColor;
  const color = groupColors[colorName];

  useEffect(() => {
    const styleElement = document.createElement('style');

    // 使用独特的Select器
    const styleContent = `
      .workflow-group-render[data-group-id="${node.id}"] .workflow-group-background {
        border: 1px solid ${color['300']};
      }

      .workflow-group-render.selected[data-group-id="${node.id}"] .workflow-group-background {
        border: 1px solid ${color['400']};
      }
    `;

    styleElement.textContent = styleContent;
    document.head.appendChild(styleElement);

    return () => {
      styleElement.remove();
    };
  }, [color]);

  return (
    <div
      className="workflow-group-background"
      data-flow-editor-selectable="true"
      onMouseDown={(e) => {
        // Require Alt key to drag the group via background to avoid accidental moves
        if (e.altKey) {
          e.stopPropagation();
          e.preventDefault();
          onDrag?.(e);
        }
        // otherwise, allow event to bubble for normal interactions
      }}
      style={{
        ...style,
        backgroundColor: `${color['300']}29`,
        cursor: 'move',
      }}
    />
  );
};
