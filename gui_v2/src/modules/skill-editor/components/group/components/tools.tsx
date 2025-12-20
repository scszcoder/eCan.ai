/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FC } from 'react';

import { IconHandle } from '@douyinfe/semi-icons';
import { useNodeRender, useClientContext, CommandService } from '@flowgram.ai/free-layout-editor';

import { NodeMenu } from '../../node-menu';
import { FlowCommandId } from '../../../shortcuts';

import { GroupTitle } from './title';
import { GroupColor } from './color';

export const GroupTools: FC = () => {
  const { node } = useNodeRender();
  const ctx = useClientContext();

  const handleDelete = () => {
    ctx.get<CommandService>(CommandService).executeCommand(FlowCommandId.DELETE, [node]);
  };

  return (
    <div className="workflow-group-tools">
      <IconHandle className="workflow-group-tools-drag" />
      <GroupTitle />
      <GroupColor />
      <NodeMenu node={node} deleteNode={handleDelete} />
    </div>
  );
};
