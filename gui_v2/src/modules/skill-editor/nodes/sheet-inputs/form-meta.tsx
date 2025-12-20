import React from 'react';
import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Button, Input, Typography } from '@douyinfe/semi-ui';
import { FlowNodeJSON } from '../../typings';

const InputsEditor: React.FC<FormRenderProps<FlowNodeJSON>> = ({ form }) => {
  const items: Array<{ name: string }> = form.values?.data?.interface?.inputs || [];
  const setItems = (next: Array<{ name: string }>) => form.setFieldValue('data.interface.inputs', next);
  const onAdd = () => setItems([...(items || []), { name: '' }]);
  const onRemove = (idx: number) => setItems(items.filter((_, i) => i !== idx));
  const onChange = (idx: number, name: string) => {
    const next = [...items];
    next[idx] = { name };
    setItems(next);
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Typography.Text strong>Sheet Inputs</Typography.Text>
      {(items || []).map((it, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            value={it.name}
            placeholder={`input_${i + 1}`}
            onChange={(v) => onChange(i, v)}
            style={{ flex: 1 }}
          />
          <Button type="danger" theme="borderless" onClick={() => onRemove(i)}>Remove</Button>
        </div>
      ))}
      <Button onClick={onAdd}>Add Input</Button>
    </div>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: (props) => <InputsEditor {...props} />,
};
