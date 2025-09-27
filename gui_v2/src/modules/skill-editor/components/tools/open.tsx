import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconFolderOpen } from '@douyinfe/semi-icons';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { SkillInfo } from '../../typings/skill-info';
import { hasIPCSupport, hasFullFilePaths } from '../../../../config/platform';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';

interface OpenProps {
  disabled?: boolean;
}

export const Open = ({ disabled }: OpenProps) => {
  const { document: workflowDocument } = useClientContext();
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setBreakpoints = useSkillInfoStore((state) => state.setBreakpoints);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);

  const handleOpen = useCallback(async () => {
    try {
      if (hasIPCSupport() && hasFullFilePaths()) {
        // Desktop mode: Use IPC backend for full file path support
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        
        const dialogResponse = await ipcApi.showOpenDialog([
          { name: 'Skill Files', extensions: ['json'] },
          { name: 'All Files', extensions: ['*'] }
        ]);

        if (dialogResponse.success && dialogResponse.data && !dialogResponse.data.cancelled) {
          const filePath = dialogResponse.data.filePath;
          
          // Read file content through IPC
          const fileResponse = await ipcApi.readSkillFile(filePath);
          
          if (fileResponse.success && fileResponse.data) {
            const data = JSON.parse(fileResponse.data.content) as SkillInfo;
            const diagram = data.workFlow;

            if (diagram) {
              // Set skill info with file path
              setSkillInfo(data);
              setCurrentFilePath(filePath);
              setHasUnsavedChanges(false);

              // Add to recent files
              addRecentFile(createRecentFile(filePath, data.skillName));

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
              // Fallback for older formats
              workflowDocument.clear();
              workflowDocument.fromJSON(data as any);
              workflowDocument.fitView && workflowDocument.fitView();
            }
          } else {
            console.error('Failed to read file:', fileResponse.error);
          }
        }
      } else {
        // Web mode: Use browser FileReader API (original implementation)
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
                  // Set skill info without file path (web mode limitation)
                  setSkillInfo(data);
                  setCurrentFilePath(null);
                  setHasUnsavedChanges(false);

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
                  // Fallback for older formats
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
      }
    } catch (error) {
      console.error('Failed to open file:', error);
    }
  }, [workflowDocument, setSkillInfo, setBreakpoints, setCurrentFilePath, setHasUnsavedChanges]);

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