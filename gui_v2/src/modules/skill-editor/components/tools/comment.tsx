import { useState, useCallback } from 'react';

import {
  delay,
  usePlayground,
  useService,
  WorkflowDocument,
  WorkflowDragService,
  WorkflowSelectService,
} from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';

import { WorkflowNodeType } from '../../nodes';
import { IconCommentColored } from './colored-icons';

export const Comment = () => {
  const playground = usePlayground();
  const document = useService(WorkflowDocument);
  const selectService = useService(WorkflowSelectService);
  const dragService = useService(WorkflowDragService);

  const [tooltipVisible, setTooltipVisible] = useState(false);

  const calcNodePosition = useCallback(
    (mouseEvent: React.MouseEvent<HTMLButtonElement>) => {
      const mousePosition = playground.config.getPosFromMouseEvent(mouseEvent);
      return {
        x: mousePosition.x,
        y: mousePosition.y - 75,
      };
    },
    [playground]
  );

  const createComment = useCallback(
    async (mouseEvent: React.MouseEvent<HTMLButtonElement>) => {
      setTooltipVisible(false);
      const canvasPosition = calcNodePosition(mouseEvent);
      // create comment node - Create节点
      const node = document.createWorkflowNodeByType(WorkflowNodeType.Comment, canvasPosition);
      // wait comment node render - 等待节点Render
      await delay(16);
      // select comment node - 选中节点
      selectService.selectNode(node);
      // maybe touch event - 可能是触摸Event
      if (mouseEvent.detail !== 0) {
        // start drag -开始Drag
        dragService.startDragSelectedNodes(mouseEvent);
      }
    },
    [selectService, calcNodePosition, document, dragService]
  );

  return (
    <Tooltip
      trigger="custom"
      visible={tooltipVisible}
      onVisibleChange={setTooltipVisible}
      content="Comment"
    >
      <IconButton
        disabled={playground.config.readonly}
        icon={<IconCommentColored size={18} />}
        type="tertiary"
        theme="borderless"
        onClick={createComment}
        onMouseEnter={() => setTooltipVisible(true)}
        onMouseLeave={() => setTooltipVisible(false)}
      />
    </Tooltip>
  );
};
