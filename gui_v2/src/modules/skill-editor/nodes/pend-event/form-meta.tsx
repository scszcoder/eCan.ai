/**
 * Pend Event Node form
 */
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio, Button } from '@douyinfe/semi-ui';
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
        <Divider />
        <FormItem name="Pending Events" type="array" vertical>
          <Field<any> name="inputsValues.pendingEvents">
            {({ field }) => {
              const arr: string[] = Array.isArray(field.value?.content) ? (field.value.content as string[]) : [];
              const setArray = (next: string[]) => field.onChange({ type: 'constant', content: next });
              const addOne = () => setArray([...(arr || []), 'human_chat']);
              const removeAt = (idx: number) => {
                const next = [...arr];
                next.splice(idx, 1);
                setArray(next);
              };
              const updateAt = (idx: number, val: string) => {
                const next = [...arr];
                next[idx] = val;
                setArray(next);
              };
              return (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(arr && arr.length > 0 ? arr : []).map((v, i) => (
                    <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <Select
                        value={v}
                        onChange={(val) => updateAt(i, String(val))}
                        optionList={EVENT_TYPES.map((t) => ({ label: t, value: t }))}
                        style={{ flex: 1 }}
                      />
                      <Button type="danger" theme="borderless" onClick={() => removeAt(i)}>
                        Delete
                      </Button>
                    </div>
                  ))}
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
