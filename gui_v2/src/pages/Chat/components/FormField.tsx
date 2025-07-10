import React from 'react';
import { Form, Button, Card } from '@douyinfe/semi-ui';
import styles from './FormField.module.css';
import { useTranslation } from 'react-i18next';
import { getValidators, validateField } from '../hooks/useChatForm';
import { FormField as IFormField } from '../types/chat';
import { logger } from '@/utils/logger';

interface DynamicFormProps {
  form: {
    id: string;
    title?: string;
    fields: IFormField[];
    submit_text?: string;
  };
  chatId?: string;
  messageId?: string;
  onFormSubmit?: (
    formId: string,
    values: Record<string, any>,
    chatId?: string,
    messageId?: string,
    processedForm?: any
  ) => void;
}

/**
 * 动态表单组件，根据传入的 form 配置渲染不同类型的表单项。
 * 支持 text、textarea、number、select、checkbox、radio、date、password、switch 等类型。
 * @param {object} props
 * @param {object} props.form - 表单配置对象，包含 fields 数组
 * @param {string} [props.chatId] - 聊天ID
 * @param {string} [props.messageId] - 消息ID
 * @param {function} [props.onFormSubmit] - 表单提交回调
 */
export const DynamicForm: React.FC<DynamicFormProps> = ({ form, chatId, messageId, onFormSubmit }) => {
  const { t } = useTranslation();

  // 构造初始表单值
  const initialValues: Record<string, any> = {};
  form.fields.forEach(field => {
    let v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
    if (field.type === 'checkbox') {
      initialValues[field.id] = Array.isArray(v) ? v : v !== undefined && v !== null && v !== '' ? [v] : [];
    } else {
      initialValues[field.id] = v !== undefined ? v : '';
    }
  });

  // 生成每个字段的校验规则
  const getFieldRules = (field: IFormField) => {
    const rules: Array<{ validator: (rule: any, value: any) => boolean | Error | Error[]; message: string }> = [];
    if (field.required) {
      rules.push({
        validator: (rule: any, value: any) => {
          const result = validateField(field, value, t);
          return result === true ? true : new Error(result);
        },
        message: t('pages.chat.formRequired', { label: field.label })
      });
    } else if (field.validator) {
      rules.push({
        validator: (rule: any, value: any) => {
          const result = validateField(field, value, t);
          return result === true ? true : new Error(result);
        },
        message: t('pages.chat.formValidate', { label: field.label })
      });
    }
    return rules;
  };

  // 表单提交处理
  const handleSubmit = (values: Record<string, any>) => {
    const processedForm = {
      ...form,
      fields: form.fields.map(field => ({
        ...field,
        selectedValue: values[field.id]
      }))
    };
    onFormSubmit?.(form.id, values, chatId, messageId, processedForm);
  };

  return (
    <Card className={styles.cardFormSemi}>
      <Form
        initValues={initialValues}
        onSubmit={handleSubmit}
        style={{ width: '100%' }}
      >
        {form.fields.map(field => {
          const label = t(field.label) || field.label;
          const placeholder = field.placeholder;
          const required = field.required;
          const options = Array.isArray(field.options)
            ? field.options.map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
            : [];
          const rules = getFieldRules(field);
          switch (field.type) {
            case 'text':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'textarea':
              return <Form.TextArea 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'number':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      type="number" 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'select':
              return <Form.Select 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      optionList={options}
                      placeholder={placeholder} />;
            case 'checkbox':
              return <Form.CheckboxGroup 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      options={options} />;
            case 'radio':
              return <Form.RadioGroup 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      options={options} />;
            case 'date':
              return <Form.DatePicker 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      placeholder={placeholder} />;
            case 'password':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      type="password" 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'switch':
              return <Form.Switch 
                      key={field.id}
                      field={field.id} 
                      label={label} />;
            default:
              logger.warn("unkown form field type: ", field.type)
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={label} 
                      placeholder={placeholder} 
                      required={required} />;
          }
        })}
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: 28, marginBottom: 8 }}>
          <Button
            htmlType="submit"
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
          >
            {form.submit_text || t('pages.chat.submit')}
          </Button>
        </div>
      </Form>
    </Card>
  );
};

export default DynamicForm; 