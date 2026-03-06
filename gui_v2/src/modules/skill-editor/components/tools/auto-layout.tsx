import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { usePlayground, usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';

import { IconAutoLayoutColored } from './colored-icons';

export const AutoLayout = () => {
  const { t } = useTranslation('skillEditor');
  const tools = usePlaygroundTools();
  const playground = usePlayground();
  const autoLayout = useCallback(async () => {
    await tools.autoLayout();
  }, [tools]);

  return (
    <Tooltip content={t('toolbar.autoLayout')}>
      <IconButton
        disabled={playground.config.readonly}
        type="tertiary"
        theme="borderless"
        onClick={autoLayout}
        icon={<IconAutoLayoutColored size={18} />}
      />
    </Tooltip>
  );
};
