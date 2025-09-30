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
import { IPCWCClient } from '@/services/ipc/ipcWCClient';

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
    // 0. Scaffold a new diagram-based skill via IPC (backend will create <name>_skill/diagram_dir/...)
    const client = IPCWCClient.getInstance();
    const defaultName = `skill_${Date.now()}`;
    let scaffoldedName = defaultName;
    let diagramJsonPath: string | null = null;
    try {
      const resp: any = await client.sendRequest('skills.scaffold', { name: defaultName, kind: 'diagram' });
      if (resp?.status === 'success' && resp.result?.skillRoot) {
        scaffoldedName = defaultName;
        const root: string = resp.result.skillRoot;
        diagramJsonPath = `${root.replace(/\\/g, '/')}/diagram_dir/${scaffoldedName}_skill.json`;
      }
    } catch (e) {
      // Proceed even if scaffold fails, editor will still clear to empty
      // eslint-disable-next-line no-console
      console.warn('[NewSkill] scaffold failed, proceeding with empty canvas', e);
    }

    // 1. Save the current data using the CORRECT, up-to-date logic
    if (skillInfo) {
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

      setSkillInfo(updatedSkillInfo);
      await saveFile(updatedSkillInfo, username || undefined);
    }

    // 2. Clear the existing canvas data
    workflowDocument.clear && workflowDocument.clear();
    // 3. Load empty data
    workflowDocument.fromJSON(emptyFlow);
    // 4. Fit the canvas view
    tools.fitView && tools.fitView();
    // 5. Generate and save the new SkillInfo, set name and optional path
    const info = createSkillInfo(emptyFlow);
    info.skillName = scaffoldedName;
    setSkillInfo(info);
    if (diagramJsonPath) {
      try {
        useSkillInfoStore.getState().setCurrentFilePath(diagramJsonPath);
      } catch {}
    }
  }, [workflowDocument, username, tools, setSkillInfo, skillInfo, breakpoints]);

  return (
    <Tooltip content="New Skill">
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