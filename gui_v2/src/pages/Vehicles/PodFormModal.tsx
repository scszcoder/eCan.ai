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
import { useTranslation } from 'react-i18next';
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
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [sizeId, setSizeId] = useState<string>('standard');
  const [lifecycle, setLifecycle] = useState<PodLifecycle>('always_on');
  const [replicas, setReplicas] = useState<number>(1);

  const isEdit = Boolean(pod?.id);

  const K = 'pages.vehicles.pod.form';

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
      label: t(`${K}.cap.${cap}`, { defaultValue: CAPABILITY_LABELS[cap] || cap }),
    })),
    // A dedicated:<agent> capability is written by the agent page. Show any
    // already on this pod so editing the form cannot silently strip it.
    ...(pod?.capabilities || [])
      .filter((c) => isDedicatedCapability(c))
      .map((c) => ({ value: c, label: t(`${K}.capabilityDedicated`, { cap: c }) })),
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
      title={isEdit ? t(`${K}.titleEdit`) : t(`${K}.titleCreate`)}
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
          message={t(`${K}.limitTitle`, { max: limits.max_pods })}
          description={t(`${K}.limitDesc`, { used: limits.used_pods })}
        />
      )}

      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t(`${K}.nameLabel`)}
          rules={[{ required: true, message: t(`${K}.nameRequired`) }]}
        >
          <Input placeholder={t(`${K}.namePlaceholder`)} />
        </Form.Item>

        <Form.Item name="description" label={t(`${K}.descriptionLabel`)}>
          <Input placeholder={t(`${K}.descriptionPlaceholder`)} />
        </Form.Item>

        <Form.Item name="size_id" label={t(`${K}.sizeLabel`)}>
          <Select
            onChange={(value) => setSizeId(value as string)}
            options={POD_SIZES.map((s) => ({
              value: s.id,
              label: t(`${K}.sizeOption`, {
                id: s.id,
                desc: t(`${K}.sizeDesc`, {
                  cpu: s.cpu,
                  mem: s.memory_gb,
                  conc: s.concurrency,
                }),
              }),
            }))}
          />
        </Form.Item>

        <Form.Item name="lifecycle" label={t(`${K}.lifecycleLabel`)}>
          <Radio.Group
            onChange={(e) => setLifecycle(e.target.value as PodLifecycle)}
            optionType="button"
            buttonStyle="solid"
            options={LIFECYCLE_OPTIONS.map((o) => ({
              value: o.value,
              label:
                o.value === 'always_on'
                  ? t(`${K}.lifecycleAlwaysOn`)
                  : t(`${K}.lifecycleOnDemand`),
            }))}
          />
        </Form.Item>
        <Text type="secondary" style={{ display: 'block', marginTop: -12, marginBottom: 16 }}>
          {lifecycle === 'always_on'
            ? t(`${K}.lifecycleAlwaysOnHelp`)
            : t(`${K}.lifecycleOnDemandHelp`)}
        </Text>

        {lifecycle === 'on_demand' && (
          <Form.Item
            name="idle_shutdown_minutes"
            label={t(`${K}.idleLabel`)}
            extra={t(`${K}.idleExtra`)}
          >
            <InputNumber min={1} max={1440} style={{ width: '100%' }} />
          </Form.Item>
        )}

        <Form.Item
          name="desired_replicas"
          label={t(`${K}.replicasLabel`)}
          extra={t(`${K}.replicasExtra`)}
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
          label={t(`${K}.capabilitiesLabel`)}
          extra={t(`${K}.capabilitiesExtra`)}
        >
          <Select
            mode="multiple"
            allowClear
            placeholder={t(`${K}.capabilitiesPlaceholder`)}
            options={capabilityOptions}
          />
        </Form.Item>

        <Alert
          type={lifecycle === 'always_on' ? 'info' : 'success'}
          showIcon
          message={
            lifecycle === 'always_on'
              ? t(`${K}.costAlwaysOnTitle`, { cost: cost.monthly_cny.toFixed(0) })
              : t(`${K}.costOnDemandTitle`, { cost: cost.monthly_cny.toFixed(0) })
          }
          description={
            lifecycle === 'always_on'
              ? t(`${K}.costAlwaysOnDesc`, {
                  hourly: cost.hourly_cny.toFixed(2),
                  count: replicas,
                })
              : t(`${K}.costOnDemandDesc`, {
                  hourly: cost.hourly_cny.toFixed(2),
                  count: replicas,
                })
          }
        />
      </Form>
    </Modal>
  );
};

export default PodFormModal;
