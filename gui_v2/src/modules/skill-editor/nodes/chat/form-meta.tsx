/**
 * Chat Node form
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, TextArea } from '@douyinfe/semi-ui';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';
import { IPCAPI } from '../../../../services/ipc/api';

interface AgentOption { id: string; name: string; kind: 'human' | 'agent' }

export const ChatFormRender = ({ form }: FormRenderProps) => {
  const [options, setOptions] = useState<AgentOption[]>([{ id: 'human', name: 'Human', kind: 'human' }]);

  useEffect(() => {
    IPCAPI.getInstance().getEditorAgents<{ agents: AgentOption[] }>()
      .then((resp) => {
        if (resp.success && resp.data?.agents) {
          setOptions(resp.data.agents);
        }
      })
      .catch(() => {});
  }, []);

  const partyOptions = useMemo(
    () => options.map((o) => ({ label: o.name, value: o.id })),
    [options]
  );

  return (
    <>
      <FormHeader />
      <FormContent>
        <FormItem name="party" type="string" label="Chat With" vertical>
          <Field<any> name="inputsValues.party">
            {({ field }) => (
              <Select
                value={field.value?.content ?? 'human'}
                onChange={(val) => field.onChange({ type: 'constant', content: String(val) })}
                optionList={partyOptions}
                placeholder="Select party (default: Human)"
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="messageTemplate" type="string" label="Message" vertical>
          <Field<any> name="inputsValues.messageTemplate">
            {({ field }) => (
              <TextArea
                value={String(field.value?.content ?? '')}
                onChange={(val) => field.onChange({ type: 'template', content: String(val ?? '') })}
                rows={4}
                placeholder="Enter chat message template"
              />
            )}
          </Field>
        </FormItem>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <ChatFormRender {...props} />,
  validate: {
    party: ({ value }) => (value ? undefined : 'Party is required'),
  },
  effect: defaultFormMeta.effect,
};
