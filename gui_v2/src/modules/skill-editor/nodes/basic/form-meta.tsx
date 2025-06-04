import { FormRenderProps, FormMeta, ValidateTrigger, Field } from '@flowgram.ai/free-layout-editor';
import { Button } from '@douyinfe/semi-ui';
import { IconPlus, IconCrossCircleStroked } from '@douyinfe/semi-icons';
import { nanoid } from 'nanoid';

import { FlowNodeJSON } from '../../typings';
import { FormHeader, FormContent, FormInputs, FormOutputs, FormItem, Feedback } from '../../form-components';
import { FormCallable } from '../../form-components/form-callable';
import { useNodeRenderContext } from '../../hooks';

interface InputValue {
  type: string;
  description: string;
}

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => {
  const { readonly } = useNodeRenderContext();

  return (
    <>
      <FormHeader />
      <FormContent>
        <Field name="inputs.properties">
          {({ field }) => {
            const properties = (field.value && typeof field.value === 'object') ? (field.value as Record<string, InputValue>) : {};
            const entries = Object.entries(properties);

            return (
              <>
                {entries.map(([key, value], index) => (
                  <FormItem key={key} name={key} type="string" required={true}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <div style={{ flexGrow: 1 }}>
                        <div style={{ marginBottom: 8 }}>
                          <strong>{key}</strong>
                        </div>
                        <div>
                          {value.description}
                        </div>
                      </div>
                      {!readonly && (
                        <Button
                          theme="borderless"
                          icon={<IconCrossCircleStroked />}
                          onClick={() => {
                            const newProperties = { ...properties };
                            delete newProperties[key];
                            field.onChange(newProperties);
                          }}
                        />
                      )}
                    </div>
                  </FormItem>
                ))}
                {!readonly && (
                  <div>
                    <Button
                      theme="borderless"
                      icon={<IconPlus />}
                      onClick={() => {
                        const inputCount = Object.keys(properties).length;
                        const newInputKey = `input${inputCount + 1}`;
                        field.onChange({
                          ...properties,
                          [newInputKey]: {
                            type: 'string',
                            description: `Input value ${inputCount + 1}`,
                          },
                        });
                      }}
                    >
                      Add
                    </Button>
                  </div>
                )}
              </>
            );
          }}
        </Field>
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