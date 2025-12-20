import { useCallback } from 'react';

import {
  WorkflowNodePanelService,
  WorkflowNodePanelUtils,
} from '@flowgram.ai/free-node-panel-plugin';
import { LineRenderProps } from '@flowgram.ai/free-lines-plugin';
import {
  delay,
  HistoryService,
  useService,
  WorkflowDocument,
  WorkflowDragService,
  WorkflowLinesManager,
  WorkflowNodeEntity,
  WorkflowNodeJSON,
} from '@flowgram.ai/free-layout-editor';

import './index.less';
import { useVisible } from './use-visible';
import { IconPlusCircle } from './button';

export const LineAddButton = (props: LineRenderProps) => {
  const { line, selected, hovered, color } = props;
  const visible = useVisible({ line, selected, hovered });
  const nodePanelService = useService<WorkflowNodePanelService>(WorkflowNodePanelService);
  const document = useService(WorkflowDocument);
  const dragService = useService(WorkflowDragService);
  const linesManager = useService(WorkflowLinesManager);
  const historyService = useService(HistoryService);

  const { fromPort, toPort } = line;

  const onClick = useCallback(async () => {
    // calculate the middle point of the line - 计算线条的中点Position
    const position = {
      x: (line.position.from.x + line.position.to.x) / 2,
      y: (line.position.from.y + line.position.to.y) / 2,
    };

    // get container node for the new node - Get新节点的Container节点
    const containerNode = fromPort?.node?.parent;

    // show node selection panel - Display节点Select面板
    const result = await nodePanelService.singleSelectNodePanel({
      position,
      containerNode,
      panelProps: {
        enableScrollClose: true,
      },
    });
    if (!result) {
      return;
    }

    const { nodeType, nodeJSON } = result;

    // adjust position for the new node - 调整新节点的Position
    const nodePosition = WorkflowNodePanelUtils.adjustNodePosition({
      nodeType,
      position,
      fromPort,
      toPort,
      containerNode,
      document,
      dragService,
    });

    // create new workflow node - Create新的工作流节点
    const node: WorkflowNodeEntity = document.createWorkflowNodeByType(
      nodeType,
      nodePosition,
      nodeJSON ?? ({} as WorkflowNodeJSON),
      containerNode?.id
    );

    // auto offset subsequent nodes - 自动偏移后续节点
    if (fromPort && toPort) {
      WorkflowNodePanelUtils.subNodesAutoOffset({
        node,
        fromPort,
        toPort,
        containerNode,
        historyService,
        dragService,
        linesManager,
      });
    }

    // wait for node render - 等待节点Render
    await delay(20);

    // build connection lines - 构建Connection线
    WorkflowNodePanelUtils.buildLine({
      fromPort,
      node,
      toPort,
      linesManager,
    });

    // remove original line - Remove原始线条
    line.dispose();
  }, []);

  if (!visible) {
    return <></>;
  }

  // Use the line's center (computed by WorkflowLineRenderData) so the button
  // sits on the actual curve mid-point instead of the bounding box center.
  // center.labelX / labelY are relative to the line container's top-left.
  let left: string | number = '50%';
  let top: string | number = '50%';
  try {
    const center = (line as any).center as { labelX?: number; labelY?: number } | undefined;
    if (center && typeof center.labelX === 'number' && typeof center.labelY === 'number') {
      left = center.labelX;
      top = center.labelY;
    }
  } catch {}

  return (
    <div
      className="line-add-button"
      style={{
        left,
        top,
        color,
      }}
      data-testid="sdk.workflow.canvas.line.add"
      data-line-id={line.id}
      onClick={onClick}
    >
      <IconPlusCircle />
    </div>
  );
};
