/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState, useEffect } from 'react';

import { useRefresh } from '@flowgram.ai/free-layout-editor';
import { useClientContext } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton, Divider } from '@douyinfe/semi-ui';
import { IconUndoColored, IconRedoColored, IconPauseColored, IconStopColored, IconStepColored, IconResumeColored, IconHelpColored } from './colored-icons';

import { TestRunButton } from '../testrun/testrun-button';
import { TestRunControlButton } from '../testrun/testrun-controls';
import { AddNode } from '../add-node';
import { ZoomSelect } from './zoom-select';
import { SwitchLine } from './switch-line';
import { ToolContainer, ToolSection } from './styles';
import { Save, SaveAs } from './save';
import { SkillNameBadge } from './skill-name';
import { Readonly } from './readonly';
import { MinimapSwitch } from './minimap-switch';
import { Minimap } from './minimap';
import { Interactive } from './interactive';
import { FitView } from './fit-view';
import { Comment } from './comment';
import { AutoLayout } from './auto-layout';
import { Open } from './open';
import { Info } from './info';
import { GitMenu } from './git';
import { HelpPanel } from '../help/help-panel';
import { NewPage } from './new-page';
import { ProblemButton } from '../problem-panel';
import { IPCAPI } from '../../../../services/ipc/api';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { useUserStore } from '../../../../stores/userStore';

export const Tools = () => {
  const { history, playground, document } = useClientContext();
  const skillInfoFromStore = useSkillInfoStore((state) => state.skillInfo);
  const previewMode = useSkillInfoStore((state) => state.previewMode);
  const username = useUserStore((state) => state.username);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [minimapVisible, setMinimapVisible] = useState(true);
  const [helpVisible, setHelpVisible] = useState(false);
  useEffect(() => {
    const disposable = history.undoRedoService.onChange(() => {
      setCanUndo(history.canUndo());
      setCanRedo(history.canRedo());
    });
    return () => disposable.dispose();
  }, [history]);
  const refresh = useRefresh();

  useEffect(() => {
    const disposable = playground.config.onReadonlyOrDisabledChange(() => refresh());
    return () => disposable.dispose();
  }, [playground]);

  const ipcApi = IPCAPI.getInstance();

  const handleRunControl = (action: 'cancel' | 'pause' | 'resume' | 'step') => {
    if (!skillInfoFromStore || !username) return;

    // Create a new skill info object with the latest diagram
    const skillInfo = {
      ...skillInfoFromStore,
      diagram: document.toJSON(),
    };

    switch (action) {
      case 'cancel':
        ipcApi.cancelRunSkill(username, skillInfo);
        break;
      case 'pause':
        ipcApi.pauseRunSkill(username, skillInfo);
        break;
      case 'resume':
        ipcApi.resumeRunSkill(username, skillInfo);
        break;
      case 'step':
        ipcApi.stepRunSkill(username, skillInfo);
        break;
    }
  };

  return (
    <ToolContainer className="demo-free-layout-tools">
      <ToolSection>
        <Interactive />
        <AutoLayout />
        <SwitchLine />
        <ZoomSelect />
        <FitView />
        <MinimapSwitch minimapVisible={minimapVisible} setMinimapVisible={setMinimapVisible} />
        <Minimap visible={minimapVisible} />
        <Readonly />
        <Comment />
        <Tooltip content="Undo">
          <IconButton
            type="tertiary"
            theme="borderless"
            icon={<IconUndoColored size={18} />}
            disabled={!canUndo || playground.config.readonly}
            onClick={() => history.undo()}
          />
        </Tooltip>
        <Tooltip content="Redo">
          <IconButton
            type="tertiary"
            theme="borderless"
            icon={<IconRedoColored size={18} />}
            disabled={!canRedo || playground.config.readonly}
            onClick={() => history.redo()}
          />
        </Tooltip>
        <ProblemButton />
        <Divider layout="vertical" style={{ height: '16px' }} margin={3} />
        <AddNode disabled={playground.config.readonly} />
        <Divider layout="vertical" style={{ height: '16px' }} margin={3} />
        <Open disabled={playground.config.readonly} />
        <NewPage disabled={playground.config.readonly} />
        <Save disabled={playground.config.readonly || previewMode} />
        <SaveAs disabled={playground.config.readonly || previewMode} />
        <Divider layout="vertical" style={{ height: '16px' }} margin={3} />
        <SkillNameBadge />
        <Info />
        <GitMenu />
        {/* Help button */}
        <Tooltip content="Help">
          <IconButton
            type="tertiary"
            theme="borderless"
            icon={<IconHelpColored size={18} />}
            onClick={() => setHelpVisible(true)}
          />
        </Tooltip>
        <TestRunButton disabled={playground.config.readonly} />
        <TestRunControlButton
          icon={<IconPauseColored size={16} />}
          onClick={() => handleRunControl('pause')}
          tooltip="Pause Run"
          disabled={playground.config.readonly}
        />
        <TestRunControlButton
          icon={<IconStepColored size={16} />}
          onClick={() => handleRunControl('step')}
          tooltip="Step Run"
          disabled={playground.config.readonly}
        />
        <TestRunControlButton
          icon={<IconResumeColored size={16} />}
          onClick={() => handleRunControl('resume')}
          tooltip="Resume Run"
          disabled={playground.config.readonly}
        />
        <TestRunControlButton
          icon={<IconStopColored size={16} />}
          onClick={() => handleRunControl('cancel')}
          tooltip="Stop Run"
          disabled={playground.config.readonly}
        />
      </ToolSection>
      <HelpPanel visible={helpVisible} onCancel={() => setHelpVisible(false)} />
    </ToolContainer>
  );
};
