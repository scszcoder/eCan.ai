import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconFlowChartStroked } from '@douyinfe/semi-icons';
import emptyFlow from '../../data/empty-flow.json';
import { saveFile } from './save';
import { useUserStore } from '../../../../stores/userStore';
import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';

interface NewPageProps {
  disabled?: boolean;
}

export const NewPage = ({ disabled }: NewPageProps) => {
  const { document: workflowDocument } = useClientContext();
  const username = useUserStore((state) => state.username);
  const tools = usePlaygroundTools();

  const handleNewPage = useCallback(async () => {
    // 1. 保存当前数据，复用 saveFile
    await saveFile(workflowDocument.toJSON(), username || undefined);
    // 2. 清理现有画布数据
    workflowDocument.clear && workflowDocument.clear();
    // 3. 加载 emptydata
    workflowDocument.fromJSON(emptyFlow);
    // 4. 画布自适应
    tools.fitView && tools.fitView();
  }, [workflowDocument, username, tools]);

  return (
    <Tooltip content="New Page">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconFlowChartStroked />}
        disabled={disabled}
        onClick={handleNewPage}
      />
    </Tooltip>
  );
}; 