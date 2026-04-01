/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React, { useState, useCallback } from 'react';

import { Button, Collapsible, Tabs, Tooltip, Checkbox, Select, Typography } from '@douyinfe/semi-ui';
import { IconMinus, IconCloud, IconCloudStroked } from '@douyinfe/semi-icons';

import iconVariable from '../../../assets/icon-variable.png';
import { GlobalVariableEditor } from './global-variable-editor';
import { FullVariableList } from './full-variable-list';
import { DataMappingEditor } from './data-mapping-editor';
import { SettingsPanel } from './settings-panel';
import { ToolsetPanel } from './toolset-panel';
import { SkillsetPanel } from './skillset-panel';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useUserStore } from '../../../../../stores/userStore';
import { useSkillStore } from '../../../../../stores/domain/skillStore';
import { IPCAPI } from '../../../../../services/ipc/api';

import styles from './index.module.less';

/** Half-filled cloud icon for hybrid execution mode */
const HalfCloudIcon: React.FC<{ size?: number }> = ({ size = 24 }) => (
  <svg width={size} height={size} viewBox="0 0 1024 1024" style={{ display: 'inline-block', verticalAlign: 'middle' }}>
    <defs>
      <clipPath id="hybrid-left">
        <rect x="0" y="0" width="512" height="1024" />
      </clipPath>
      <clipPath id="hybrid-right">
        <rect x="512" y="0" width="512" height="1024" />
      </clipPath>
    </defs>
    <path
      clipPath="url(#hybrid-left)"
      d="M811.4 418.7C765.6 297.9 648.9 212 512.2 212S258.8 297.8 213 418.6C127.3 441.1 64 519.1 64 612c0 110.5 89.5 200 200 200h496c110.5 0 200-89.5 200-200 0-92.8-63.3-170.7-148.6-193.3z"
      fill="#999"
      fillOpacity="0.5"
    />
    <path
      clipPath="url(#hybrid-right)"
      d="M811.4 418.7C765.6 297.9 648.9 212 512.2 212S258.8 297.8 213 418.6C127.3 441.1 64 519.1 64 612c0 110.5 89.5 200 200 200h496c110.5 0 200-89.5 200-200 0-92.8-63.3-170.7-148.6-193.3z"
      fill="#1890ff"
    />
  </svg>
);

type ExecMode = 'local' | 'hybrid' | 'cloud';

const EXEC_MODE_CYCLE: ExecMode[] = ['local', 'hybrid', 'cloud'];

const EXEC_MODE_TOOLTIPS: Record<ExecMode, string> = {
  local: 'Run Locally (click for hybrid)',
  hybrid: 'Hybrid Mode (click for cloud)',
  cloud: 'Run in Cloud (click for local)',
};

/**
 * Persist cloud execution mode to DB and update the Skills page store.
 * Fire-and-forget — errors are logged but don't block the UI toggle.
 */
async function persistExecModeToDB(
  nextRunInCloud: boolean,
  nextHybridCloud: boolean,
) {
  try {
    const skillInfo = useSkillInfoStore.getState().skillInfo;
    if (!skillInfo) return; // No skill loaded yet

    const skillId = (skillInfo as any).skillId || (skillInfo as any).id;
    if (!skillId) return;

    const username = useUserStore.getState().username || '';
    const api = IPCAPI.getInstance();

    // Merge into existing config
    const existingConfig = (skillInfo as any).config || {};
    const localHelperSkillId = useSkillInfoStore.getState().localHelperSkillId;
    const localHelperMachine = useSkillInfoStore.getState().localHelperMachine;
    const helperNameFromStore = (() => {
      try {
        if (!localHelperSkillId || typeof localHelperSkillId !== 'string') return null;
        if (!localHelperSkillId.startsWith('skill_')) return String(localHelperSkillId);
        const store = useSkillStore.getState();
        const found = store.items.find((s: any) => String(s.id) === String(localHelperSkillId));
        return found?.name || null;
      } catch {
        return null;
      }
    })();
    const updatedConfig = {
      ...existingConfig,
      run_in_cloud: nextRunInCloud,
      hybrid_cloud_mode: nextHybridCloud,
      local_helper_skill_id: localHelperSkillId ?? (existingConfig as any)?.local_helper_skill_id ?? null,
      local_helper_skill_name: (existingConfig as any)?.local_helper_skill_name ?? helperNameFromStore ?? null,
      local_helper_machine: localHelperMachine ?? (existingConfig as any)?.local_helper_machine ?? null,
    };

    // IMPORTANT: only send fields that exist on SkillUpdateInput.
    const payload: Record<string, any> = {
      id: skillId,
      config: updatedConfig,
    };

    console.log('[CLOUD_TOGGLE] Persisting exec mode to DB:', { skillId, runInCloud: nextRunInCloud, hybrid: nextHybridCloud });

    const resp = await api.saveAgentSkill(username, payload);

    if (resp && resp.success) {
      console.log('[CLOUD_TOGGLE] DB sync OK');

      // Update Skills page store immediately
      const store = useSkillStore.getState();
      const sid = String((resp as any).data?.skill_id || skillId);
      const existing = store.items.find((s) => String(s.id) === sid);
      if (existing) {
        store.updateItem(sid, { config: updatedConfig } as any);
      }
    } else {
      console.warn('[CLOUD_TOGGLE] DB sync failed:', resp?.error);
    }
  } catch (e) {
    console.warn('[CLOUD_TOGGLE] Error persisting exec mode (non-fatal):', e);
  }
}

export function VariablePanel() {
  const [isOpen, setOpen] = useState<boolean>(false);
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const setRunInCloud = useSkillInfoStore((state) => state.setRunInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const setHybridCloudMode = useSkillInfoStore((state) => state.setHybridCloudMode);

  const currentMode: ExecMode = !runInCloud ? 'local' : hybridCloudMode ? 'hybrid' : 'cloud';

  const handleToggleExecMode = useCallback(() => {
    const idx = EXEC_MODE_CYCLE.indexOf(currentMode);
    const next = EXEC_MODE_CYCLE[(idx + 1) % EXEC_MODE_CYCLE.length];
    let nextRunInCloud = false;
    let nextHybridCloud = false;
    switch (next) {
      case 'local':
        nextRunInCloud = false;
        nextHybridCloud = false;
        break;
      case 'hybrid':
        nextRunInCloud = true;
        nextHybridCloud = true;
        break;
      case 'cloud':
        nextRunInCloud = true;
        nextHybridCloud = false;
        break;
    }
    setRunInCloud(nextRunInCloud);
    setHybridCloudMode(nextHybridCloud);

    // Fire-and-forget: persist to DB + update Skills page store
    persistExecModeToDB(nextRunInCloud, nextHybridCloud);
  }, [currentMode, setRunInCloud, setHybridCloudMode]);

  return (
    <div className={styles['panel-wrapper']}>
      {/* Cloud toggle button - cycles: local -> hybrid -> cloud */}
      <Tooltip content={EXEC_MODE_TOOLTIPS[currentMode]}>
        <Button
          className={`${styles['cloud-toggle-button']}`}
          theme="light"
          onClick={handleToggleExecMode}
        >
          {currentMode === 'cloud' ? (
            <IconCloud size="large" style={{ color: '#1890ff' }} />
          ) : currentMode === 'hybrid' ? (
            <HalfCloudIcon size={24} />
          ) : (
            <IconCloudStroked size="large" style={{ color: '#999', opacity: 0.6 }} />
          )}
        </Button>
      </Tooltip>
      <Tooltip content="Toggle Variable Panel">
        <Button
          className={`${styles['variable-panel-button']} ${isOpen ? styles.close : ''}`}
          theme={isOpen ? 'borderless' : 'light'}
          onClick={() => setOpen((_open) => !_open)}
        >
          {isOpen ? <IconMinus /> : <img src={iconVariable} width={20} height={20} />}
        </Button>
      </Tooltip>
      <Collapsible isOpen={isOpen}>
        <div className={styles['panel-container']}>
          <Tabs>
            <Tabs.TabPane itemKey="variables" tab="Variable List">
              <FullVariableList />
            </Tabs.TabPane>
            <Tabs.TabPane itemKey="global" tab="Global Editor">
              <GlobalVariableEditor />
            </Tabs.TabPane>
            <Tabs.TabPane itemKey="data-mapping" tab="Data Mapping">
              <DataMappingEditor />
            </Tabs.TabPane>
            <Tabs.TabPane itemKey="toolsets" tab="Toolsets">
              <ToolsetPanel />
            </Tabs.TabPane>
            <Tabs.TabPane itemKey="skillsets" tab="Skillsets">
              <SkillsetPanel />
            </Tabs.TabPane>
            <Tabs.TabPane itemKey="settings" tab="Settings">
              <SettingsPanel />
            </Tabs.TabPane>
          </Tabs>
        </div>
      </Collapsible>
    </div>
  );
}
