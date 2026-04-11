import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Modal, Input } from '@douyinfe/semi-ui';
import { IconNewColored } from './colored-icons';
import emptyFlow from '../../data/empty-flow.json';
import { usePlaygroundTools } from '@flowgram.ai/free-layout-editor';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { createSkillInfo } from '../../typings/skill-info';
import { IPCAPI } from '../../../../services/ipc/api';
import { detectPlatform } from '../../../../config/platform';
import { useUserStore } from '../../../../stores/userStore';
import { useSkillStore } from '../../../../stores/domain/skillStore';

interface NewPageProps {
  disabled?: boolean;
}

export const NewPage = ({ disabled }: NewPageProps) => {
  const { t } = useTranslation('skillEditor');
  const { document: workflowDocument } = useClientContext();
  const tools = usePlaygroundTools();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const setPreviewMode = useSkillInfoStore((state) => state.setPreviewMode);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const setDataMappingJson = useSkillInfoStore((state) => state.setDataMappingJson);
  const setDataMappingDirty = useSkillInfoStore((state) => state.setDataMappingDirty);
  const setDataMappingPath = useSkillInfoStore((state) => state.setDataMappingPath);
  const username = useUserStore((state) => state.username);

  const normalizeSkillBaseName = (name: string) => {
    const raw = (name || 'untitled').trim();
    return raw.replace(/_skill$/i, '') || 'untitled';
  };

  /**
   * Sanitize username/email to be safe for S3 directory paths.
   * Converts "jack@xyz.com" -> "jack_xyz_com"
   * Must match backend _safe_user_dir_name() in skill_editor_agent.py
   */
  const sanitizeUsername = (user: string): string => {
    const u = (user || '').trim();
    if (!u) return 'unknown';
    if (u.includes('@')) {
      const [localPart, domainPart] = u.split('@', 2);
      return `${localPart}_${(domainPart || '').replace(/\./g, '_')}`;
    }
    return u.replace(/@/g, '_').replace(/\./g, '_');
  };

  const buildWebSkillPath = (skillName: string, user?: string | null) => {
    const base = normalizeSkillBaseName(skillName);
    // Folder name includes _skill suffix, e.g., "abc" -> "abc_skill/"
    const folderName = `${base}_skill`;
    // Sanitize username for S3 path (convert @ and . to _)
    const ownerPrefix = user ? `${sanitizeUsername(user)}/` : '';
    return `${ownerPrefix}my_skills/${folderName}/diagram_dir/${base}_skill.json`;
  };

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

        const ipcApi = IPCAPI.getInstance();
        const jsonString = JSON.stringify(updatedSkillInfo, null, 2);
        await ipcApi.writeSkillFile({ filePath: currentFilePath, content: jsonString });
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
          title: t('newSkill.title'),
          content: (
            <div style={{ marginTop: 16 }}>
              <p style={{ marginBottom: 8 }}>{t('newSkill.nameLabel')}</p>
              <Input
                placeholder={t('newSkill.namePlaceholder')}
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
                {t('newSkill.structureHint')}<br/>
                my_skills/{'<name>_skill'}/diagram_dir/{'<name>_skill.json'}
              </p>
            </div>
          ),
          okText: t('newSkill.okText'),
          cancelText: t('newSkill.cancelText'),
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
      const ipcApi = IPCAPI.getInstance();
      if (detectPlatform() === 'web') {
        const checkResult = await ipcApi.checkSkillExists(skillBaseName);
        if (checkResult.success && checkResult.data?.exists) {
          Modal.warning({
            title: t('newSkill.alreadyExistsTitle'),
            content: t('newSkill.alreadyExistsContent', { name: skillBaseName }),
          });
          return;
        }
      } else {
        const checkResult = await ipcApi.checkSkillExists(skillBaseName);
        if (checkResult.success && checkResult.data?.exists) {
          Modal.warning({
            title: t('newSkill.alreadyExistsTitle'),
            content: t('newSkill.alreadyExistsContent', { name: skillBaseName }),
          });
          return;
        }
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
    let mappingJsonForStore: any = null;
    let backendSkillId: string | null = null;  // DB-generated ID from scaffold response
    
    try {
      // Generate skill JSON and bundle JSON with correct skillName (no _skill suffix)
      const now = Date.now();
      const skillJson = {
        skillName: skillBaseName,
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

      let mappingJson = {
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
        event_data_mapping: {},
      };

      if (detectPlatform() === 'web') {
        try {
          const resp = await fetch('/skills/data_mapping.json', { cache: 'no-store' });
          if (resp.ok) {
            const text = await resp.text();
            mappingJson = JSON.parse(text);
          }
        } catch (e) {
          console.warn('[NEW_SKILL] Failed to load default data_mapping.json', e);
        }

        const diagramPath = buildWebSkillPath(skillBaseName, username || undefined);
        const skillRootPath = diagramPath.split('/diagram_dir/')[0];
        const bundlePath = diagramPath.replace(/_skill\.json$/i, '_skill_bundle.json');
        const mappingPath = `${skillRootPath}/data_mapping.json`;

        const ipcApi = IPCAPI.getInstance();
        await ipcApi.writeSkillFile([
          { filePath: diagramPath, content: JSON.stringify(skillJson, null, 2) },
          { filePath: bundlePath, content: JSON.stringify(bundleJson, null, 2) },
          { filePath: mappingPath, content: JSON.stringify(mappingJson, null, 2) },
        ]);

        setDataMappingJson(JSON.stringify(mappingJson, null, 2), false);
        setDataMappingDirty(false);
        mappingJsonForStore = mappingJson;

        setPreviewMode(false);
        skillRoot = skillRootPath;
        diagramJsonPath = diagramPath;
        console.log('[NEW_SKILL] Scaffolded web skill structure:', { skillRoot, diagramJsonPath });
      } else {
        const ipcApi = IPCAPI.getInstance();
        const scaffoldResponse = await ipcApi.scaffoldSkill(skillBaseName, '', 'diagram', skillJson, bundleJson, mappingJson);

        if (scaffoldResponse.success && scaffoldResponse.data) {
          setPreviewMode(false);
          const scaffoldData = scaffoldResponse.data as any;
          skillRoot = scaffoldData.skillRoot;
          diagramJsonPath = scaffoldData.diagramPath ||
            `${skillRoot}/diagram_dir/${skillBaseName}_skill.json`;
          // IMPORTANT: Use the DB-generated skillId from backend, not the frontend UUID.
          // This ensures subsequent saves use the correct DB ID (fixes P0-B02).
          backendSkillId = scaffoldData.skillId || null;
          console.log('[NEW_SKILL] Scaffolded skill structure:', { skillRoot, diagramJsonPath, backendSkillId });
          mappingJsonForStore = mappingJson;
        } else {
          console.error('[NEW_SKILL] Failed to scaffold skill:', scaffoldResponse.error);
          Modal.error({
            title: t('newSkill.errorTitle'),
            content: t('newSkill.errorCreate', { error: scaffoldResponse.error?.message || 'Unknown error' }),
          });
          return;
        }
      }
    } catch (e) {
      console.error('[NEW_SKILL] Scaffold error:', e);
      Modal.error({
        title: t('newSkill.errorTitle'),
        content: t('newSkill.errorStructure', { error: String(e) }),
      });
      return;
    }

    // 4. Load the empty flow into canvas
    workflowDocument.clear && workflowDocument.clear();
    workflowDocument.fromJSON(emptyFlow);
    tools.fitView && tools.fitView();
    
    // Update skill info store with correct skillName and DB-generated skillId
    const info = createSkillInfo(emptyFlow);
    info.skillName = skillBaseName;  // User input, no _skill suffix
    // Use the backend DB skillId so subsequent saves work correctly (P0-B02)
    if (backendSkillId) {
      info.skillId = backendSkillId;
      console.log('[NEW_SKILL] Using backend skillId:', backendSkillId);
    }
    setSkillInfo(info);
    if (mappingJsonForStore) {
      setDataMappingJson(JSON.stringify(mappingJsonForStore, null, 2), false);
      setDataMappingDirty(false);
    }
    
    // Set file path
    useSkillInfoStore.getState().setCurrentFilePath(diagramJsonPath!);
    const mappingPath = diagramJsonPath ? `${diagramJsonPath.split('/diagram_dir/')[0]}/data_mapping.json` : null;
    setDataMappingPath(mappingPath);
    useSkillInfoStore.getState().setHasUnsavedChanges(false);

    // Add to useSkillStore so Skills page shows the new skill immediately (P1-B09)
    const skillId = backendSkillId || info.skillId;
    if (skillId) {
      try {
        useSkillStore.getState().addItem({
          id: skillId,
          name: skillBaseName,
          owner: username || '',
          description: '',
          version: '1.0.0',
          path: diagramJsonPath || '',
          level: 'entry',
          source: 'ui',
          status: 'active',
        } as any);
        console.log('[NEW_SKILL] Added to useSkillStore:', skillId);
      } catch (e) {
        console.warn('[NEW_SKILL] Failed to add to useSkillStore:', e);
      }
    }

    console.log('[NEW_SKILL] Created new skill:', diagramJsonPath);
    
    Modal.success({
      title: t('newSkill.successTitle'),
      content: t('newSkill.successContent', { name: skillBaseName }),
    });
  }, [
    workflowDocument,
    tools,
    setSkillInfo,
    setPreviewMode,
    skillInfo,
    breakpoints,
    setDataMappingJson,
    setDataMappingDirty,
    setDataMappingPath,
    username,
  ]);

  return (
    <Tooltip content={t('toolbar.newSkill')}>
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