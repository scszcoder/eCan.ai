/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';
import { autoRenameRefEffect } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { FormHeader, FormContent } from '../../form-components';
import { ConditionInputs } from './condition-inputs';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <ConditionInputs />
    </FormContent>
    {/* Dynamic port markers for condition outputs */}
    <div
      data-port-id="if_out"
      data-port-type="output"
      data-port-direction="output"
      data-port-group="conditions"
      data-port-name="if_out"
      data-port="true"
      style={{ 
        position: 'absolute', 
        right: -6, 
        top: 60, 
        width: 12, 
        height: 12, 
        borderRadius: '50%',
        background: '#3b82f6',
        border: '2px solid #fff',
        zIndex: 100,
        cursor: 'crosshair',
        pointerEvents: 'auto'
      }}
      title="if"
    />
    <div
      data-port-id="else_out"
      data-port-type="output"
      data-port-direction="output"
      data-port-group="conditions"
      data-port-name="else_out"
      data-port="true"
      style={{ 
        position: 'absolute', 
        right: -6, 
        top: 80, 
        width: 12, 
        height: 12, 
        borderRadius: '50%',
        background: '#3b82f6',
        border: '2px solid #fff',
        zIndex: 110,
        cursor: 'crosshair',
        pointerEvents: 'auto'
      }}
      title="else"
    />
  </>
);

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
