/**
 * Browser Automation node custom form
 */
import React from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select } from '@douyinfe/semi-ui';
import { defaultFormMeta } from '../default-form-meta';
import { FormContent, FormHeader, FormItem, FormInputs } from '../../form-components';
import { DisplayOutputs } from '@flowgram.ai/form-materials';
import { getModelMap } from '../../stores/model-store';

const TOOL_OPTIONS = [
  { label: 'browser-use', value: 'browser-use' },
  { label: 'crawl4ai', value: 'crawl4ai' },
  { label: 'browsebase', value: 'browsebase' },
];

export const FormRender = ({ form }: FormRenderProps<any>) => {
  const modelMap = getModelMap();
  const providers = Object.keys(modelMap);

  return (
    <>
      <FormHeader />
      <FormContent>
        <Divider />
        {/* Tool selector */}
        <FormItem name="tool" type="string" vertical>
          <Field<string> name="inputsValues.tool.content">
            {({ field }) => (
              <Select
                value={(field.value as string) || TOOL_OPTIONS[0].value}
                onChange={(val) => field.onChange(val as string)}
                optionList={TOOL_OPTIONS}
                style={{ width: '100%' }}
                dropdownMatchSelectWidth
                size="small"
              />
            )}
          </Field>
        </FormItem>

        {/* Model Provider selector */}
        <FormItem name="modelProvider" type="string" vertical>
          <Field<string> name="inputsValues.modelProvider.content">
            {({ field: providerField }) => {
              const currentProvider = (providerField.value as string) || providers[0] || 'OpenAI';
              const providerOptions = providers.map(p => ({ label: p, value: p }));
              return (
                <Select
                  value={currentProvider}
                  onChange={(val) => providerField.onChange(val as string)}
                  optionList={providerOptions}
                  style={{ width: '100%' }}
                  dropdownMatchSelectWidth
                  size="small"
                />
              );
            }}
          </Field>
        </FormItem>

        {/* Model Name selector depends on provider */}
        <FormItem name="modelName" type="string" vertical>
          <Field<string> name="inputsValues.modelName.content">
            {({ field: modelField }) => (
              <Field<string> name="inputsValues.modelProvider.content">
                {({ field: providerField }) => {
                  const provider = (providerField.value as string) || providers[0] || 'OpenAI';
                  const models = modelMap[provider] || [];
                  const modelOptions = models.map(m => ({ label: m, value: m }));
                  const value = modelField.value || models[0] || '';
                  if (value && models.length && !models.includes(value)) {
                    setTimeout(() => modelField.onChange(models[0]), 0);
                  }
                  return (
                    <Select
                      value={value}
                      onChange={(val) => modelField.onChange(val as string)}
                      optionList={modelOptions}
                      style={{ width: '100%' }}
                      dropdownMatchSelectWidth
                      size="small"
                    />
                  );
                }}
              </Field>
            )}
          </Field>
        </FormItem>

        {/* Render the rest of inputs using the default component (temperature, prompts) */}
        <FormInputs />
        <Divider />
        <DisplayOutputs displayFromScope />
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  effect: defaultFormMeta.effect,
  validate: defaultFormMeta.validate,
};
