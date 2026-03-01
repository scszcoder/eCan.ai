/**
 * Pend Event Node form
 */
import { Field, FormMeta, FormRenderProps, FlowNodeJSON } from '@flowgram.ai/free-layout-editor';
import { Divider, Select, InputNumber, Radio, Button, Input, Typography } from '@douyinfe/semi-ui';
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
  'human_chat', 'a2a', 'webhook', 'websocket', 'mqtt', 'sse', 'timer', 'system', 'other'
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
            if (["websocket", "sse", "webhook", "system"].includes(et)) {
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
            if (et === 'timer') {
              return (
                <FormItem key={`main-extra-${et}`} name="Timer Name" type="string" vertical>
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
                  : { type: String(item?.type ?? 'human_chat'), messageType: item?.messageType ?? '', agentIds: item?.agentIds ?? '', timerName: item?.timerName ?? '' };
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
              const updateExtraAt = (idx: number, key: 'messageType' | 'agentIds' | 'timerName', val: string) => {
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
                        {['websocket', 'sse', 'webhook', 'system'].includes(et) && (
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
                        {et === 'timer' && (
                          <FormItem key={`list-extra-${i}-timer`} name="Timer Name" type="string" vertical>
                            <Input
                              value={item.timerName ?? ''}
                              placeholder="e.g. check_orders"
                              onChange={(val) => updateExtraAt(i, 'timerName', String(val))}
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
        <Divider />
        <FormItem name="Routing Match Fields" type="array" vertical>
          <Typography.Text type="tertiary" size="small" style={{ display: 'block', marginBottom: 8 }}>
            Match fields for routing events to the correct task. Event Field is a dot-path
            in the normalized event envelope (type, source, tag, data.*, context.*).
            Task Field is a dot-path in the task (state.*, skill.*, id, name).
            Task Field can be blank if auto-filled at runtime (e.g. task id).{' '}
            <Typography.Text
              link={{ onClick: openDocFile }}
              size="small"
              style={{ cursor: 'pointer' }}
            >
              View Specification
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
                        placeholder="Event Field (e.g. data.order_id)"
                        onChange={(val) => updateRow(i, 'event_path', String(val))}
                        style={{ flex: 1 }}
                        size="small"
                      />
                      <Input
                        value={item.task_path}
                        placeholder="Task Field (e.g. state.order_id)"
                        onChange={(val) => updateRow(i, 'task_path', String(val))}
                        style={{ flex: 1 }}
                        size="small"
                      />
                      <Button type="danger" theme="borderless" size="small" onClick={() => removeRow(i)}>
                        Del
                      </Button>
                    </div>
                  ))}
                  <div>
                    <Button size="small" onClick={addRow}>Add Match Field</Button>
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
