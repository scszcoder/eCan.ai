/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger, Field, mapValues, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { IFlowValue, InputsValues } from '@flowgram.ai/form-materials';

import { FlowNodeJSON, JsonSchema } from '../../typings';
import { FormHeader, FormContent, FormOutputs } from '../../form-components';
import { FormCallable } from '../../form-components/form-callable';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => {

  return (
    <>
      <FormHeader />
      <FormContent>
      <Field name="inputs.properties"
        render={() => (
          <Field<Record<string, IFlowValue | undefined> | undefined> name="inputsValues">
            {({ field: { value, onChange } }) => (
              <InputsValues value={value} onChange={(_v) => onChange(_v)} />
            )}
          </Field>
        )}
      />
        <div style={{ 
          height: '1px', 
          background: '#e8e8e8', 
          margin: '12px 0',
          width: '100%' 
        }} />
        <FormCallable />
        <FormOutputs />
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: {
    title: ({ value }) => (value ? undefined : 'Title is required'),
  },
}; 