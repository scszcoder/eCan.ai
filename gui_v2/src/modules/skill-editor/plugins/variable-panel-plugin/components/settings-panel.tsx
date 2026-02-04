/**
 * Settings Panel for Skill Editor
 * Contains hybrid cloud mode settings and local helper skill selection
 */

import { useEffect } from 'react';
import { Checkbox, Select, Input, Typography } from '@douyinfe/semi-ui';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import { useSkillStore } from '../../../../../stores/domain/skillStore';
import { useUserStore } from '../../../../../stores/userStore';
import { IPCAPI } from '../../../../../services/ipc/api';

import styles from './index.module.less';

const { Text } = Typography;

export function SettingsPanel() {
  const runInCloud = useSkillInfoStore((state) => state.runInCloud);
  const hybridCloudMode = useSkillInfoStore((state) => state.hybridCloudMode);
  const setHybridCloudMode = useSkillInfoStore((state) => state.setHybridCloudMode);
  const localHelperSkillId = useSkillInfoStore((state) => state.localHelperSkillId);
  const setLocalHelperSkillId = useSkillInfoStore((state) => state.setLocalHelperSkillId);
  const localHelperMachine = useSkillInfoStore((state) => state.localHelperMachine);
  const setLocalHelperMachine = useSkillInfoStore((state) => state.setLocalHelperMachine);
  
  const skills = useSkillStore((state) => state.items);
  const fetchSkills = useSkillStore((state) => state.fetchItems);
  const username = useUserStore((state) => state.username);

  // Fetch skills on mount if not already loaded
  useEffect(() => {
    if (skills.length === 0 && username) {
      fetchSkills(username);
    }
  }, [skills.length, username, fetchSkills]);

  // Auto-fill hostname when hybrid mode is enabled and no machine is set
  useEffect(() => {
    if (hybridCloudMode && runInCloud && !localHelperMachine) {
      // Fetch hostname from backend
      IPCAPI.getInstance().getHostname<{ hostname: string }>().then((response) => {
        if (response.success && response.data?.hostname) {
          setLocalHelperMachine(response.data.hostname);
        }
      }).catch((err) => {
        console.warn('Failed to get hostname:', err);
      });
    }
  }, [hybridCloudMode, runInCloud, localHelperMachine, setLocalHelperMachine]);

  // Reset hybrid cloud mode when switching to local execution
  useEffect(() => {
    if (!runInCloud && hybridCloudMode) {
      setHybridCloudMode(false);
      setLocalHelperSkillId(null);
      setLocalHelperMachine(null);
    }
  }, [runInCloud, hybridCloudMode, setHybridCloudMode, setLocalHelperSkillId, setLocalHelperMachine]);

  const skillOptions = skills.map((skill) => ({
    value: skill.id,
    label: skill.name || skill.id,
  }));

  return (
    <div className={styles['settings-panel']}>
      <div className={styles['settings-section']}>
        <Text strong>Cloud Execution Settings</Text>
        
        <div className={styles['settings-item']} style={{ marginTop: 16 }}>
          <Checkbox
            checked={hybridCloudMode}
            disabled={!runInCloud}
            onChange={(e) => {
              const checked = e.target.checked;
              setHybridCloudMode(checked);
              if (!checked) {
                setLocalHelperSkillId(null);
                setLocalHelperMachine(null);
              }
            }}
          >
            <span style={{ color: runInCloud ? 'inherit' : '#999' }}>
              Hybrid Cloud Mode
            </span>
          </Checkbox>
          <Text type="tertiary" size="small" style={{ display: 'block', marginLeft: 24, marginTop: 4 }}>
            {runInCloud 
              ? 'Enable to use a local helper skill that works with this cloud skill'
              : 'Only available when skill is set to run in cloud'}
          </Text>
        </div>

        {hybridCloudMode && runInCloud && (
          <>
            <div className={styles['settings-item']} style={{ marginTop: 16, marginLeft: 24 }}>
              <Text style={{ display: 'block', marginBottom: 8 }}>Local Helper Skill</Text>
              <Select
                placeholder="Select a local helper skill"
                style={{ width: '100%' }}
                value={localHelperSkillId}
                onChange={(value) => setLocalHelperSkillId(value as string)}
                optionList={skillOptions}
                filter
                showClear
              />
              <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
                This skill will run locally and coordinate with the cloud skill
              </Text>
            </div>

            <div className={styles['settings-item']} style={{ marginTop: 16, marginLeft: 24 }}>
              <Text style={{ display: 'block', marginBottom: 8 }}>Local Helper Machine</Text>
              <Input
                placeholder="Enter machine hostname"
                style={{ width: '100%' }}
                value={localHelperMachine || ''}
                onChange={(value) => setLocalHelperMachine(value || null)}
              />
              <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
                The hostname of the machine running the local helper skill
              </Text>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
