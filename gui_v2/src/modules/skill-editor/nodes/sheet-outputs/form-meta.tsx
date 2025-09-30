import React from 'react';
import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Button, Input, Typography, Select } from '@douyinfe/semi-ui';
import { FlowNodeJSON } from '../../typings';
import { useSheetsStore } from '../../stores/sheets-store';

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
  const sheetOptions = Object.values(sheets).map((s) => ({ label: `${s.name} (${s.id})`, value: s.id }));
  const nextId = String((form as any)?.values?.data?.nextSheet || '');
  const nextExists = !!(nextId && sheets[nextId]);

  return (
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
      <Select
        placeholder="Select next sheet"
        value={nextId}
        optionList={sheetOptions}
        onChange={(v) => {
          try { (form as any).setFieldValue?.('data.nextSheet', v as string); } catch {}
        }}
        style={{ minWidth: 220 }}
      />
      {!nextExists && nextId && (
        <Typography.Text type="warning">Selected sheet id not found in this bundle.</Typography.Text>
      )}
      {nextExists && (
        <Button onClick={() => openSheet(nextId)}>Open next sheet</Button>
      )}
    </div>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: (props) => <OutputsEditor {...props} />,
};
