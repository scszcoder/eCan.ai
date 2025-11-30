import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconNewColored } from './colored-icons';
import emptyFlow from '../../data/empty-flow.json';
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
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);

  const handleNewPage = useCallback(async () => {
    // 1. 先SaveWhen前 skill（If有且有文件Path）- 不弹出Dialog
    const currentFilePath = useSkillInfoStore.getState().currentFilePath;
    if (skillInfo && currentFilePath) {
      try {
        const diagram = workflowDocument.toJSON();
        diagram.nodes.forEach((node: any) => {
          if (breakpoints.includes(node.id)) {
            if (!node.data) {
              node.data = {};
            }
            node.data.break_point = true;
          } else {
            if (node.data?.break_point) {
              delete node.data.break_point;
            }
          }
        });

        const updatedSkillInfo = {
          ...skillInfo,
          workFlow: diagram,
          lastModified: new Date().toISOString(),
        };

        // 直接Save到When前文件Path，不弹出Dialog
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        const jsonString = JSON.stringify(updatedSkillInfo, null, 2);
        await ipcApi.writeSkillFile(currentFilePath, jsonString);
        console.log('[NEW_SKILL] Saved current skill to:', currentFilePath);
      } catch (e) {
        console.warn('[NEW_SKILL] Failed to save current skill:', e);
      }
    }

    // 2. 弹出Dialog让UserInput新 skill 的Name（只弹出一次）
    let scaffoldedName = 'untitled';
    let diagramJsonPath: string | null = null;
    
    try {
      const { IPCAPI } = await import('../../../../services/ipc/api');
      const ipcApi = IPCAPI.getInstance();
      
      const defaultFileName = `untitled.json`;
      console.log('[SKILL_IO][FRONTEND][NEW_SKILL] Opening save dialog');
      const dialogResponse = await ipcApi.showSaveDialog(defaultFileName, [
        { name: 'Skill Files', extensions: ['json'] },
        { name: 'All Files', extensions: ['*'] }
      ]);
      
      if (dialogResponse.success && dialogResponse.data && !dialogResponse.data.cancelled) {
        const filePath = (dialogResponse.data as any).filePath;
        if (filePath) {
          const fileName = filePath.split(/[/\\]/).pop() || 'untitled.json';
          scaffoldedName = fileName.replace(/\.json$/i, '');
          diagramJsonPath = filePath;
          console.log('[SKILL_IO][FRONTEND][NEW_SKILL] User selected:', scaffoldedName);
        } else {
          console.log('[SKILL_IO][FRONTEND][NEW_SKILL] User cancelled');
          return;
        }
      } else {
        console.log('[SKILL_IO][FRONTEND][NEW_SKILL] Dialog cancelled');
        return;
      }
    } catch (e) {
      console.warn('[NewSkill] Failed to show dialog, using default name', e);
      return; // IfDialogFailed，直接返回
    }

    // 3. Clear the existing canvas data
    workflowDocument.clear && workflowDocument.clear();
    // 4. Load empty data
    workflowDocument.fromJSON(emptyFlow);
    // 5. Fit the canvas view
    tools.fitView && tools.fitView();
    // 6. Generate new SkillInfo
    const info = createSkillInfo(emptyFlow);
    info.skillName = scaffoldedName;
    setSkillInfo(info);
    
    // 7. 立即Save新Create的 skill 到文件System
    if (diagramJsonPath) {
      try {
        // Save新 skill 到文件
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        const jsonString = JSON.stringify(info, null, 2);
        const writeResponse = await ipcApi.writeSkillFile(diagramJsonPath, jsonString);
        
        if (writeResponse.success) {
          // 使用Backend返回的实际文件Path（Include完整的文件夹结构）
          const actualFilePath = (writeResponse.data as any)?.filePath || diagramJsonPath;
          console.log('[NEW_SKILL] Created new skill file:', actualFilePath);
          
          // Settings正确的文件Path
          useSkillInfoStore.getState().setCurrentFilePath(actualFilePath);
          useSkillInfoStore.getState().setHasUnsavedChanges(false);
        } else {
          console.error('[NEW_SKILL] Failed to create skill file:', writeResponse.error);
        }
      } catch (e) {
        console.error('[NEW_SKILL] Error saving new skill:', e);
      }
    }
  }, [workflowDocument, username, tools, setSkillInfo, skillInfo, breakpoints]);

  return (
    <Tooltip content="New Skill">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconNewColored size={18} />}
        disabled={disabled}
        onClick={handleNewPage}
      />
    </Tooltip>
  );
};