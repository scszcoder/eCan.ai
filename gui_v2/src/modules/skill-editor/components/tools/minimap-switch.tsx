import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';

import { IconMinimapColored } from './colored-icons';

export const MinimapSwitch = (props: {
  minimapVisible: boolean;
  setMinimapVisible: (visible: boolean) => void;
}) => {
  const { t } = useTranslation('skillEditor');
  const { minimapVisible, setMinimapVisible } = props;

  return (
    <Tooltip content={t('toolbar.minimap')}>
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconMinimapColored size={18} visible={minimapVisible} />}
        onClick={() => setMinimapVisible(!minimapVisible)}
      />
    </Tooltip>
  );
};
