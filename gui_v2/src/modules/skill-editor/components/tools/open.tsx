import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconFolderOpen } from '@douyinfe/semi-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { SkillInfo } from '../../typings/skill-info';

interface OpenProps {
  disabled?: boolean;
}

export const Open = ({ disabled }: OpenProps) => {
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);

  const handleOpen = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.style.display = 'none';

    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (event) => {
          try {
            const data = JSON.parse(event.target?.result as string) as SkillInfo;
            const diagram = data.workFlow;

            if (diagram) {
              // Set skill info first
              setSkillInfo(data);

              // Find and set breakpoints
              const breakpointIds = diagram.nodes
                .filter((node: any) => node.data?.break_point)
                .map((node: any) => node.id);
              setBreakpoints(breakpointIds);

              // Load diagram into the editor
              workflowDocument.clear();
              workflowDocument.fromJSON(diagram);
              workflowDocument.fitView && workflowDocument.fitView();
            } else {
              // Fallback for older formats or raw diagrams
              workflowDocument.clear();
              workflowDocument.fromJSON(data as any);
              workflowDocument.fitView && workflowDocument.fitView();
            }
          } catch (error) {
            console.error('Failed to load file:', error);
          }
        };
        reader.readAsText(file);
      }
      // Clean up the input element
      document.body.removeChild(input);
    };

    document.body.appendChild(input);
    input.click();
  }, [workflowDocument, setSkillInfo, setBreakpoints]);

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