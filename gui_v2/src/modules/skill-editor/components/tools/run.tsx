import { useState } from 'react';

import { useService } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconPlay } from '@douyinfe/semi-icons';

import { WorkflowRuntimeService } from '../../plugins/runtime-plugin/runtime-service';

/**
 * Run the simulation and highlight the lines
 */
export function Run() {
  const [isRunning, setRunning] = useState(false);
  const runtimeService = useService(WorkflowRuntimeService);
  const onRun = async () => {
    setRunning(true);
    await runtimeService.taskRun('{}');
    setRunning(false);
  };
  return (
    <Tooltip content="Test Run">
    <IconButton
      type="tertiary"
      theme="borderless"
      icon={<IconPlay />}
      loading={isRunning}
      onClick={onRun}
    />
  </Tooltip>
  );
}
