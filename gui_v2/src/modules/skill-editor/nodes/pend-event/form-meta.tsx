/**
 * Pend Event Node form
 */
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio, Button, Input, Typography } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';
import { IPCAPI } from '../../../../services/ipc/api';

const DOC_PATH = 'gui_v2/src/modules/skill-editor/doc/mapping-dsl.md';
const openDocFile = () => {
  IPCAPI.getInstance().executeRequest('open_file', { path: DOC_PATH }).catch(() => {
    // Fallback: log the path so user can find it
    console.log('[PendEvent] Doc path:', DOC_PATH);
  });
};

const EVENT_TYPES = [
  'human_chat', 'a2a', 'webhook', 'websocket', 'mqtt', 'sse', 'timer', 'browser_event', 'system', 'other'
];

export const PendEventFormRender = ({}: FormRenderProps<FlowNodeJSON>) => {
  const { t } = useTranslation('skillEditor');
  return (
    <>
      <FormHeader />
      <FormContent>
        <FormItem name="eventType" label={t('nodes.pendEvent.eventType')} type="string" vertical>
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
        <Field<any> name="inputsValues.eventType">
          {({ field }) => {
            const et = String(field.value?.content ?? 'human_chat');
            if (["websocket", "sse", "webhook", "system"].includes(et)) {
              return (
                <FormItem key={`main-extra-${et}`} name="messageType" label={t('nodes.pendEvent.messageType')} type="string" vertical>
                  <Field<any> name="inputsValues.messageType">
                    {({ field: mtField }) => (
                      <Input
                        value={String(mtField.value?.content ?? '')}
                        onChange={(val) => mtField.onChange({ type: 'constant', content: String(val) })}
                      />
                    )}
                  </Field>
                </FormItem>
              );
            }
            if (et === 'a2a') {
              return (
                <FormItem key={`main-extra-${et}`} name="agentIds" label={t('nodes.pendEvent.agentIds')} type="string" vertical>
                  <Field<any> name="inputsValues.agentIds">
                    {({ field: aiField }) => (
                      <Input
                        value={String(aiField.value?.content ?? '')}
                        onChange={(val) => aiField.onChange({ type: 'constant', content: String(val) })}
                      />
                    )}
                  </Field>
                </FormItem>
              );
            }
            if (et === 'timer') {
              return (
                <FormItem key={`main-extra-${et}`} name="timerName" label={t('nodes.pendEvent.timerName')} type="string" vertical>
                  <Field<any> name="inputsValues.timerName">
                    {({ field: tnField }) => (
                      <Input
                        value={String(tnField.value?.content ?? '')}
                        placeholder="e.g. check_orders"
                        onChange={(val) => tnField.onChange({ type: 'constant', content: String(val) })}
                      />
                    )}
                  </Field>
                </FormItem>
              );
            }
            if (et === 'browser_event') {
              return (
                <FormItem key={`main-extra-${et}`} name="eventLabel" label={t('nodes.pendEvent.eventLabel')} type="string" vertical>
                  <Field<any> name="inputsValues.browserEventLabel">
                    {({ field: beField }) => (
                      <Input
                        value={String(beField.value?.content ?? '')}
                        placeholder="e.g. price_api, page_loaded"
                        onChange={(val) => beField.onChange({ type: 'constant', content: String(val) })}
                      />
                    )}
                  </Field>
                </FormItem>
              );
            }
            return <></>;
          }}
        </Field>
        <Divider />
        <FormItem name="pendingSources" label={t('nodes.pendEvent.pendingSources')} type="array" vertical>
          <Field<any> name="inputsValues.pendingSources">
            {({ field }) => {
              const raw = Array.isArray(field.value?.content) ? (field.value.content as any[]) : [];
              const toObj = (item: any) =>
                typeof item === 'string'
                  ? { type: item }
                  : { type: String(item?.type ?? 'human_chat'), messageType: item?.messageType ?? '', agentIds: item?.agentIds ?? '', timerName: item?.timerName ?? '', browserEventLabel: item?.browserEventLabel ?? '' };
              const arr = (raw || []).map(toObj);
              const setArray = (next: any[]) => field.onChange({ type: 'constant', content: next });
              const addOne = () => setArray([...(arr || []), { type: 'human_chat' }]);
              const removeAt = (idx: number) => {
                const next = [...arr];
                next.splice(idx, 1);
                setArray(next);
              };
              const updateTypeAt = (idx: number, val: string) => {
                const next = [...arr];
                next[idx] = { ...next[idx], type: val };
                setArray(next);
              };
              const updateExtraAt = (idx: number, key: 'messageType' | 'agentIds' | 'timerName' | 'browserEventLabel', val: string) => {
                const next = [...arr];
                next[idx] = { ...next[idx], [key]: val };
                setArray(next);
              };
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(arr && arr.length > 0 ? arr : []).map((item, i) => {
                    const et = item.type;
                    return (
                      <div key={i} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <Select
                            value={et}
                            onChange={(val) => updateTypeAt(i, String(val))}
                            optionList={EVENT_TYPES.map((t) => ({ label: t, value: t }))}
                            style={{ flex: 1 }}
                          />
                          <Button type="danger" theme="borderless" onClick={() => removeAt(i)}>
                            {t('nodes.pendEvent.delete')}
                          </Button>
                        </div>
                        {['websocket', 'sse', 'webhook', 'system'].includes(et) && (
                          <FormItem key={`list-extra-${i}-${et}`} name="messageType" label={t('nodes.pendEvent.messageType')} type="string" vertical>
                            <Input
                              value={item.messageType ?? ''}
                              onChange={(val) => updateExtraAt(i, 'messageType', String(val))}
                            />
                          </FormItem>
                        )}
                        {et === 'a2a' && (
                          <FormItem key={`list-extra-${i}-${et}`} name="agentIds" label={t('nodes.pendEvent.agentIds')} type="string" vertical>
                            <Input
                              value={item.agentIds ?? ''}
                              onChange={(val) => updateExtraAt(i, 'agentIds', String(val))}
                            />
                          </FormItem>
                        )}
                        {et === 'timer' && (
                          <FormItem key={`list-extra-${i}-timer`} name="timerName" label={t('nodes.pendEvent.timerName')} type="string" vertical>
                            <Input
                              value={item.timerName ?? ''}
                              placeholder="e.g. check_orders"
                              onChange={(val) => updateExtraAt(i, 'timerName', String(val))}
                            />
                          </FormItem>
                        )}
                        {et === 'browser_event' && (
                          <FormItem key={`list-extra-${i}-browser`} name="eventLabel" label={t('nodes.pendEvent.eventLabel')} type="string" vertical>
                            <Input
                              value={item.browserEventLabel ?? ''}
                              placeholder="e.g. price_api, page_loaded"
                              onChange={(val) => updateExtraAt(i, 'browserEventLabel', String(val))}
                            />
                          </FormItem>
                        )}
                      </div>
                    );
                  })}
                  <div>
                    <Button onClick={addOne}>{t('nodes.pendEvent.add')}</Button>
                  </div>
                </div>
              );
            }}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="timeoutSec" label={t('nodes.pendEvent.timeoutSec')} type="number" vertical>
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
        <FormItem name="resumePolicy" label={t('nodes.pendEvent.resumePolicy')} type="string" vertical>
          <Field<any> name="inputsValues.resumePolicy">
            {({ field }) => (
              <Radio.Group
                type="button"
                value={field.value?.content ?? 'first'}
                onChange={(e) => field.onChange({ type: 'constant', content: String((e as any).target?.value ?? 'first') })}
              >
                <Radio value="first">{t('nodes.pendEvent.first')}</Radio>
                <Radio value="all">{t('nodes.pendEvent.all')}</Radio>
              </Radio.Group>
            )}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="matchFields" label={t('nodes.pendEvent.routingMatchFields')} type="array" vertical>
          <Typography.Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
            {t('nodes.pendEvent.routingMatchFieldsDesc')}{' '}
            <Typography.Text
              link={{ onClick: openDocFile }}
              size="small"
              style={{ cursor: 'pointer' }}
            >
              {t('nodes.pendEvent.viewSpecification')}
            </Typography.Text>
          </Typography.Text>
          <Field<any> name="inputsValues.matchFields">
            {({ field }) => {
              const raw = Array.isArray(field.value?.content) ? (field.value.content as any[]) : [];
              const arr = raw.map((item: any) => ({
                event_path: String(item?.event_path ?? ''),
                task_path: String(item?.task_path ?? ''),
              }));
              const setArr = (next: any[]) => field.onChange({ type: 'constant', content: next });
              const addRow = () => setArr([...arr, { event_path: '', task_path: '' }]);
              const removeRow = (idx: number) => {
                const next = [...arr];
                next.splice(idx, 1);
                setArr(next);
              };
              const updateRow = (idx: number, key: 'event_path' | 'task_path', val: string) => {
                const next = [...arr];
                next[idx] = { ...next[idx], [key]: val };
                setArr(next);
              };
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {arr.map((item, i) => (
                    <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      <Input
                        value={item.event_path}
                        placeholder={t('nodes.pendEvent.eventFieldPlaceholder')}
                        onChange={(val) => updateRow(i, 'event_path', String(val))}
                        style={{ flex: 1 }}
                        size="small"
                      />
                      <Input
                        value={item.task_path}
                        placeholder={t('nodes.pendEvent.taskFieldPlaceholder')}
                        onChange={(val) => updateRow(i, 'task_path', String(val))}
                        style={{ flex: 1 }}
                        size="small"
                      />
                      <Button type="danger" theme="borderless" size="small" onClick={() => removeRow(i)}>
                        {t('nodes.pendEvent.delete')}
                      </Button>
                    </div>
                  ))}
                  <div>
                    <Button size="small" onClick={addRow}>{t('nodes.pendEvent.addMatchField')}</Button>
                  </div>
                </div>
              );
            }}
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
