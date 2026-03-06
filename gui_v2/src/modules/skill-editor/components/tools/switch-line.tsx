import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { useService, WorkflowLinesManager } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';

import { IconSwitchLineColored } from './colored-icons';

export const SwitchLine = () => {
  const { t } = useTranslation('skillEditor');
  const linesManager = useService(WorkflowLinesManager);
  const switchLine = useCallback(() => {
    linesManager.switchLineType();
  }, [linesManager]);

  return (
    <Tooltip content={t('toolbar.switchLine')}>
      <IconButton type="tertiary" theme="borderless" onClick={switchLine} icon={<IconSwitchLineColored size={18} />} />
    </Tooltip>
  );
};
