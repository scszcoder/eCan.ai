import { Tooltip, IconButton } from '@douyinfe/semi-ui';

import { IconMinimapColored } from './colored-icons';

export const MinimapSwitch = (props: {
  minimapVisible: boolean;
  setMinimapVisible: (visible: boolean) => void;
}) => {
  const { minimapVisible, setMinimapVisible } = props;

  return (
    <Tooltip content="Minimap">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconMinimapColored size={18} visible={minimapVisible} />}
        onClick={() => setMinimapVisible(!minimapVisible)}
      />
    </Tooltip>
  );
};
