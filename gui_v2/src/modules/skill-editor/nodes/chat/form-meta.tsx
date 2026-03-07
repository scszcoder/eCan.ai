/**
 * Chat Node form
 */
import { useEffect, useMemo, useState } from 'react';
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, TextArea } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';
import { IPCAPI } from '../../../../services/ipc/api';

interface AgentOption { id: string; name: string; kind: 'human' | 'agent' }

export const ChatFormRender = ({}: FormRenderProps<FlowNodeJSON>) => {
  const { t } = useTranslation('skillEditor');
  const [options, setOptions] = useState<AgentOption[]>([{ id: 'human', name: t('nodes.chat.human'), kind: 'human' }]);

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
        <FormItem name="party" type="string" label={t('nodes.chat.chatWith')} vertical>
          <Field<any> name="inputsValues.party">
            {({ field }) => (
              <Select
                value={field.value?.content ?? 'human'}
                onChange={(val) => field.onChange({ type: 'constant', content: String(val) })}
                optionList={partyOptions}
                placeholder={t('nodes.chat.selectParty')}
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="messageTemplate" type="string" label={t('nodes.chat.message')} vertical>
          <Field<any> name="inputsValues.messageTemplate">
            {({ field }) => (
              <TextArea
                value={String(field.value?.content ?? '')}
                onChange={(val) => field.onChange({ type: 'template', content: String(val ?? '') })}
                rows={4}
                placeholder={t('nodes.chat.messagePlaceholder')}
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
    party: ({ value }) => (value ? undefined : i18n.t('nodes.chat.partyRequired', { ns: 'skillEditor' })),
  },
  effect: defaultFormMeta.effect,
};
