import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconFolderOpen } from '@douyinfe/semi-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';

interface OpenProps {
  disabled?: boolean;
}

export const Open = ({ disabled }: OpenProps) => {
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);

  const handleOpen = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const data = JSON.parse(event.target?.result as string);
            if (data && data.workFlow) {
              setSkillInfo(data);
              workflowDocument.clear();
              workflowDocument.fromJSON(data.workFlow);
              workflowDocument.fitView && workflowDocument.fitView();
            } else {
              workflowDocument.clear();
              workflowDocument.fromJSON(data);
              workflowDocument.fitView && workflowDocument.fitView();
            }
          } catch (error) {
            console.error('Failed to load file:', error);
          }
        };
        reader.readAsText(file);
      }
    };
    input.click();
  }, [workflowDocument, setSkillInfo]);

  return (
    <Tooltip content="Open">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconFolderOpen />}
        disabled={disabled}
        onClick={handleOpen}
      />
    </Tooltip>
  );
}; 