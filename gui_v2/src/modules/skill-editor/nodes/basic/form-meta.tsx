/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger, Field, mapValues, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { IFlowValue } from '@flowgram.ai/form-materials';

import { FlowNodeJSON, JsonSchema } from '../../typings';
import { FormHeader, FormContent, FormOutputs, PropertiesEdit } from '../../form-components';
import { FormCallable } from '../../form-components/form-callable';

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => {

  return (
    <>
      <FormHeader />
      <FormContent>
      <Field
          name="inputs.properties"
          render={({
            field: { value: propertiesSchemaValue, onChange: propertiesSchemaChange },
          }: FieldRenderProps<Record<string, JsonSchema>>) => (
            <Field<Record<string, IFlowValue>> name="inputsValues">
              {({ field: { value: propertiesValue, onChange: propertiesValueChange } }) => {
                const onChange = (newProperties: Record<string, JsonSchema>) => {
                  const newPropertiesValue = mapValues(newProperties, (v) => v.default);
                  const newPropetiesSchema = mapValues(newProperties, (v) => {
                    delete v.default;
                    return v;
                  });
                  propertiesValueChange(newPropertiesValue);
                  propertiesSchemaChange(newPropetiesSchema);
                };
                const value = mapValues(propertiesSchemaValue, (v, key) => ({
                  ...v,
                  default: propertiesValue?.[key],
                }));
                return (
                  <>
                    <PropertiesEdit value={value} onChange={onChange} useFx={true} />
                  </>
                );
              }}
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