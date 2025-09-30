/**
 * Pend Event Node form
 */
import React from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio } from '@douyinfe/semi-ui';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';

const EVENT_TYPES = [
  'human_chat', 'a2a', 'webhook', 'websocket', 'mqtt', 'sse', 'timer', 'other'
];

export const PendEventFormRender = ({ form }: FormRenderProps) => {
  return (
    <>
      <FormHeader />
      <FormContent>
        <FormItem name="eventType" type="string" label="Event Type" vertical>
          <Field<any> name="inputsValues.eventType">
            {({ field }) => (
              <Select
                value={String(field.value?.content ?? 'human_chat')}
                onChange={(val) => field.onChange({ type: 'constant', content: String(val) })}
                optionList={EVENT_TYPES.map((t) => ({ label: t, value: t }))}
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="timeoutSec" type="number" label="Timeout (sec)" vertical>
          <Field<any> name="inputsValues.timeoutSec">
            {({ field }) => (
              <InputNumber
                min={0}
                value={Number(field.value?.content ?? 0)}
                onChange={(v) => field.onChange({ type: 'constant', content: Number(v || 0) })}
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="resumePolicy" type="string" label="Resume Policy" vertical>
          <Field<any> name="inputsValues.resumePolicy">
            {({ field }) => (
              <Radio.Group
                type="button"
                value={field.value?.content ?? 'first'}
                onChange={(e) => field.onChange({ type: 'constant', content: String((e as any).target?.value ?? 'first') })}
              >
                <Radio value="first">First</Radio>
                <Radio value="all">All</Radio>
              </Radio.Group>
            )}
          </Field>
        </FormItem>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <PendEventFormRender {...props} />,
  validate: {},
  effect: defaultFormMeta.effect,
};
