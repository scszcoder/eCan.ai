/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';

import { FlowNodeJSON } from '../../typings';
import { defaultFormMeta } from '../default-form-meta';
import { FormHeader, FormContent } from '../../form-components';

export const renderForm = (_props: FormRenderProps<FlowNodeJSON>) => {
  return (
    <>
      <FormHeader />
      <FormContent>
        {/** Task node editor */}
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: defaultFormMeta.validate,
  effect: defaultFormMeta.effect,
  plugins: [],
};
