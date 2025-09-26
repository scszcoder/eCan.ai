/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger, Field } from '@flowgram.ai/free-layout-editor';
import { IFlowValue, InputsValues, createInferInputsPlugin, DisplayOutputs } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { defaultFormMeta } from '../default-form-meta';
import { FormHeader, FormContent } from '../../form-components';
import { FormCallable } from '../../form-components/form-callable';
import { useNodeStateSchema } from '../../../../stores/nodeStateSchemaStore';
import NodeStatePanel from '../../components/node-state/NodeStatePanel';

export const renderForm = (_props: FormRenderProps<FlowNodeJSON>) => {
  const { schema, loading } = useNodeStateSchema();

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
        <DisplayOutputs displayFromScope />

        {/* Node State editable panel */}
        <div style={{ 
          height: '1px', 
          background: '#e8e8e8', 
          margin: '12px 0',
          width: '100%' 
        }} />
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Node State</div>
        <Field<any> name="state">
          {({ field: { value, onChange } }) => (
            loading || !schema ? (
              <div style={{ color: '#999' }}>Loading node state schema...</div>
            ) : (
              <NodeStatePanel schema={schema} value={value ?? {}} onChange={onChange} />
            )
          )}
        </Field>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: defaultFormMeta.validate,
  effect: defaultFormMeta.effect,
  plugins: [
    createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' }),
  ],
};
