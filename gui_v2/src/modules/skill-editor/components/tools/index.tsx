/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useEffect } from 'react';

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
import { useRunningNodeStore } from '../../stores/running-node-store';
import { useUserStore } from '../../../../stores/userStore';

// Error boundary that auto-recovers from context errors during React transitions
class ToolsErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; retryCount: number; lastErrorTime: number }
> {
  private retryTimeout: NodeJS.Timeout | null = null;
  
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, retryCount: 0, lastErrorTime: 0 };
  }
  
  static getDerivedStateFromError(error: Error) {
    // Catch ALL errors during render and allow retry
    // This handles both #321 (Invalid hook call) and #130 (undefined component)
    // which can occur during React transitional states
    console.log('[ToolsErrorBoundary] Caught error:', error.message?.slice(0, 100));
    return { hasError: true, lastErrorTime: Date.now() };
  }
  
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.log('[ToolsErrorBoundary] componentDidCatch:', error.message?.slice(0, 100));
  }
  
  componentDidUpdate(_prevProps: any, prevState: { hasError: boolean; retryCount: number; lastErrorTime: number }) {
    if (this.state.hasError && !prevState.hasError) {
      // Clear any existing timeout
      if (this.retryTimeout) {
        clearTimeout(this.retryTimeout);
      }
      
      // Use exponential backoff for retries: 200ms, 400ms, 800ms, etc.
      const delay = Math.min(200 * Math.pow(1.5, this.state.retryCount), 2000);
      
      this.retryTimeout = setTimeout(() => {
        if (this.state.retryCount < 15) {
          console.log('[ToolsErrorBoundary] Retrying render...', this.state.retryCount + 1, 'delay was', delay);
          this.setState({ hasError: false, retryCount: this.state.retryCount + 1 });
        } else {
          console.error('[ToolsErrorBoundary] Max retries exceeded, showing fallback');
        }
      }, delay);
    }
  }
  
  componentWillUnmount() {
    if (this.retryTimeout) {
      clearTimeout(this.retryTimeout);
    }
  }
  
  render() {
    if (this.state.hasError) {
      // Return empty container during error state to maintain layout
      return <div style={{ height: 40 }} />;
    }
    if (this.state.retryCount >= 15) {
      // Show permanent fallback after max retries
      return <div style={{ height: 40, color: 'var(--semi-color-text-2)', fontSize: 12, display: 'flex', alignItems: 'center', padding: '0 8px' }}>Tools loading...</div>;
    }
    return this.props.children;
  }
}

const ToolsInner = () => {
  // Stabilization state - wait for flowgram to settle before rendering interactive elements
  // This prevents errors during the initial "churn" period when flowgram
  // fires internal events like FreeLayoutScopeChain.sortAll
  // NOTE: We keep components mounted but visually hidden to preserve their state (like Open's pickerVisible)
  const [isStable, setIsStable] = useState(false);
  
  useEffect(() => {
    // Wait a brief moment for flowgram's internal initialization to complete
    const timer = setTimeout(() => {
      setIsStable(true);
    }, 100);
    return () => clearTimeout(timer);
  }, []);
  
  const ctx = useClientContext();
  const { history, playground, document } = ctx;
  
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

  const handleRunControl = async (action: 'cancel' | 'pause' | 'resume' | 'step') => {
    if (!skillInfoFromStore || !username) return;

    // Create a new skill info object with the latest diagram
    const skillInfo = {
      ...skillInfoFromStore,
      diagram: document.toJSON(),
    };

    switch (action) {
      case 'cancel': {
        // Inject run_id and skill_id so the Lambda can locate and stop the Fargate task
        const activeRunId = useRunningNodeStore.getState().activeRunId;
        const cancelPayload = {
          ...skillInfo,
          run_id: activeRunId || '0123456789',
          skill_id: (skillInfoFromStore as any)?.skillId || (skillInfoFromStore as any)?.skill_id,
        };
        console.log('[ToolBar] cancelRunSkill with run_id:', cancelPayload.run_id, 'skill_id:', cancelPayload.skill_id);
        try {
          await ipcApi.cancelRunSkill(username, cancelPayload);
          console.log('[ToolBar] ✅ Cancel request sent successfully');
        } catch (err) {
          console.error('[ToolBar] ❌ Failed to send cancel request:', err);
        }
        // Remove from dev task tracking
        if (activeRunId) {
          useRunningNodeStore.getState().removeDevTask(activeRunId);
        }
        // Clear the active run tracking
        useRunningNodeStore.getState().setActiveRunId(null);
        useRunningNodeStore.getState().setRunningNodeId(null);
        break;
      }
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

// Export wrapped component with error boundary for resilience during context transitions
export const Tools = () => (
  <ToolsErrorBoundary>
    <ToolsInner />
  </ToolsErrorBoundary>
);
