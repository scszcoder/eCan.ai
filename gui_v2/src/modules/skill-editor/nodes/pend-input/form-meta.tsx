/**
 * Pend Input Node form
 */
import { useEffect, useMemo, useState } from 'react';
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';
import { IPCAPI } from '../../../../services/ipc/api';

interface SourceOption { id: string; name: string }

export const PendFormRender = ({}: FormRenderProps<FlowNodeJSON>) => {
  const { t } = useTranslation('skillEditor');
  const [queues, setQueues] = useState<SourceOption[]>([]);
  const [events, setEvents] = useState<SourceOption[]>([]);

  useEffect(() => {
    IPCAPI.getInstance().getEditorPendingSources<{ queues: SourceOption[]; events: SourceOption[] }>()
      .then((resp) => {
        if (resp.success && resp.data) {
          setQueues(resp.data.queues || []);
          setEvents(resp.data.events || []);
        }
      })
      .catch(() => {});
  }, []);

  const pendingOptions = useMemo(() => {
    const q = queues.map((q) => ({ label: `${t('nodes.pendInput.queue')}: ${q.name}`, value: `queue:${q.id}` }));
    const e = events.map((ev) => ({ label: `${t('nodes.pendInput.event')}: ${ev.name}`, value: `event:${ev.id}` }));
    return [...q, ...e];
  }, [queues, events, t]);

  return (
    <>
      <FormHeader />
      <FormContent>
        <FormItem name="pendingSources" label={t('nodes.pendInput.pendingSources')} type="array" vertical>
          <Field<any> name="inputsValues.pendingSources">
            {({ field }) => (
              <Select
                value={(field.value?.content as string[]) ?? []}
                onChange={(val) => field.onChange({ type: 'constant', content: (val as string[]) ?? [] })}
                optionList={pendingOptions}
                placeholder={t('nodes.pendInput.selectSources')}
                multiple
                filter
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="timeoutSec" label={t('nodes.pendInput.timeoutSec')} type="number" vertical>
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
        <FormItem name="resumePolicy" label={t('nodes.pendInput.resumePolicy')} type="string" vertical>
          <Field<any> name="inputsValues.resumePolicy">
            {({ field }) => (
              <Radio.Group
                type="button"
                value={field.value?.content ?? 'first'}
                onChange={(e) => field.onChange({ type: 'constant', content: String((e as any).target?.value ?? 'first') })}
              >
                <Radio value="first">{t('nodes.pendInput.first')}</Radio>
                <Radio value="all">{t('nodes.pendInput.all')}</Radio>
              </Radio.Group>
            )}
          </Field>
        </FormItem>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  render: (props) => <PendFormRender {...props} />,
  validate: {
    pendingSources: ({ value }) => (Array.isArray(value) && value.length > 0 ? undefined : 'Select at least one source'),  // Keep English for validation
  },
  effect: defaultFormMeta.effect,
};
