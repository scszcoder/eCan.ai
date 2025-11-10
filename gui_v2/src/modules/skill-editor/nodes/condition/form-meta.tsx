/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';
import React from 'react';
import { useNodeRenderContext } from '../../hooks';
import { autoRenameRefEffect } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { FormHeader, FormContent } from '../../form-components';
import { ConditionInputs } from './condition-inputs';
import { useNodeFlipStore } from '../../stores/node-flip-store';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <ConditionInputs />
    </FormContent>
    <ConditionPortMarkers />
  </>
);

// Component to render port markers with H-flip support (engine auto-binds markers)
const ConditionPortMarkers: React.FC = () => {
  const { node } = useNodeRenderContext();
  const { isFlipped } = useNodeFlipStore();
  const hFlip = isFlipped(node.id);
  
  const portStyle = (top: number) => ({
    position: 'absolute' as const,
    ...(hFlip ? { left: -6, right: 'auto' } : { right: -6, left: 'auto' }),
    top,
    width: 12,
    height: 12,
    borderRadius: '50%',
    background: '#3b82f6',
    border: '2px solid #fff',
    cursor: 'crosshair',
    pointerEvents: 'auto' as const
  });
  
  return (
    <>
      {/* Dynamic port markers for condition outputs */}
      <div
        data-port-id="if_out"
        data-port-key="if_out"
        data-port-type="output"
        data-port-location={hFlip ? 'left' : 'right'}
        data-port-direction="output"
        data-port-group="conditions"
        data-port-name="if_out"
        data-port="true"
        style={{ ...portStyle(60), zIndex: 100 }}
        title="if"
      />
      <div
        data-port-id="else_out"
        data-port-key="else_out"
        data-port-type="output"
        data-port-location={hFlip ? 'left' : 'right'}
        data-port-direction="output"
        data-port-group="conditions"
        data-port-name="else_out"
        data-port="true"
        style={{ ...portStyle(80), zIndex: 110 }}
        title="else"
      />
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: {
    title: ({ value }: { value: string }) => (value ? undefined : 'Title is required'),
    'conditions.*': ({ value }) => {
      const key: string | undefined = value?.key;
      const isElse = typeof key === 'string' && key.startsWith('else_');
      if (isElse) return undefined;
      if (!value?.value) return 'Condition is required';
      return undefined;
    },
  },
  effect: {
    conditions: autoRenameRefEffect,
  },
};
