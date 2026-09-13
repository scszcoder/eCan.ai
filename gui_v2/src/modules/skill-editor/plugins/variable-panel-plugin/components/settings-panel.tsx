/**
 * Settings Panel for Skill Editor
 * Placement declarations (residency / lifetime / requires) and the legacy
 * hybrid-cloud settings.
 */

import { useEffect } from 'react';
import { Checkbox, Select, Input, Typography } from '@douyinfe/semi-ui';
import { useSkillInfoStore } from '../../../stores/skill-info-store';
import {
  CAPABILITIES,
  CAPABILITY_LABELS,
  LIFETIME_OPTIONS,
  RESIDENCY_OPTIONS,
  isDedicatedCapability,
  type Lifetime,
  type Residency,
} from '../../../../../types/domain/placement';
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

  const residency = useSkillInfoStore((state) => state.residency);
  const setResidency = useSkillInfoStore((state) => state.setResidency);
  const lifetime = useSkillInfoStore((state) => state.lifetime);
  const setLifetime = useSkillInfoStore((state) => state.setLifetime);
  const requires = useSkillInfoStore((state) => state.requires);
  const setRequires = useSkillInfoStore((state) => state.setRequires);
  
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

  const residencyHelp =
    RESIDENCY_OPTIONS.find((o) => o.value === residency)?.help ?? '';
  const lifetimeHelp = LIFETIME_OPTIONS.find((o) => o.value === lifetime)?.help ?? '';

  // Only offers capabilities a pod can actually advertise, so a skill cannot
  // quietly declare a requirement nothing will ever satisfy. dedicated:<agent>
  // requirements are written by the agent page, not typed here, but any that
  // already exist stay visible rather than being silently dropped.
  const capabilityOptions = [
    ...CAPABILITIES.map((cap) => ({
      value: cap,
      label: CAPABILITY_LABELS[cap] || cap,
    })),
    ...requires
      .filter((r) => isDedicatedCapability(r) || !CAPABILITIES.includes(r as any))
      .map((r) => ({ value: r, label: r })),
  ];

  return (
    <div className={styles['settings-panel']}>
      <div className={styles['settings-section']}>
        <Text strong>Placement</Text>
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          Where this skill may run, and for how long. The scheduler places work
          with these; they do not change how the skill executes today.
        </Text>

        <div className={styles['settings-item']} style={{ marginTop: 16 }}>
          <Text style={{ display: 'block', marginBottom: 8 }}>Residency</Text>
          <Select
            style={{ width: '100%' }}
            value={residency}
            onChange={(value) => setResidency(value as Residency)}
            optionList={RESIDENCY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
          <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
            {residencyHelp}
          </Text>
        </div>

        <div className={styles['settings-item']} style={{ marginTop: 16 }}>
          <Text style={{ display: 'block', marginBottom: 8 }}>Lifetime</Text>
          <Select
            style={{ width: '100%' }}
            value={lifetime}
            onChange={(value) => setLifetime(value as Lifetime)}
            optionList={LIFETIME_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          />
          <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
            {lifetimeHelp}
          </Text>
        </div>

        <div className={styles['settings-item']} style={{ marginTop: 16 }}>
          <Text style={{ display: 'block', marginBottom: 8 }}>Requires</Text>
          <Select
            multiple
            style={{ width: '100%' }}
            placeholder="No requirements — any pod can run this"
            value={requires}
            onChange={(value) => setRequires((value as string[]) || [])}
            optionList={capabilityOptions}
            showClear
          />
          <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
            Only a pod advertising all of these can run this skill. Each one
            narrows where the work can go, so ask for what it genuinely needs.
          </Text>
        </div>
      </div>

      <div className={styles['settings-section']} style={{ marginTop: 24 }}>
        <Text strong>Cloud Execution Settings</Text>
        <Text type="tertiary" size="small" style={{ display: 'block', marginTop: 4 }}>
          The existing launcher path. Still what runs a cloud task today;
          Placement above replaces it per task as they move onto the queue.
        </Text>
        
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
