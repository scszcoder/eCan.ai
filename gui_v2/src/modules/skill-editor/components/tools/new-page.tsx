import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Modal, Input } from '@douyinfe/semi-ui';
import { IconNewColored } from './colored-icons';
import emptyFlow from '../../data/empty-flow.json';
import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { createSkillInfo } from '../../typings/skill-info';

interface NewPageProps {
  disabled?: boolean;
}

export const NewPage = ({ disabled }: NewPageProps) => {
  const { document: workflowDocument } = useClientContext();
  const tools = usePlaygroundTools();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);

  const handleNewPage = useCallback(async () => {
    // 1. Save current skill if exists
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

        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        const jsonString = JSON.stringify(updatedSkillInfo, null, 2);
        await ipcApi.writeSkillFile(currentFilePath, jsonString);
        console.log('[NEW_SKILL] Saved current skill to:', currentFilePath);
      } catch (e) {
        console.warn('[NEW_SKILL] Failed to save current skill:', e);
      }
    }

    // 2. Prompt user for skill name using Modal
    let skillBaseName: string | null = null;
    
    try {
      skillBaseName = await new Promise<string | null>((resolve) => {
        let inputValue = '';
        let modalInstance: ReturnType<typeof Modal.confirm> | null = null;
        
        modalInstance = Modal.confirm({
          title: 'Create New Skill',
          content: (
            <div style={{ marginTop: 16 }}>
              <p style={{ marginBottom: 8 }}>Enter skill name (without _skill suffix):</p>
              <Input
                placeholder="e.g., shopify_fullfill"
                autoFocus
                onChange={(value) => { inputValue = value; }}
                onEnterPress={() => {
                  if (inputValue.trim()) {
                    modalInstance?.destroy();
                    resolve(inputValue.trim());
                  }
                }}
              />
              <p style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
                Standard structure will be created:<br/>
                my_skills/{'<name>_skill'}/diagram_dir/{'<name>_skill.json'}
              </p>
            </div>
          ),
          okText: 'Create',
          cancelText: 'Cancel',
          onOk: () => {
            modalInstance?.destroy();
            if (inputValue.trim()) {
              resolve(inputValue.trim());
            } else {
              resolve(null);
            }
          },
          onCancel: () => {
            modalInstance?.destroy();
            resolve(null);
          },
        });
      });
    } catch (e) {
      console.warn('[NEW_SKILL] Modal error:', e);
      return;
    }

    if (!skillBaseName) {
      console.log('[NEW_SKILL] User cancelled or empty name');
      return;
    }

    // Remove _skill suffix if user added it (we'll add it in backend)
    if (skillBaseName.endsWith('_skill')) {
      skillBaseName = skillBaseName.slice(0, -6);
    }

    console.log('[NEW_SKILL] Creating skill with name:', skillBaseName);

    // 3. Check if skill already exists
    try {
      const { IPCAPI } = await import('../../../../services/ipc/api');
      const ipcApi = IPCAPI.getInstance();
      
      const checkResult = await ipcApi.checkSkillExists(skillBaseName);
      if (checkResult.success && checkResult.data?.exists) {
        Modal.warning({
          title: 'Skill Already Exists',
          content: `A skill named "${skillBaseName}" already exists. Please choose a different name.`,
        });
        return;
      }
    } catch (e) {
      console.warn('[NEW_SKILL] Failed to check skill existence:', e);
      // Continue anyway - backend will also check
    }

    // 4. Call backend to scaffold directory and write files
    // Backend will:
    // - Create directory: my_skills/<name>_skill/diagram_dir/
    // - Create files: <name>_skill.json and <name>_skill_bundle.json
    // - skillName in JSON should be the user input (without _skill suffix)
    let skillRoot: string | null = null;
    let diagramJsonPath: string | null = null;
    
    try {
      const { IPCAPI } = await import('../../../../services/ipc/api');
      const ipcApi = IPCAPI.getInstance();
      
      // Generate skill JSON and bundle JSON with correct skillName (no _skill suffix)
      const now = Date.now();
      const skillJson = {
        skillName: skillBaseName,  // User input, no _skill suffix
        description: '',
        owner: '',
        version: '1.0.0',
        workFlow: emptyFlow,
        config: {},
        mode: 'development',
        run_mode: 'developing'
      };
      
      const bundleJson = {
        mainSheetId: 'main',
        sheets: [
          {
            id: 'main',
            name: 'Main',
            document: emptyFlow,
            createdAt: now,
            lastOpenedAt: now
          }
        ],
        openTabs: ['main'],
        activeSheetId: 'main'
      };
      
      // Create empty mapping JSON with correct structure
      const mappingJson = {
        developing: {
          mappings: [],
          options: {
            strict: false,
            apply_order: "top_down"
          }
        },
        released: {
          mappings: [],
          options: {
            strict: true,
            apply_order: "top_down"
          }
        },
        node_transfers: {},
        event_routing: {}
      };
      
      const scaffoldResponse = await ipcApi.scaffoldSkill(skillBaseName, '', 'diagram', skillJson, bundleJson, mappingJson);
      
      if (scaffoldResponse.success && scaffoldResponse.data) {
        skillRoot = (scaffoldResponse.data as any).skillRoot;
        // Use diagramPath from backend response (more reliable)
        diagramJsonPath = (scaffoldResponse.data as any).diagramPath || 
          `${skillRoot}/diagram_dir/${skillBaseName}_skill.json`;
        console.log('[NEW_SKILL] Scaffolded skill structure:', { skillRoot, diagramJsonPath });
      } else {
        console.error('[NEW_SKILL] Failed to scaffold skill:', scaffoldResponse.error);
        Modal.error({
          title: 'Error',
          content: `Failed to create skill: ${scaffoldResponse.error?.message || 'Unknown error'}`,
        });
        return;
      }
    } catch (e) {
      console.error('[NEW_SKILL] Scaffold error:', e);
      Modal.error({
        title: 'Error',
        content: `Failed to create skill structure: ${e}`,
      });
      return;
    }

    // 4. Load the empty flow into canvas
    workflowDocument.clear && workflowDocument.clear();
    workflowDocument.fromJSON(emptyFlow);
    tools.fitView && tools.fitView();
    
    // Update skill info store with correct skillName (no _skill suffix)
    const info = createSkillInfo(emptyFlow);
    info.skillName = skillBaseName;  // User input, no _skill suffix
    setSkillInfo(info);
    
    // Set file path
    useSkillInfoStore.getState().setCurrentFilePath(diagramJsonPath!);
    useSkillInfoStore.getState().setHasUnsavedChanges(false);
    
    console.log('[NEW_SKILL] Created new skill:', diagramJsonPath);
    
    Modal.success({
      title: 'Success',
      content: `Skill "${skillBaseName}" created successfully!`,
    });
  }, [workflowDocument, tools, setSkillInfo, skillInfo, breakpoints]);

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