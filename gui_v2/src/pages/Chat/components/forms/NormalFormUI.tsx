import React, { useState, useRef } from 'react';
import { Form, Button, Card, Input, Select, Tooltip, Typography } from '@douyinfe/semi-ui';
import { IconInfoCircle } from '@douyinfe/semi-icons';
import { useTranslation } from 'react-i18next';
import { validateField } from '../../hooks/useChatForm';
import { logger } from '@/utils/logger';
import { DynamicNormalFormProps } from './types';

// Text content component for displaying chat-like text above form
const TextContent: React.FC<{ text?: string }> = ({ text }) => {
  if (!text?.trim()) return null;
  return (
    <div style={{ 
      marginBottom: 20, 
      padding: 16, 
      backgroundColor: 'var(--semi-color-bg-1)',
      borderRadius: 8,
      border: '1px solid var(--semi-color-border)'
    }}>
      <Typography.Paragraph style={{ 
        whiteSpace: 'pre-wrap', 
        wordBreak: 'break-word',
        margin: 0,
        lineHeight: 1.6,
        color: 'var(--semi-color-text-0)'
      }}>
        {text}
      </Typography.Paragraph>
    </div>
  );
};

const NormalFormUI: React.FC<DynamicNormalFormProps> = (props) => {
  const { t } = useTranslation();
  const [sliderValues, setSliderValues] = React.useState<Record<string, number>>({});
  const [customInputMode, setCustomInputMode] = useState<Record<string, boolean>>({});
  const [customInputValue, setCustomInputValue] = useState<Record<string, string>>({});
  const customInputRefs = useRef<Record<string, any>>({});
  const formRef = useRef<any>(null);
  const [localOptions, setLocalOptions] = useState<Record<string, { label: string, value: any }[]>>({});
  const [pendingSelectValue, setPendingSelectValue] = useState<Record<string, any>>({});
  const [selectValue, setSelectValue] = useState<Record<string, any>>({});

  // Guard against undefined props.form or props.form.fields
  // Support both fields and parametric_filters as form fields
  const fields = Array.isArray(props.form?.fields) ? props.form.fields : 
                 Array.isArray(props.form?.parametric_filters) ? props.form.parametric_filters : [];

  // Helper: read options from either 'options' or 'OPTIONS'
  const getFieldOptions = (field: any) => {
    const raw = field?.options ?? field?.OPTIONS;
    return Array.isArray(raw) ? raw : [];
  };

  React.useEffect(() => {
    const init: Record<string, { label: string, value: any }[]> = {};
    fields.forEach(field => {
      if (((field.type as string) === 'select' || (field.type as string) === 'pull_down') && field.custom === true) {
        const baseOpts = getFieldOptions(field);
        let opts = Array.isArray(baseOpts)
          ? baseOpts.map(opt => ({ label: t(opt.label) || String(opt.label), value: opt.value }))
          : [];
        const v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
        if (opts.length === 0 && v !== undefined && v !== null && v !== '') {
          opts = [{ label: String(v), value: v }];
        }
        const fieldId = Array.isArray(field.id) ? field.id.join('_') : String(field.id || '');
        init[fieldId] = opts;
      }
    });
    setLocalOptions(init);
  }, [fields]);

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

  React.useEffect(() => {
    const init: Record<string, any> = {};
    fields.forEach(field => {
      if (((field.type as string) === 'select' || (field.type as string) === 'pull_down') && field.custom === true) {
        const v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
        if (v !== undefined && v !== null && v !== '') {
          const fieldId = Array.isArray(field.id) ? field.id.join('_') : String(field.id || '');
          init[fieldId] = v;
        }
      }
    });
    setSelectValue(init);
  }, [fields]);

  const initialValues: Record<string, any> = {};
  fields.forEach(field => {
    const fieldId = Array.isArray(field.id) ? field.id.join('_') : String(field.id || '');
    let v = field.selectedValue !== undefined ? field.selectedValue : field.defaultValue;
    if (field.type === 'checkbox' || field.type === 'checkboxes') {
      initialValues[fieldId] = Array.isArray(v) ? v : v !== undefined && v !== null && v !== '' ? [v] : [];
    } else if (field.type === 'slider') {
      if (v !== undefined && v !== null && v !== '') {
        initialValues[fieldId] = Number(v);
      } else {
        initialValues[fieldId] = field.min !== undefined ? field.min : 0;
      }
    } else {
      initialValues[fieldId] = v !== undefined ? v : '';
    }
  });

  const getFieldRules = (field: any) => {
    const rules: Array<{ validator: (rule: any, value: any) => boolean | Error | Error[]; message: string }> = [];
    
    // SecurityGet label 字符串
    const safeLabel = Array.isArray(field.label) 
      ? field.label.join(' ') 
      : String(field.label || '');
    
    if (field.required) {
      rules.push({
        validator: (rule: any, value: any) => {
          const result = validateField(field, value, t);
          return result === true ? true : new Error(result);
        },
        message: t('pages.chat.formRequired', { label: safeLabel })
      });
    } else if (field.validator) {
      rules.push({
        validator: (rule: any, value: any) => {
          const result = validateField(field, value, t);
          return result === true ? true : new Error(result);
        },
        message: t('pages.chat.formValidate', { label: safeLabel })
      });
    }
    return rules;
  };

  const handleDoubleClick = (fieldId: string, currentValue?: string) => {
    const field = fields.find(f => {
      const fId = Array.isArray(f.id) ? f.id.join('_') : String(f.id || '');
      return fId === fieldId;
    });
    if (field && field.custom === true) {
      setCustomInputMode(prev => ({ ...prev, [fieldId]: true }));
      setCustomInputValue(prev => ({ ...prev, [fieldId]: currentValue || '' }));
      setTimeout(() => {
        if (customInputRefs.current[fieldId]) {
          customInputRefs.current[fieldId].focus();
        }
      }, 50);
    }
  };
  const handleCustomInputFinish = (fieldId: string) => {
    const value = customInputValue[fieldId]?.trim();
    if (value && formRef.current?.setValue) {
      formRef.current.setValue(fieldId, value);
    }
    setCustomInputMode(prev => ({ ...prev, [fieldId]: false }));
  };

  const handleSubmit: (values: Record<string, any>) => void = (values) => {
    const processedForm = {
      ...props.form,
      fields: fields.map(field => {
        const fieldId = Array.isArray(field.id) ? field.id.join('_') : String(field.id || '');
        const optionsKey = field.hasOwnProperty('options') ? 'options' : (field.hasOwnProperty('OPTIONS') ? 'OPTIONS' : 'options');
        const originalOptions = getFieldOptions(field);
        const nextOptions = ((field.type as string) === 'select' || (field.type as string) === 'pull_down') && field.custom === true
          ? (localOptions[fieldId] || [])
          : originalOptions;
        return {
          ...field,
          selectedValue: values[fieldId],
          [optionsKey]: nextOptions
        };
      })
    };
    props.onFormSubmit?.(props.form.id, values, props.chatId, props.messageId, processedForm);
  };

  const renderField = (field: any) => {
    // 确保 id 是字符串Type
    const fieldId = Array.isArray(field.id) 
      ? field.id.join('_') // If是数组，用下划线Connection
      : String(field.id || ''); // 确保是字符串
    
    // 确保 label 是字符串Type
    const rawLabel = field.label;
    const label = Array.isArray(rawLabel) 
      ? rawLabel.join(' ') // If是数组，用空格Connection
      : (t(rawLabel) || String(rawLabel || '')); // 确保是字符串
    
    const placeholder = field.placeholder ? t(field.placeholder) : '';
    const required = field.required;
    const rules = getFieldRules(field);
    const value = formRef.current?.getValue ? formRef.current.getValue(fieldId) : initialValues[fieldId];
    const isCustom = field.custom === true;
    const options = isCustom
      ? (localOptions[fieldId] || [])
      : (getFieldOptions(field).map((opt: { label: string; value: string | number }) => ({ label: t(opt.label) || String(opt.label), value: opt.value })));
    
    // 为 Semi-UI ComponentCreateTag
    // 有些ComponentNeed字符串Type的 label，有些Can接受 React 元素
    const labelText = label; // 纯文本Tag
    const labelNode = (
      <label className="semi-form-field-label" htmlFor={fieldId}>
        {required && <span className="semi-form-field-label-asterisk">*</span>}
        {label}
        {field.tooltip && (
          <Tooltip content={t(field.tooltip)}>
            <IconInfoCircle style={{ marginLeft: 4, color: 'var(--semi-color-primary)', verticalAlign: 'middle', cursor: 'pointer' }} />
          </Tooltip>
        )}
      </label>
    );
    if (field.type === 'group' && Array.isArray(field.fields)) {
      return (
        <Card key={fieldId} style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 8 }}>{label}</div>
          {field.fields.map(renderField)}
        </Card>
      );
    }
    switch (field.type) {
      case 'text':
        return <Form.Input 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                placeholder={placeholder} 
                required={required} 
                rules={rules} />;
      case 'textarea':
        return <Form.TextArea 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                placeholder={placeholder} 
                required={required} 
                rules={rules} />;
      case 'number':
        return <Form.Input 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                type="number" 
                placeholder={placeholder} 
                required={required} 
                rules={rules} />;
      case 'select': {
        if (isCustom) {
          let errorMsg = '';
          if (formRef.current && formRef.current.getFieldError) {
            const err = formRef.current.getFieldError(fieldId);
            if (Array.isArray(err) && err.length > 0) errorMsg = err[0];
            else if (typeof err === 'string') errorMsg = err;
          }
          const helpText = field.helpText ? t(field.helpText) : '';
          if (customInputMode[fieldId]) {
            return (
              <div key={fieldId} className="semi-form-field">
                <label className="semi-form-field-label" htmlFor={`custom-input-select-${fieldId}`}>
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
                    id={`custom-input-select-${fieldId}`}
                    ref={el => customInputRefs.current[fieldId] = el}
                    value={customInputValue[fieldId] || ''}
                    placeholder={placeholder || t('pages.chat.customInputPlaceholder')}
                    onChange={v => setCustomInputValue(prev => ({ ...prev, [fieldId]: v }))}
                    onBlur={() => {
                      const v = customInputValue[fieldId]?.trim();
                      if (v) {
                        const exists = (localOptions[fieldId] || []).some(opt => opt.value === v);
                        if (!exists) {
                          setLocalOptions(prev => {
                            const updated = {
                              ...prev,
                              [fieldId]: [...(prev[fieldId] || []), { label: v, value: v }]
                            };
                            setTimeout(() => {
                              setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                              if (formRef.current?.setValue) {
                                formRef.current.setValue(fieldId, v);
                              }
                            }, 0);
                            return updated;
                          });
                        } else {
                          setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                          if (formRef.current?.setValue) {
                            formRef.current.setValue(fieldId, v);
                          }
                        }
                        handleCustomInputFinish(fieldId);
                      }
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        const v = customInputValue[fieldId]?.trim();
                        if (v) {
                          const exists = (localOptions[fieldId] || []).some(opt => opt.value === v);
                          if (!exists) {
                            setLocalOptions(prev => {
                              const updated = {
                                ...prev,
                                [fieldId]: [...(prev[fieldId] || []), { label: v, value: v }]
                              };
                              setTimeout(() => {
                                setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                                if (formRef.current?.setValue) {
                                  formRef.current.setValue(fieldId, v);
                                }
                              }, 0);
                              return updated;
                            });
                          } else {
                            setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                            if (formRef.current?.setValue) {
                              formRef.current.setValue(fieldId, v);
                            }
                          }
                        }
                        handleCustomInputFinish(fieldId);
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
          return (
            <div key={fieldId} className="semi-form-field">
              <label className="semi-form-field-label" htmlFor={`select-${fieldId}`}>
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
                    id={`select-${fieldId}`}
                    value={selectValue[fieldId]}
                    onChange={v => {
                      setSelectValue(sv => {
                        if (formRef.current?.setValue) {
                          formRef.current.setValue(fieldId, v);
                        }
                        return { ...sv, [fieldId]: v };
                      });
                    }}
                    optionList={options}
                    placeholder={placeholder}
                    renderSelectedItem={(optionNode: any) => {
                      const isInOptions = options.some((opt: { label: string; value: string | number }) => opt.value === optionNode.value);
                      if (!isInOptions && optionNode.value) {
                        return (
                          <div
                            style={{ display: 'flex', alignItems: 'center', width: '100%', cursor: 'pointer' }}
                            onDoubleClick={() => handleDoubleClick(fieldId, optionNode.value)}
                          >
                            <span style={{ flex: 1 }}>{optionNode.label || optionNode.value}</span>
                            <i className="semi-icon-edit" style={{ fontSize: '12px', marginLeft: '4px' }}></i>
                          </div>
                        );
                      }
                      return (
                        <div
                          style={{ width: '100%', cursor: 'pointer' }}
                          onDoubleClick={() => handleDoubleClick(fieldId, optionNode.value)}
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
          return (
            <Form.Select
              key={fieldId}
              field={fieldId}
              label={labelNode}
              optionList={options}
              placeholder={placeholder}
              rules={rules}
              allowCreate={false}
            />
          );
        }
      }
      case 'pull_down': {
        // pull_down 与 select Process方式相同
        if (isCustom) {
          let errorMsg = '';
          if (formRef.current && formRef.current.getFieldError) {
            const err = formRef.current.getFieldError(fieldId);
            if (Array.isArray(err) && err.length > 0) errorMsg = err[0];
            else if (typeof err === 'string') errorMsg = err;
          }
          const helpText = field.helpText ? t(field.helpText) : '';
          if (customInputMode[fieldId]) {
            return (
              <div key={fieldId} className="semi-form-field">
                <label className="semi-form-field-label" htmlFor={`custom-input-pulldown-${fieldId}`}>
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
                    id={`custom-input-pulldown-${fieldId}`}
                    ref={el => customInputRefs.current[fieldId] = el}
                    value={customInputValue[fieldId] || ''}
                    placeholder={placeholder || t('pages.chat.customInputPlaceholder')}
                    onChange={v => setCustomInputValue(prev => ({ ...prev, [fieldId]: v }))}
                    onBlur={() => {
                      const v = customInputValue[fieldId]?.trim();
                      if (v) {
                        const exists = (localOptions[fieldId] || []).some(opt => opt.value === v);
                        if (!exists) {
                          setLocalOptions(prev => {
                            const updated = {
                              ...prev,
                              [fieldId]: [...(prev[fieldId] || []), { label: v, value: v }]
                            };
                            setTimeout(() => {
                              setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                              if (formRef.current?.setValue) {
                                formRef.current.setValue(fieldId, v);
                              }
                            }, 0);
                            return updated;
                          });
                        } else {
                          setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                          if (formRef.current?.setValue) {
                            formRef.current.setValue(fieldId, v);
                          }
                        }
                        handleCustomInputFinish(fieldId);
                      }
                    }}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        const v = customInputValue[fieldId]?.trim();
                        if (v) {
                          const exists = (localOptions[fieldId] || []).some(opt => opt.value === v);
                          if (!exists) {
                            setLocalOptions(prev => {
                              const updated = {
                                ...prev,
                                [fieldId]: [...(prev[fieldId] || []), { label: v, value: v }]
                              };
                              setTimeout(() => {
                                setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                                if (formRef.current?.setValue) {
                                  formRef.current.setValue(fieldId, v);
                                }
                              }, 0);
                              return updated;
                            });
                          } else {
                            setSelectValue(sv => ({ ...sv, [fieldId]: v }));
                            if (formRef.current?.setValue) {
                              formRef.current.setValue(fieldId, v);
                            }
                          }
                        }
                        handleCustomInputFinish(fieldId);
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
          return (
            <div key={fieldId} className="semi-form-field">
              <label className="semi-form-field-label" htmlFor={`pulldown-${fieldId}`}>
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
                    id={`pulldown-${fieldId}`}
                    value={selectValue[fieldId]}
                    onChange={v => {
                      setSelectValue(sv => {
                        if (formRef.current?.setValue) {
                          formRef.current.setValue(fieldId, v);
                        }
                        return { ...sv, [fieldId]: v };
                      });
                    }}
                    optionList={options}
                    placeholder={placeholder}
                    renderSelectedItem={(optionNode: any) => {
                      const isInOptions = options.some((opt: { label: string; value: string | number }) => opt.value === optionNode.value);
                      if (!isInOptions && optionNode.value) {
                        return (
                          <div
                            style={{ display: 'flex', alignItems: 'center', width: '100%', cursor: 'pointer' }}
                            onDoubleClick={() => handleDoubleClick(fieldId, optionNode.value)}
                          >
                            <span style={{ flex: 1 }}>{optionNode.label || optionNode.value}</span>
                            <i className="semi-icon-edit" style={{ fontSize: '12px', marginLeft: '4px' }}></i>
                          </div>
                        );
                      }
                      return (
                        <div
                          style={{ width: '100%', cursor: 'pointer' }}
                          onDoubleClick={() => handleDoubleClick(fieldId, optionNode.value)}
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
          return (
            <Form.Select
              key={fieldId}
              field={fieldId}
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
                key={fieldId} 
                field={fieldId} 
                label={labelText} 
                options={options.map((opt: { label: string; value: string | number }) => opt as { label: string; value: string | number })} />;
      case 'checkboxes':
        // Process checkboxes Type (复数形式)，与 checkbox 相同
        return <Form.CheckboxGroup 
                key={fieldId} 
                field={fieldId} 
                label={labelText} 
                options={options.map((opt: { label: string; value: string | number }) => opt as { label: string; value: string | number })} />;
      case 'radio':
        return <Form.RadioGroup 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                options={options.map((opt: { label: string; value: string | number }) => opt as { label: string; value: string | number })} />;
      case 'date':
        return <Form.DatePicker 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                placeholder={placeholder} />;
      case 'password':
        return <Form.Input 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                type="password" 
                placeholder={placeholder} 
                required={required} 
                rules={rules} />;
      case 'switch':
        return <Form.Switch 
                key={fieldId}
                field={fieldId} 
                label={labelNode} />;
      case 'slider':
        const currentValue = sliderValues[fieldId] !== undefined ? sliderValues[fieldId] : initialValues[fieldId];
        const min = field.min !== undefined ? field.min : 0;
        const max = field.max !== undefined ? field.max : 100;
        const step = field.step !== undefined ? field.step : 1;
        const unit = field.unit || '';
        const percentage = ((currentValue - min) / (max - min)) * 100;
        return (
          <div key={fieldId} style={{ width: '100%', position: 'relative' }}>
            <Form.Slider
              field={fieldId}
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
                    [fieldId]: value
                  }));
                }
              }}
            />
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
              zIndex: 100, // Content层级
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)'
            }}>
              {currentValue}{unit}
            </div>
          </div>
        );
      default:
        logger.warn("unkown form field type: ", field.type)
        return <Form.Input 
                key={fieldId} 
                field={fieldId} 
                label={labelNode} 
                placeholder={placeholder} 
                required={required} />;
    }
  };

  return (
    <div>
      {/* Display text content above the form if it exists */}
      <TextContent text={props.form.text} />
      
      <Card>
        {props.form.title && (
          <>
            <div style={{ fontWeight: 600, fontSize: 18, marginBottom: 8, textAlign: 'center' }}>{props.form.title}</div>
            <div style={{ borderBottom: '1px solid #e5e6eb', margin: '0 auto 16px auto', width: '60%' }} />
          </>
        )}
        <Form
          ref={formRef}
          initValues={initialValues}
          onSubmit={handleSubmit}
          style={{ width: '100%' }}
        >
          {fields.map(renderField)}
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
              {props.form.submit_text ? t(props.form.submit_text) : t('pages.chat.submit')}
            </Button>
          </div>
        </Form>
      </Card>
    </div>
  );
};

export default NormalFormUI;