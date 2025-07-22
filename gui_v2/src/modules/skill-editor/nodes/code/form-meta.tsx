/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { createInferInputsPlugin } from '@flowgram.ai/form-materials';
import { Divider } from '@douyinfe/semi-ui';

import { FormHeader, FormContent, FormOutputs } from '../../form-components';
import { CodeNodeJSON } from './types';
import { Outputs } from './components/outputs';
import { Inputs } from './components/inputs';
import { Code } from './components/code';
import { defaultFormMeta } from '../default-form-meta';

export const FormRender = ({ form }: FormRenderProps<CodeNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <Inputs />
      <Code />
      <Outputs />
      <FormOutputs />
    </FormContent>
  </>
);

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  effect: defaultFormMeta.effect,
  plugins: [createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' })],
};
