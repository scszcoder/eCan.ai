import { useState } from 'react';

import { useService } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconPlay } from '@douyinfe/semi-icons';

import { RunningService } from '../../services';

export function Run() {
  const [isRunning, setRunning] = useState(false);
  const runningService = useService(RunningService);

  const onRun = async () => {
    setRunning(true);
    await runningService.startRun();
    setRunning(false);
  };

  return (
    <Tooltip content="Run">
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
