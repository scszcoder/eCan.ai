import React from 'react';
import { Field, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { CallableFunction } from '../../typings/callable';
import { FormItem } from '../form-item';
import { FunctionOutlined } from '@ant-design/icons';
import { CallableSelector } from '../../components/form-components/callable/callable-selector';
import { systemFunctions } from '../../components/form-components/callable/test-data';

export function FormCallable() {
  return (
    <Field<CallableFunction> name="data.callable">
      {({ field: { value, onChange } }: FieldRenderProps<CallableFunction>) => (
        <FormItem name="callable" type="function" required>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FunctionOutlined style={{ fontSize: '16px', color: '#666' }} />
            <CallableSelector
              value={value}
              onChange={(func) => {
                onChange(func);
              }}
              onEdit={onChange}
              onAdd={() => {
                const newFunc: CallableFunction = {
                  name: '',
                  desc: '',
                  params: {
                    type: 'object',
                    properties: {}
                  },
                  returns: {
                    type: 'object',
                    properties: {}
                  },
                  type: 'custom'
                };
                onChange(newFunc);
              }}
              systemFunctions={systemFunctions}
            />
          </div>
        </FormItem>
      )}
    </Field>
  );
} 