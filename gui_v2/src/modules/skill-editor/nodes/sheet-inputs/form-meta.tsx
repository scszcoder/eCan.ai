import React from 'react';
import { FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { Button, Input, Typography } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';
import { FlowNodeJSON } from '../../typings';

const InputsEditor: React.FC<FormRenderProps<FlowNodeJSON>> = ({ form }) => {
  const { t } = useTranslation('skillEditor');
  const items: Array<{ name: string }> = form.values?.data?.interface?.inputs || [];
  const setItems = (next: Array<{ name: string }>) => {
    const anyForm = form as any;
    if (typeof anyForm?.setFieldValue === 'function') {
      anyForm.setFieldValue('data.interface.inputs', next);
    } else if (typeof anyForm?.setValue === 'function') {
      anyForm.setValue('data.interface.inputs', next);
    }
  };
  const onAdd = () => setItems([...(items || []), { name: '' }]);
  const onRemove = (idx: number) => setItems(items.filter((_, i) => i !== idx));
  const onChange = (idx: number, name: string) => {
    const next = [...items];
    next[idx] = { name };
    setItems(next);
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Typography.Text strong>{t('nodes.sheetInputs.title')}</Typography.Text>
      {(items || []).map((it, i) => (
        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            value={it.name}
            placeholder={t('nodes.sheetInputs.inputPlaceholder', { index: i + 1 })}
            onChange={(v) => onChange(i, v)}
            style={{ flex: 1 }}
          />
          <Button type="danger" theme="borderless" onClick={() => onRemove(i)}>{t('nodes.sheetInputs.remove')}</Button>
        </div>
      ))}
      <Button onClick={onAdd}>{t('nodes.sheetInputs.addInput')}</Button>
    </div>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: (props) => <InputsEditor {...props} />,
};
