import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconFile } from '@douyinfe/semi-icons';
import emptyFlow from '../../data/empty-flow.json';
import { saveFile } from './save';
import { useUserStore } from '../../../../stores/userStore';
import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { createSkillInfo } from '../../typings/skill-info';

interface NewPageProps {
  disabled?: boolean;
}

export const NewPage = ({ disabled }: NewPageProps) => {
  const { document: workflowDocument } = useClientContext();
  const username = useUserStore((state) => state.username);
  const tools = usePlaygroundTools();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);

  const handleNewPage = useCallback(async () => {
    // 1. 保存当前数据，复用 saveFile
    if (skillInfo) {
      await saveFile(skillInfo, username || undefined);
    }
    // 2. 清理现有画布数据
    workflowDocument.clear && workflowDocument.clear();
    // 3. 加载 emptydata
    workflowDocument.fromJSON(emptyFlow);
    // 4. 画布自适应
    tools.fitView && tools.fitView();
    // 5. 生成并保存新的 SkillInfo
    setSkillInfo(createSkillInfo(emptyFlow));
  }, [workflowDocument, username, tools, setSkillInfo, skillInfo]);

  return (
    <Tooltip content="New Page">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconFile />}
        disabled={disabled}
        onClick={handleNewPage}
      />
    </Tooltip>
  );
}; 