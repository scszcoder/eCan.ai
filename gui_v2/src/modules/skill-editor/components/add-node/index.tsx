import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconPlusCircle } from '@douyinfe/semi-icons';

import { useAddNode } from './use-add-node';

export const AddNode = (props: { disabled: boolean }) => {
  const addNode = useAddNode();
  return (
    <Tooltip content="Add Node">
      <IconButton
        type="tertiary"
        theme="borderless"
        data-testid="demo.free-layout.add-node"
        icon={<IconPlusCircle />}
        disabled={props.disabled}
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          addNode(rect);
        }}
      />
    </Tooltip>
  );
};
