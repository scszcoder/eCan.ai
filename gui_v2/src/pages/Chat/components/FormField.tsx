import React from 'react';
import { Form, Typography, Button, Card } from '@douyinfe/semi-ui';
import { FormField as FormFieldType } from '../types/chat';
import useChatForm from '../hooks/useChatForm';
import styles from './FormField.module.css';
import { useTranslation } from 'react-i18next';


interface FormFieldProps {
  field: FormFieldType;
  value: any;
  error?: string;
  onChange: (fieldId: string, value: any) => void;
  style?: React.CSSProperties;
}

const FormField: React.FC<FormFieldProps> = ({ field, value, error, onChange, style }) => {
  const { t } = useTranslation();
  if (!field || !field.id) return null;
  const { id, type, label, placeholder, required, options = [] } = field;

  // 国际化 label/placeholder
  const i18nLabel = t(label) || label;
  const i18nPlaceholder = placeholder ? t(placeholder) : (type === 'select' ? t('pages.chat.selectPlaceholder', { label: i18nLabel }) : t('pages.chat.inputPlaceholder', { label: i18nLabel }));

  switch (type) {
    case 'text':
      return (
        <Form.Input
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          placeholder={i18nPlaceholder}
          value={value || ''}
          onChange={val => onChange(id, val)}
        />
      );
    case 'textarea':
      return (
        <Form.TextArea
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          placeholder={i18nPlaceholder}
          value={value || ''}
          onChange={val => onChange(id, val)}
        />
      );
    case 'number':
      return (
        <Form.Input
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          type="number"
          placeholder={i18nPlaceholder}
          value={value || ''}
          onChange={val => onChange(id, val)}
        />
      );
    case 'select':
      return (
        <Form.Select
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          placeholder={i18nPlaceholder}
          value={value}
          onChange={val => onChange(id, val)}
          optionList={Array.isArray(options)
            ? options.filter(opt => opt && typeof opt === 'object' && 'label' in opt && 'value' in opt)
                .map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
            : []}
        />
      );
    case 'checkbox':
      return (
        <Form.CheckboxGroup
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          value={Array.isArray(value) ? value : (value ? [value] : [])}
          onChange={val => onChange(id, val)}
          options={Array.isArray(options)
            ? options.filter(opt => opt && typeof opt === 'object' && 'label' in opt && 'value' in opt)
                .map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
            : []}
        />
      );
    case 'radio':
      return (
        <Form.RadioGroup
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          value={value}
          onChange={val => onChange(id, val)}
          options={Array.isArray(options)
            ? options.filter(opt => opt && typeof opt === 'object' && 'label' in opt && 'value' in opt)
                .map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
            : []}
        />
      );
    case 'date':
      return (
        <Form.DatePicker
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          placeholder={i18nPlaceholder}
          value={value}
          onChange={val => onChange(id, val)}
        />
      );
    default:
      return (
        <Form.Input
          field={id}
          label={i18nLabel}
          required={required}
          validateStatus={error ? 'error' : undefined}
          style={style}
          placeholder={i18nPlaceholder}
          value={value || ''}
          onChange={val => onChange(id, val)}
        />
      );
  }
};

interface DynamicFormProps {
  form: {
    id: string;
    title: string;
    fields: FormFieldType[];
    submit_text?: string;
  };
  onFormSubmit?: (formId: string, values: any) => void;
}

export const DynamicForm: React.FC<DynamicFormProps> = ({ form, onFormSubmit }) => {
  const { t } = useTranslation();
  const { formState, errors, handleChange, validateForm } = useChatForm(form.fields);

  const handleSubmit = () => {
    const { isValid } = validateForm();
    if (isValid) {
      onFormSubmit?.(form.id, formState);
    }
  };

  return (
    <Card className={styles.cardFormSemi}>
      <Form>
        {form.fields.map(field => (
          <FormField
            key={field.id}
            field={field}
            value={formState[field.id]}
            error={errors[field.id]}
            onChange={handleChange}
          />
        ))}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          marginTop: 28,
          marginBottom: 8
        }}>
          <Button
            type="primary"
            size="large"
            style={{
              minWidth: 160,
              fontWeight: 600,
              borderRadius: 8,
              boxShadow: '0 2px 12px rgba(25, 118, 210, 0.12)',
              color: '#fff',
              textShadow: '0 1px 2px rgba(0,0,0,0.15)'
            }}
            onClick={handleSubmit}
          >
            {t(form.submit_text) || t('pages.chat.submit')}
          </Button>
        </div>
        {Object.values(errors).length > 0 && (
          <div style={{ marginTop: 12 }}>
            <span style={{ color: '#d32f2f', fontSize: 14, fontWeight: 500 }}>{t('pages.chat.formErrorTip')}</span>
          </div>
        )}
      </Form>
    </Card>
  );
};

export default FormField; 