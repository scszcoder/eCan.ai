import { Field, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { CallableFunction, createDefaultCallableFunction } from '../../typings/callable';
import { FormItem } from '../form-item';
import { CallableSelector } from '../../components/callable/callable-selector';
import { systemFunctions } from '../../components/callable/test-data';
import { Feedback } from '../feedback';
import { useNodeRenderContext } from '../../hooks';

export function FormCallable() {
  const { readonly } = useNodeRenderContext();
  return (
    <Field<CallableFunction> name="data.callable">
      {({ field, fieldState }: FieldRenderProps<CallableFunction>) => (
        <FormItem
          name="tool" type="object" required={false}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CallableSelector
              readonly={readonly}
              value={field.value}
              onChange={(func) => {
                field.onChange(func);
              }}
              onAdd={() => {
                if (readonly) return;
                field.onChange(createDefaultCallableFunction());
              }}
              systemFunctions={systemFunctions}
            />
          </div>
          <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
        </FormItem>
      )}
    </Field>
  );
}