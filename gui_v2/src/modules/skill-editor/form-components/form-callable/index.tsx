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
    desc: tool.description,
    params: tool.inputSchema ?? { type: 'object', properties: {} },
    returns: tool.outputSchema ?? { type: 'object', properties: {} },
    type: 'system',
    source: '',
  }));

  return (
    <Field<CallableFunction> name="data.callable">
      {({ field, fieldState }: FieldRenderProps<CallableFunction>) => (
        <FormItem
          name="tool" type="object" required={false} vertical>
          <div style={{ width: '100%', maxWidth: '100%' }}>
            <CallableSelector
              readonly={readonly}
              value={field.value}
              onChange={(func) => {
                try { console.log('[Callable] onChange selected:', func); } catch {}
                field.onChange(func);
                try { console.log('[Callable] data.callable updated with:', func); } catch {}
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