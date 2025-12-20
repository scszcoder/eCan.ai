import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { IconButton, Tooltip } from '@douyinfe/semi-ui';
import { IconFitViewColored } from './colored-icons';

export const FitView = () => {
  const tools = usePlaygroundTools();
  return (
    <Tooltip content="FitView">
      <IconButton
        icon={<IconFitViewColored size={18} />}
        type="tertiary"
        theme="borderless"
        onClick={() => tools.fitView()}
      />
    </Tooltip>
  );
};
