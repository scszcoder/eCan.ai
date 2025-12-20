/**
 * Pend Event Node form
 */
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio, Button, Input } from '@douyinfe/semi-ui';
import { FormHeader, FormContent, FormItem } from '../../form-components';
import { defaultFormMeta } from '../default-form-meta';

const EVENT_TYPES = [
  'human_chat', 'a2a', 'webhook', 'websocket', 'mqtt', 'sse', 'timer', 'other'
];

export const PendEventFormRender = ({}: FormRenderProps<FlowNodeJSON>) => {
  return (
    <>
      <FormHeader />
      <FormContent>
        <FormItem name="Event Type" type="string" vertical>
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
            if (["websocket", "sse", "webhook"].includes(et)) {
              return (
                <FormItem key={`main-extra-${et}`} name="Message Type" type="string" vertical>
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
                <FormItem key={`main-extra-${et}`} name="Agent Ids" type="string" vertical>
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
            return null;
          }}
        </Field>
        <Divider />
        <FormItem name="Pending Sources" type="array" vertical>
          <Field<any> name="inputsValues.pendingSources">
            {({ field }) => {
              const raw = Array.isArray(field.value?.content) ? (field.value.content as any[]) : [];
              const toObj = (item: any) =>
                typeof item === 'string'
                  ? { type: item }
                  : { type: String(item?.type ?? 'human_chat'), messageType: item?.messageType ?? '', agentIds: item?.agentIds ?? '' };
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
              const updateExtraAt = (idx: number, key: 'messageType' | 'agentIds', val: string) => {
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
                            Delete
                          </Button>
                        </div>
                        {['websocket', 'sse', 'webhook'].includes(et) && (
                          <FormItem key={`list-extra-${i}-${et}`} name="Message Type" type="string" vertical>
                            <Input
                              value={item.messageType ?? ''}
                              onChange={(val) => updateExtraAt(i, 'messageType', String(val))}
                            />
                          </FormItem>
                        )}
                        {et === 'a2a' && (
                          <FormItem key={`list-extra-${i}-${et}`} name="Agent Ids" type="string" vertical>
                            <Input
                              value={item.agentIds ?? ''}
                              onChange={(val) => updateExtraAt(i, 'agentIds', String(val))}
                            />
                          </FormItem>
                        )}
                      </div>
                    );
                  })}
                  <div>
                    <Button onClick={addOne}>Add</Button>
                  </div>
                </div>
              );
            }}
          </Field>
        </FormItem>
        <Divider />
        <FormItem name="Timeout (sec)" type="number" vertical>
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
        <FormItem name="Resume Policy" type="string" vertical>
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
