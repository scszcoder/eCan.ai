/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useState } from 'react';

import { Button, Collapsible, Tabs, Tooltip, Checkbox, Select, Typography } from '@douyinfe/semi-ui';
import { IconMinus, IconCloud, IconCloudStroked } from '@douyinfe/semi-icons';

import iconVariable from '../../../assets/icon-variable.png';
import { GlobalVariableEditor } from './global-variable-editor';
import { FullVariableList } from './full-variable-list';
import { DataMappingEditor } from './data-mapping-editor';
import { SettingsPanel } from './settings-panel';
import { useSkillInfoStore } from '../../../stores/skill-info-store';

import styles from './index.module.less';

export function VariablePanel() {
  const [isOpen, setOpen] = useState<boolean>(false);
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const setRunInCloud = useSkillInfoStore((state) => state.setRunInCloud);

  return (
    <div className={styles['panel-wrapper']}>
      {/* Cloud toggle button - positioned above the var button */}
      <Tooltip content={runInCloud ? "Run in Cloud (click to run locally)" : "Run Locally (click to run in cloud)"}>
        <Button
          className={`${styles['cloud-toggle-button']}`}
          theme="light"
          onClick={() => setRunInCloud(!runInCloud)}
        >
          {runInCloud ? (
            <IconCloud size="large" style={{ color: '#1890ff' }} />
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
            <Tabs.TabPane itemKey="settings" tab="Settings">
              <SettingsPanel />
            </Tabs.TabPane>
          </Tabs>
        </div>
      </Collapsible>
    </div>
  );
}