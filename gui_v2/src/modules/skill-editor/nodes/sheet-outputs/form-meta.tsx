import React from 'react';
import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Button, Input, Typography, Select } from '@douyinfe/semi-ui';
import { Field } from '@flowgram.ai/free-layout-editor';
import { FlowNodeJSON } from '../../typings';
import { useSheetsStore } from '../../stores/sheets-store';
import { FormHeader, FormContent } from '../../form-components';

const OutputsEditor: React.FC<FormRenderProps<FlowNodeJSON>> = ({ form }) => {
  const items: Array<{ name: string }> = form.values?.data?.interface?.outputs || [];
  const setItems = (next: Array<{ name: string }>) => form.setFieldValue('data.interface.outputs', next);
  const onAdd = () => setItems([...(items || []), { name: '' }]);
  const onRemove = (idx: number) => setItems(items.filter((_, i) => i !== idx));
  const onChange = (idx: number, name: string) => {
    const next = [...items];
    next[idx] = { name };
    setItems(next);
  };
  const sheets = useSheetsStore((s) => s.sheets);
  const openSheet = useSheetsStore((s) => s.openSheet);
  // options built from current bundle's sheets
  const options = Object.values(sheets).map((s) => ({ label: `${s.name} (${s.id})`, value: s.id }));

  return (
    <>
      <FormHeader />
      <FormContent>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Typography.Text strong>Sheet Outputs</Typography.Text>
          {(items || []).map((it, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <Input
                value={it.name}
                placeholder={`output_${i + 1}`}
                onChange={(v) => onChange(i, v)}
                style={{ flex: 1 }}
              />
              <Button type="danger" theme="borderless" onClick={() => onRemove(i)}>Remove</Button>
            </div>
          ))}
          <Button onClick={onAdd}>Add Output</Button>
          <div style={{ height: 1, background: '#eee' }} />
          <Typography.Text strong>Next Sheet (optional)</Typography.Text>
          <Field<string> name="data.nextSheet">
            {({ field }) => {
              const nextId = String(field.value || '');
              const nextExists = !!(nextId && sheets[nextId]);
              return (
                <>
                  <Select
                    placeholder="Pick next sheet"
                    value={nextId}
                    optionList={options}
                    onChange={(v) => field.onChange(String(v))}
                    filter
                    style={{ minWidth: 240 }}
                  />
                  {!nextExists && nextId && (
                    <Typography.Text type="warning">Selected sheet id not found in this bundle.</Typography.Text>
                  )}
                  {nextExists && (
                    <Button onClick={() => openSheet(nextId)}>Open next sheet</Button>
                  )}
                </>
              );
            }}
          </Field>
        </div>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: (props) => <OutputsEditor {...props} />,
};
