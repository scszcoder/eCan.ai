/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import React from 'react';
import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { createInferInputsPlugin } from '@flowgram.ai/form-materials';

import { FormHeader, FormContent } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';
import { EventEditor } from './components/event';
import { CodeSaver } from '../../components/code-saver';
import { Outputs } from '../code/components/outputs';
import { Inputs } from '../code/components/inputs';

export const FormRender = ({ form }: FormRenderProps<any>) => (
  <>
    <FormHeader />
    <FormContent>
      <Inputs />
      <EventEditor />
      <CodeSaver form={form} />
      <Outputs />
    </FormContent>
  </>
);

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  effect: defaultFormMeta.effect,
  validate: defaultFormMeta.validate,
  plugins: [createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' })],
};
