import { useCallback } from 'react';

import { useService, WorkflowLinesManager } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';

import { IconSwitchLineColored } from './colored-icons';

export const SwitchLine = () => {
  const linesManager = useService(WorkflowLinesManager);
  const switchLine = useCallback(() => {
    linesManager.switchLineType();
  }, [linesManager]);

  return (
    <Tooltip content={'Switch Line'}>
      <IconButton type="tertiary" theme="borderless" onClick={switchLine} icon={<IconSwitchLineColored size={18} />} />
    </Tooltip>
  );
};
