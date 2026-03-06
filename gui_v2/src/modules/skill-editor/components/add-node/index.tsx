import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { IconAddNodeColored } from '../tools/colored-icons';

import { useAddNode } from './use-add-node';

export const AddNode = (props: { disabled: boolean }) => {
  const { t } = useTranslation('skillEditor');
  const addNode = useAddNode();
  return (
    <Tooltip content={t('toolbar.addNode')}>
      <IconButton
        type="tertiary"
        theme="borderless"
        data-testid="demo.free-layout.add-node"
        icon={<IconAddNodeColored size={18} />}
        disabled={props.disabled}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          addNode(rect);
        }}
      />
    </Tooltip>
  );
};
