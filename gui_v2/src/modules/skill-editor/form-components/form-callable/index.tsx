import { Field, FieldRenderProps } from '@flowgram.ai/free-layout-editor';
import { CallableFunction, createDefaultCallableFunction } from '../../typings/callable';
import { FormItem } from '../form-item';
import { CallableSelector } from '../../components/callable/callable-selector';
import { Feedback } from '../feedback';
import { useNodeRenderContext } from '../../hooks';
import { useToolStore } from '../../../../stores/toolStore';
import { useUserStore } from '../../../../stores/userStore';
import { useEffect } from 'react';

export function FormCallable() {
  const { readonly } = useNodeRenderContext();
  const { tools, fetchTools } = useToolStore();
  const username = useUserStore((state) => state.username);

  useEffect(() => {
    if (username) {
      fetchTools(username);
    }
  }, [username, fetchTools]);

  // Map the tools from the store to the format expected by CallableSelector
  const realSystemFunctions: CallableFunction[] = tools.map(tool => ({
    id: tool.id,
    name: tool.name,
    description: tool.description,
    type: 'system', // Assuming all fetched tools are 'system' tools
    source: '', // Or another appropriate default
  }));

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
              systemFunctions={realSystemFunctions} // Use the real data
            />
          </div>
          <Feedback errors={fieldState?.errors} warnings={fieldState?.warnings} />
        </FormItem>
      )}
    </Field>
  );
}