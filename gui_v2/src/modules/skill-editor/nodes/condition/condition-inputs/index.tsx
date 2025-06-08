import { nanoid } from 'nanoid';
import { Field, FieldArray } from '@flowgram.ai/free-layout-editor';
import { ConditionRow, ConditionRowValueType, VariableSelector } from '@flowgram.ai/form-materials';
import { Button } from '@douyinfe/semi-ui';
import { IconPlus, IconCrossCircleStroked } from '@douyinfe/semi-icons';

import { useNodeRenderContext } from '../../../hooks';
import { FormItem } from '../../../form-components';
import { Feedback } from '../../../form-components';
import { ConditionPort } from './styles';

interface ConditionValue {
  key: string;
  value?: ConditionRowValueType;
}

export function ConditionInputs() {
  const { readonly } = useNodeRenderContext();
  return (
    <FieldArray name="conditions">
      {({ field }) => (
        <>
          {field.map((child, index) => (
            <Field<ConditionValue> key={child.name} name={child.name}>
              {({ field: childField, fieldState: childState }) => {
                const isIfCondition = childField.value?.key?.startsWith('if_');
                const formItemName = isIfCondition ? 'if' : 'else';
                
                return (
                  <FormItem name={formItemName} type="boolean" required={true} labelWidth={40}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        <ConditionRow
                          readonly={readonly || !isIfCondition}
                          style={{ flexGrow: 1 }}
                          value={childField.value?.value}
                          onChange={(v) => childField.onChange({ value: v, key: childField.value.key })}
                        />
                        <Button
                          theme="borderless"
                          icon={<IconCrossCircleStroked />}
                          onClick={() => {
                            if (field.value) {
                              const newValue = field.value.filter((_, i) => i !== index);
                              field.onChange(newValue);
                            }
                          }}
                          disabled={!isIfCondition}
                        />
                    </div>

                    <Feedback errors={childState?.errors} invalid={childState?.invalid} />
                    <ConditionPort data-port-id={childField.value?.key} data-port-type="output" />
                  </FormItem>
                );
              }}
            </Field>
          ))}
          {!readonly && (
            <div>
              <Button
                theme="borderless"
                icon={<IconPlus />}
                onClick={() =>
                  field.append({
                    key: `if_${nanoid(6)}`,
                    value: { type: 'expression', content: '' },
                  })
                }
              >
                Add
              </Button>
            </div>
          )}
        </>
      )}
    </FieldArray>
  );
}
