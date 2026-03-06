import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { IconFitViewColored } from './colored-icons';

export const FitView = () => {
  const { t } = useTranslation('skillEditor');
  const tools = usePlaygroundTools();
  return (
    <Tooltip content={t('toolbar.fitView')}>
      <IconButton
        icon={<IconFitViewColored size={18} />}
        type="tertiary"
        theme="borderless"
        onClick={() => tools.fitView()}
      />
    </Tooltip>
  );
};
