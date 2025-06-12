import { Field, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { CallableFunction } from '../../typings/callable';
import { FormItem } from '../form-item';
import { CallableSelector } from '../../components/callable/callable-selector';
import { systemFunctions } from '../../components/callable/test-data';

export function FormCallable() {
  return (
    <Field<CallableFunction> name="data.callable">
      {({ field: { value, onChange } }: FieldRenderProps<CallableFunction>) => (
        <FormItem name="tool" type="custom" required={false}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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