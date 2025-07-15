import React, { useState, useRef } from 'react';
import { Form, Button, Card, Slider, Input, Select, Tooltip } from '@douyinfe/semi-ui';
import { IconInfoCircle } from '@douyinfe/semi-icons';
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
 * 支持 text、textarea、number、select、checkbox、radio、date、password、switch、slider 等类型。
 * @param {object} props
 * @param {object} props.form - 表单配置对象，包含 fields 数组
 * @param {string} [props.chatId] - 聊天ID
 * @param {string} [props.messageId] - 消息ID
 * @param {function} [props.onFormSubmit] - 表单提交回调
 */
export const DynamicForm: React.FC<DynamicFormProps> = ({ form, chatId, messageId, onFormSubmit }) => {
  const { t } = useTranslation();
  const [sliderValues, setSliderValues] = React.useState<Record<string, number>>({});
  const [customInputMode, setCustomInputMode] = useState<Record<string, boolean>>({});
  const [customInputValue, setCustomInputValue] = useState<Record<string, string>>({});
  const customInputRefs = useRef<Record<string, any>>({});
  const formRef = useRef<any>(null);
  // 新增：本地 options 状态
  const [localOptions, setLocalOptions] = useState<Record<string, { label: string, value: any }[]>>({});
  const [pendingSelectValue, setPendingSelectValue] = useState<Record<string, any>>({});
  const [selectValue, setSelectValue] = useState<Record<string, any>>({});

  // 初始化本地 options
  React.useEffect(() => {
    const init: Record<string, { label: string, value: any }[]> = {};
    form.fields.forEach(field => {
      if (field.type === 'select' && field.custom === true) {
        let opts = Array.isArray(field.options)
          ? field.options.map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
          : [];
        const v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
        // 只有 options 为空时才补充 defaultValue/selectedValue
        if (opts.length === 0 && v !== undefined && v !== null && v !== '') {
          opts = [{ label: String(v), value: v }];
        }
        init[field.id] = opts;
      }
    });
    setLocalOptions(init);
    // eslint-disable-next-line
  }, [form.fields]);

  // useEffect 监听 localOptions 变化，自动选中 pendingSelectValue
  React.useEffect(() => {
    Object.entries(pendingSelectValue).forEach(([fieldId, v]) => {
      if (v !== undefined && v !== null && localOptions[fieldId]) {
        const exists = localOptions[fieldId].some(opt => opt.value === v);
        const current = formRef.current?.getValue ? formRef.current.getValue(fieldId) : undefined;
        if (exists && current !== v && formRef.current?.setValue) {
          formRef.current.setValue(fieldId, v);
          setPendingSelectValue(prev => ({ ...prev, [fieldId]: undefined }));
        }
      }
    });
  }, [localOptions, pendingSelectValue, formRef]);

  // 初始化 selectValue
  React.useEffect(() => {
    const init: Record<string, any> = {};
    form.fields.forEach(field => {
      if (field.type === 'select' && field.custom === true) {
        const v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
        if (v !== undefined && v !== null && v !== '') {
          init[field.id] = v;
        }
        // 没有 defaultValue/selectedValue 就不赋值，value 为 undefined
      }
    });
    setSelectValue(init);
  }, [form.fields]);

  // 构造初始表单值
  const initialValues: Record<string, any> = {};
  form.fields.forEach(field => {
    let v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;

    if (field.type === 'checkbox') {
      initialValues[field.id] = Array.isArray(v) ? v : v !== undefined && v !== null && v !== '' ? [v] : [];
    } else if (field.type === 'slider') {
      // 滑动组件的默认值处理
      if (v !== undefined && v !== null && v !== '') {
        initialValues[field.id] = Number(v);
      } else {
        // 如果没有默认值，使用最小值或0
        initialValues[field.id] = field.min !== undefined ? field.min : 0;
      }
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

  // 处理双击事件，激活自定义输入模式
  const handleDoubleClick = (fieldId: string, currentValue?: string) => {
    // 只有当字段配置为允许自定义时才处理
    const field = form.fields.find(f => f.id === fieldId);
    if (field && field.custom === true) {
      setCustomInputMode(prev => ({ ...prev, [fieldId]: true }));
      setCustomInputValue(prev => ({ ...prev, [field.id]: currentValue || '' }));
      // 延迟一点，确保状态更新后再聚焦
      setTimeout(() => {
        if (customInputRefs.current[fieldId]) {
          customInputRefs.current[fieldId].focus();
        }
      }, 50);
    }
  };
  // 输入框失焦或回车，保存自定义值并切回 select
  const handleCustomInputFinish = (fieldId: string) => {
    const value = customInputValue[fieldId]?.trim();
    if (value && formRef.current?.setValue) {
      formRef.current.setValue(fieldId, value);
    }
    setCustomInputMode(prev => ({ ...prev, [fieldId]: false }));
  };

  // 表单提交处理
  const handleSubmit: (values: Record<string, any>) => void = (values) => {
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
    <Card>
      <Form
        ref={formRef}
        initValues={initialValues}
        onSubmit={handleSubmit}
        style={{ width: '100%' }}
      >
        {form.fields.map((field: any) => {
          const label = t(field.label) || field.label;
          const placeholder = field.placeholder ? t(field.placeholder) : '';
          const required = field.required;
          const rules = getFieldRules(field);
          const value = formRef.current?.getValue ? formRef.current.getValue(field.id) : initialValues[field.id];
          const isCustom = field.custom === true;
          // 选项来源：custom 用 localOptions，否则用原始 options
          const options = isCustom
            ? (localOptions[field.id] || [])
            : (Array.isArray(field.options)
                ? field.options.map((opt: { label: string; value: string | number }) => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
                : []);
          // labelNode 统一处理所有类型
          const labelNode = (
            <label className="semi-form-field-label">
              {required && <span className="semi-form-field-label-asterisk">*</span>}
              {label}
              {field.tooltip && (
                <Tooltip content={t(field.tooltip)}>
                  <IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} />
                </Tooltip>
              )}
            </label>
          );
          switch (field.type) {
            case 'text':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'textarea':
              return <Form.TextArea 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'number':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      type="number" 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'select': {
              if (isCustom) {
                // 获取错误信息
                let errorMsg = '';
                if (formRef.current && formRef.current.getFieldError) {
                  const err = formRef.current.getFieldError(field.id);
                  if (Array.isArray(err) && err.length > 0) errorMsg = err[0];
                  else if (typeof err === 'string') errorMsg = err;
                }
                // 获取帮助文本
                const helpText = field.helpText ? t(field.helpText) : '';
                if (customInputMode[field.id]) {
                  return (
                    <div key={field.id} className="semi-form-field">
                      <label className="semi-form-field-label">
                        {required && <span className="semi-form-field-label-asterisk">*</span>}
                        {label}
                        {field.tooltip && (
                          <Tooltip content={t(field.tooltip)}>
                            <IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} />
                          </Tooltip>
                        )}
                      </label>
                      <div className="semi-form-field-control">
                        <Input
                          ref={el => customInputRefs.current[field.id] = el}
                          value={customInputValue[field.id] || ''}
                          placeholder={placeholder || t('pages.chat.customInputPlaceholder')}
                          onChange={v => setCustomInputValue(prev => ({ ...prev, [field.id]: v }))}
                          onBlur={() => {
                            const v = customInputValue[field.id]?.trim();
                            if (v) {
                              const exists = (localOptions[field.id] || []).some(opt => opt.value === v);
                              if (!exists) {
                                setLocalOptions(prev => {
                                  const updated = {
                                    ...prev,
                                    [field.id]: [...(prev[field.id] || []), { label: v, value: v }]
                                  };
                                  setSelectValue(sv => ({ ...sv, [field.id]: v }));
                                  if (formRef.current?.setValue) {
                                    formRef.current.setValue(field.id, v);
                                  }
                                  return updated;
                                });
                              } else {
                                setSelectValue(sv => ({ ...sv, [field.id]: v }));
                                if (formRef.current?.setValue) {
                                  formRef.current.setValue(field.id, v);
                                }
                              }
                              handleCustomInputFinish(field.id);
                            }
                          }}
                          onKeyDown={e => {
                            if (e.key === 'Enter') {
                              const v = customInputValue[field.id]?.trim();
                              if (v) {
                                const exists = (localOptions[field.id] || []).some(opt => opt.value === v);
                                if (!exists) {
                                  setLocalOptions(prev => {
                                    const updated = {
                                      ...prev,
                                      [field.id]: [...(prev[field.id] || []), { label: v, value: v }]
                                    };
                                    setSelectValue(sv => ({ ...sv, [field.id]: v }));
                                    if (formRef.current?.setValue) {
                                      formRef.current.setValue(field.id, v);
                                    }
                                    return updated;
                                  });
                                } else {
                                  setSelectValue(sv => ({ ...sv, [field.id]: v }));
                                  if (formRef.current?.setValue) {
                                    formRef.current.setValue(field.id, v);
                                  }
                                }
                              }
                              handleCustomInputFinish(field.id);
                            }
                          }}
                          style={{ width: '100%' }}
                        />
                      </div>
                      {helpText && <div className="semi-form-field-extra">{helpText}</div>}
                      {errorMsg && <div className="semi-form-field-error-message">{errorMsg}</div>}
                    </div>
                  );
                }
                // custom: true 的 select 用 <Select />，不传 field
                return (
                  <div key={field.id} className="semi-form-field">
                    <label className="semi-form-field-label">
                      {required && <span className="semi-form-field-label-asterisk">*</span>}
                      {label}
                      {field.tooltip && (
                        <Tooltip content={t(field.tooltip)}>
                          <IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} />
                        </Tooltip>
                      )}
                    </label>
                    <div className="semi-form-field-control">
                      <Tooltip content={t('pages.chat.doubleClickToEdit')} position="right">
                        <Select
                          value={selectValue[field.id]}
                          onChange={v => {
                            setSelectValue(sv => ({ ...sv, [field.id]: v }));
                            if (formRef.current?.setValue) {
                              formRef.current.setValue(field.id, v);
                            }
                          }}
                          optionList={options}
                          placeholder={placeholder}
                          renderSelectedItem={(optionNode: any) => {
                            const isInOptions = options.some((opt: { label: string; value: string | number }) => opt.value === optionNode.value);
                            if (!isInOptions && optionNode.value) {
                              return (
                                <div
                                  style={{ display: 'flex', alignItems: 'center', width: '100%', cursor: 'pointer' }}
                                  onDoubleClick={() => handleDoubleClick(field.id, optionNode.value)}
                                >
                                  <span style={{ flex: 1 }}>{optionNode.label || optionNode.value}</span>
                                  <i className="semi-icon-edit" style={{ fontSize: '12px', marginLeft: '4px' }}></i>
                                </div>
                              );
                            }
                            return (
                              <div
                                style={{ width: '100%', cursor: 'pointer' }}
                                onDoubleClick={() => handleDoubleClick(field.id, optionNode.value)}
                              >
                                {optionNode.label}
                              </div>
                            );
                          }}
                        />
                      </Tooltip>
                    </div>
                    {helpText && <div className="semi-form-field-extra">{helpText}</div>}
                    {errorMsg && <div className="semi-form-field-error-message">{errorMsg}</div>}
                  </div>
                );
              } else {
                // 普通选择框
                return (
                  <Form.Select
                    key={field.id}
                    field={field.id}
                    label={labelNode}
                    optionList={options}
                    placeholder={placeholder}
                    rules={rules}
                    allowCreate={false}
                  />
                );
              }
            }
            case 'checkbox':
              return <Form.CheckboxGroup 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      options={options.map((opt: { label: string; value: string | number }) => opt as { label: string; value: string | number })} />;
            case 'radio':
              return <Form.RadioGroup 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      options={options.map((opt: { label: string; value: string | number }) => opt as { label: string; value: string | number })} />;
            case 'date':
              return <Form.DatePicker 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      placeholder={placeholder} />;
            case 'password':
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
                      type="password" 
                      placeholder={placeholder} 
                      required={required} 
                      rules={rules} />;
            case 'switch':
              return <Form.Switch 
                      key={field.id}
                      field={field.id} 
                      label={labelNode} />;
            case 'slider':
              const currentValue = sliderValues[field.id] !== undefined ? sliderValues[field.id] : initialValues[field.id];
              const min = field.min !== undefined ? field.min : 0;
              const max = field.max !== undefined ? field.max : 100;
              const step = field.step !== undefined ? field.step : 1;
              const unit = field.unit || '';
              
              // 计算当前值在滑块上的位置百分比
              const percentage = ((currentValue - min) / (max - min)) * 100;
              
              return (
                <div key={field.id} style={{ width: '100%', position: 'relative' }}>
                  <Form.Slider
                    field={field.id}
                    label={labelNode}
                    min={min}
                    max={max}
                    step={step}
                    marks={{
                      [min]: `${min}${unit}`,
                      [max]: `${max}${unit}`
                    }}
                    tipFormatter={(value) => `${value}${unit}`}
                    style={{ width: '100%' }}
                    onChange={(value) => {
                      if (typeof value === 'number') {
                        setSliderValues(prev => ({
                          ...prev,
                          [field.id]: value
                        }));
                      }
                    }}
                  />
                  {/* 在滑块中间显示当前值 */}
                  <div style={{
                    position: 'absolute',
                    top: '35%',
                    left: `${Math.max(10, Math.min(90, percentage))}%`,
                    transform: 'translate(-50%, -50%)',
                    backgroundColor: '#1890ff',
                    color: 'white',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                    zIndex: 10,
                    boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
                  }}>
                    {currentValue}{unit}
                  </div>
                </div>
              );
            default:
              logger.warn("unkown form field type: ", field.type)
              return <Form.Input 
                      key={field.id} 
                      field={field.id} 
                      label={labelNode} 
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
            {form.submit_text ? t(form.submit_text) : t('pages.chat.submit')}
          </Button>
        </div>
      </Form>
    </Card>
  );
};

export default DynamicForm; 