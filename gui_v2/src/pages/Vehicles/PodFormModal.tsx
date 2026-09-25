/**
 * Create / edit a pod.
 *
 * Two rules this form exists to honour:
 *
 * 1. Cost is shown at the point of decision. `always_on` is a recurring charge
 *    whether or not anyone talks to the agent, so the figure sits next to the
 *    toggle rather than in a billing page discovered later.
 * 2. It only offers capabilities a skill can actually require
 *    (`types/domain/placement.ts`). A pod advertising a word no skill knows is
 *    as useless as a skill requiring a word no pod advertises.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Modal, Form, Input, Select, InputNumber, Radio, Alert, Typography } from 'antd';
import {
  CAPABILITIES,
  CAPABILITY_LABELS,
  isDedicatedCapability,
} from '@/types/domain/placement';
import {
  DEFAULT_IDLE_SHUTDOWN_MINUTES,
  LIFECYCLE_OPTIONS,
  POD_SIZES,
  describeSize,
  estimatePodCost,
  matchSize,
  sizeById,
  type Pod,
  type PodLifecycle,
} from '@/types/domain/pod';

const { Text } = Typography;

interface PodFormModalProps {
  open: boolean;
  pod?: Pod | null;
  /** How many pods this owner may have, and how many exist. */
  limits?: { max_pods: number; used_pods: number } | null;
  onCancel: () => void;
  onSubmit: (values: Record<string, any>) => Promise<void> | void;
}

const PodFormModal: React.FC<PodFormModalProps> = ({
  open,
  pod,
  limits,
  onCancel,
  onSubmit,
}) => {
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [sizeId, setSizeId] = useState<string>('standard');
  const [lifecycle, setLifecycle] = useState<PodLifecycle>('always_on');
  const [replicas, setReplicas] = useState<number>(1);

  const isEdit = Boolean(pod?.id);

  useEffect(() => {
    if (!open) return;
    const matched = matchSize(pod?.cpu_cores, pod?.memory_gb);
    const nextSize = matched?.id || 'standard';
    const nextLifecycle = (pod?.lifecycle as PodLifecycle) || 'always_on';
    const nextReplicas = pod?.desired_replicas || 1;

    setSizeId(nextSize);
    setLifecycle(nextLifecycle);
    setReplicas(nextReplicas);
    form.setFieldsValue({
      name: pod?.name || '',
      description: pod?.description || '',
      size_id: nextSize,
      lifecycle: nextLifecycle,
      desired_replicas: nextReplicas,
      idle_shutdown_minutes:
        pod?.idle_shutdown_minutes ?? DEFAULT_IDLE_SHUTDOWN_MINUTES,
      capabilities: pod?.capabilities || [],
    });
  }, [open, pod, form]);

  const size = sizeById(sizeId) || POD_SIZES[1];
  const cost = useMemo(
    () => estimatePodCost(size.cpu, size.memory_gb, lifecycle, replicas),
    [size, lifecycle, replicas],
  );

  const atLimit =
    !isEdit && limits ? limits.used_pods >= limits.max_pods : false;

  const capabilityOptions = [
    ...CAPABILITIES.map((cap) => ({
      value: cap,
      label: CAPABILITY_LABELS[cap] || cap,
    })),
    // A dedicated:<agent> capability is written by the agent page. Show any
    // already on this pod so editing the form cannot silently strip it.
    ...(pod?.capabilities || [])
      .filter((c) => isDedicatedCapability(c))
      .map((c) => ({ value: c, label: `${c} (dedicated)` })),
  ];

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await onSubmit({
        ...values,
        id: pod?.id,
        cpu_cores: size.cpu,
        memory_gb: size.memory_gb,
        max_concurrent_tasks: size.concurrency,
        idle_shutdown_minutes:
          values.lifecycle === 'on_demand' ? values.idle_shutdown_minutes : null,
      });
      form.resetFields();
    } catch {
      // validateFields already surfaced the problem on the fields themselves
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title={isEdit ? 'Edit pod' : 'Create pod'}
      open={open}
      onOk={handleOk}
      onCancel={() => {
        form.resetFields();
        onCancel();
      }}
      confirmLoading={submitting}
      okButtonProps={{ disabled: atLimit }}
      width={560}
      destroyOnHidden
    >
      {atLimit && limits && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`This account is limited to ${limits.max_pods} pods`}
          description={`${limits.used_pods} already exist. Delete one, or ask for the limit to be raised, before creating another.`}
        />
      )}

      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label="Name"
          rules={[{ required: true, message: 'Give the pod a name' }]}
        >
          <Input placeholder="e.g. chat-pod-1" />
        </Form.Item>

        <Form.Item name="description" label="Description">
          <Input placeholder="What this pod is for" />
        </Form.Item>

        <Form.Item name="size_id" label="Size">
          <Select
            onChange={(value) => setSizeId(value as string)}
            options={POD_SIZES.map((s) => ({
              value: s.id,
              label: `${s.id} — ${describeSize(s)}`,
            }))}
          />
        </Form.Item>

        <Form.Item name="lifecycle" label="Lifecycle">
          <Radio.Group
            onChange={(e) => setLifecycle(e.target.value as PodLifecycle)}
            optionType="button"
            buttonStyle="solid"
            options={LIFECYCLE_OPTIONS.map((o) => ({
              value: o.value,
              label: o.label,
            }))}
          />
        </Form.Item>
        <Text type="secondary" style={{ display: 'block', marginTop: -12, marginBottom: 16 }}>
          {LIFECYCLE_OPTIONS.find((o) => o.value === lifecycle)?.help}
        </Text>

        {lifecycle === 'on_demand' && (
          <Form.Item
            name="idle_shutdown_minutes"
            label="Shut down after idle (minutes)"
            extra="Measured by the fleet from queue emptiness, not by the pod reporting itself idle."
          >
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>
        )}

        <Form.Item
          name="desired_replicas"
          label="Replicas"
          extra="How many of this pod you want. The fleet converges towards it; the pod list shows what is actually running."
        >
          <InputNumber
            min={1}
            max={20}
            style={{ width: '100%' }}
            onChange={(value) => setReplicas(Number(value) || 1)}
          />
        </Form.Item>

        <Form.Item
          name="capabilities"
          label="Capabilities"
          extra="What this pod advertises. A turn is only placed here if everything the skill requires is on this list."
        >
          <Select
            mode="multiple"
            allowClear
            placeholder="No special capabilities"
            options={capabilityOptions}
          />
        </Form.Item>

        <Alert
          type={lifecycle === 'always_on' ? 'info' : 'success'}
          showIcon
          message={
            lifecycle === 'always_on'
              ? `About ¥${cost.monthly_cny.toFixed(0)} per month`
              : `Up to ¥${cost.monthly_cny.toFixed(0)} per month`
          }
          description={
            lifecycle === 'always_on'
              ? `¥${cost.hourly_cny.toFixed(2)}/hour × ${replicas} replica${replicas > 1 ? 's' : ''}, charged around the clock — whether or not anyone talks to the agent.`
              : `¥${cost.hourly_cny.toFixed(2)}/hour × ${replicas} replica${replicas > 1 ? 's' : ''}, but only while there is work. The figure above is the ceiling if it never goes idle.`
          }
        />
      </Form>
    </Modal>
  );
};

export default PodFormModal;
