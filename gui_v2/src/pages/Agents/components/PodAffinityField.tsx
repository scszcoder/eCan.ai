/**
 * Where an agent prefers to run — a preference, never a binding.
 *
 * The word matters, which is why it is spelled out here: under a hard binding a
 * dead pod strands its conversations, draining means reassigning agents first,
 * and a busy pod blocks its agents. Under soft affinity none of that happens,
 * because any eligible pod can resume any conversation from its checkpoint. So
 * this field says "prefer", and the UI must keep saying it.
 *
 * Real isolation is the separate checkbox, and it is expressed as a
 * capability (`dedicated:<agent-id>` on the pod) rather than a relationship —
 * scheduling, not ownership. It costs availability, and says so.
 *
 * Dedication is DERIVED, not stored twice: an agent is dedicated to a pod
 * exactly when that pod advertises `dedicated:<agent-id>`. One source of truth,
 * so the two can never disagree.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Checkbox, Select, Space, Typography, message } from 'antd';
import { IPCAPI } from '@/services/ipc/api';
import { dedicatedCapability } from '@/types/domain/placement';
import type { Pod } from '@/types/domain/pod';
import { logger } from '@/utils/logger';

const { Text } = Typography;

interface PodAffinityFieldProps {
  /** Supplied by antd Form via the enclosing Form.Item (name="vehicle_id"). */
  value?: string | null;
  onChange?: (value: string | null) => void;
  disabled?: boolean;
  agentId?: string;
  /** Machines and pods alike — an agent may prefer either. */
  vehicles: any[];
}

const PodAffinityField: React.FC<PodAffinityFieldProps> = ({
  value,
  onChange,
  disabled,
  agentId,
  vehicles,
}) => {
  const [pods, setPods] = useState<Pod[]>([]);
  const [saving, setSaving] = useState(false);

  const loadPods = useCallback(async () => {
    try {
      const resp = await IPCAPI.getInstance().getPods<any>();
      if (resp?.success && resp.data) setPods(resp.data.pods || []);
    } catch (e) {
      logger.warn('[PodAffinityField] could not load pods:', e);
    }
  }, []);

  useEffect(() => {
    loadPods();
  }, [loadPods]);

  const selectedPod = pods.find((p) => p.id === value);
  const capability = agentId ? dedicatedCapability(agentId) : '';
  const isDedicated = Boolean(
    capability && selectedPod?.capabilities?.includes(capability),
  );

  const handleDedicatedChange = async (checked: boolean) => {
    if (!selectedPod || !capability) return;
    setSaving(true);
    try {
      const next = checked
        ? Array.from(new Set([...(selectedPod.capabilities || []), capability]))
        : (selectedPod.capabilities || []).filter((c) => c !== capability);

      const resp = await IPCAPI.getInstance().savePod<any>({
        id: selectedPod.id,
        name: selectedPod.name,
        description: selectedPod.description,
        cpu_cores: selectedPod.cpu_cores,
        memory_gb: selectedPod.memory_gb,
        lifecycle: selectedPod.lifecycle,
        idle_shutdown_minutes: selectedPod.idle_shutdown_minutes,
        desired_replicas: selectedPod.desired_replicas,
        max_concurrent_tasks: selectedPod.max_concurrent_tasks,
        capabilities: next,
      });

      if (resp?.success) {
        message.success(
          checked
            ? 'This pod is now dedicated to this agent'
            : 'This pod is shared again',
        );
        loadPods();
      } else {
        message.error(resp?.error?.message || 'Could not change the pod');
      }
    } finally {
      setSaving(false);
    }
  };

  const options = vehicles.map((v: any, index: number) => ({
    key: v.id || `vehicle-${index}`,
    value: v.id,
    label: `${v.name || v.id}${v.ip ? ` (${v.ip})` : ''}`,
  }));

  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Select
        id="agent-vehicle"
        disabled={disabled}
        allowClear
        value={value || undefined}
        onChange={(next) => onChange?.(next ?? null)}
        placeholder="No preference — any pod can run this agent"
        options={options}
        getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
        aria-label="Preferred pod"
      />
      <Text type="secondary" style={{ fontSize: 12 }}>
        A preference, not a rule: work goes here when it can, and anywhere
        eligible when it cannot. Nothing is stranded if this pod goes down.
      </Text>

      {selectedPod && (
        <>
          <Checkbox
            checked={isDedicated}
            disabled={disabled || saving || !agentId}
            onChange={(e) => handleDedicatedChange(e.target.checked)}
          >
            Dedicate this pod to this agent
          </Checkbox>
          {isDedicated && (
            <Alert
              type="warning"
              showIcon
              message="This agent now waits for this pod"
              description={`Only a pod advertising ${capability} can run its work. That is real isolation, and it costs availability: if this pod is down, this agent's replies wait rather than moving elsewhere.`}
            />
          )}
        </>
      )}
    </Space>
  );
};

export default PodAffinityField;
