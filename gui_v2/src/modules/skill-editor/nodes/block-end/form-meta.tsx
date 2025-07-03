/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';
import { provideJsonSchemaOutputs, syncVariableTitle } from '@flowgram.ai/form-materials';
import { Avatar } from '@douyinfe/semi-ui';

import { FlowNodeJSON } from '../../typings';
import iconEnd from '../../assets/icon-end.jpg';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => (
  <>
    <div
      style={{
        width: 60,
        height: 60,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Avatar
        shape="circle"
        style={{
          width: 40,
          height: 40,
          borderRadius: '50%',
          cursor: 'move',
        }}
        alt="Icon"
        src={iconEnd}
      />
    </div>
  </>
);

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: {
    title: ({ value }: { value: string }) => (value ? undefined : 'Title is required'),
  },
  effect: {
    title: syncVariableTitle,
    outputs: provideJsonSchemaOutputs,
  },
};
