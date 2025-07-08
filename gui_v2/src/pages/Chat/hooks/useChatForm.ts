import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormField } from '../types/chat';

type ValidationResult = { isValid: boolean; errors: Record<string, string> };

type ValidatorFn = (value: any, ...args: any[]) => string | true;

export const useChatForm = (fields: FormField[]) => {
  const { t } = useTranslation();

  const validators: Record<string, ValidatorFn> = {
    required: (value: any, fieldName: string): string | true => {
      if (!value && value !== 0 && value !== false) {
        return t('pages.chat.formRequired', { label: fieldName });
      }
      return true;
    },
    email: (value: string): string | true => {
      if (!value) return true;
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      return emailRegex.test(value) ? true : t('pages.chat.formEmail');
    },
    minLength: (value: string, length: number): string | true => {
      if (!value) return true;
      return value.length >= length ? true : t('pages.chat.formMinLength', { length });
    },
    maxLength: (value: string, length: number): string | true => {
      if (!value) return true;
      return value.length <= length ? true : t('pages.chat.formMaxLength', { length });
    },
    number: (value: any): string | true => {
      if (!value && value !== 0) return true;
      return !isNaN(Number(value)) ? true : t('pages.chat.formNumber');
    },
    range: (value: number, min: number, max: number): string | true => {
      if (!value && value !== 0) return true;
      const num = Number(value);
      return num >= min && num <= max ? true : t('pages.chat.formRange', { min, max });
    }
  };

  const validateField = (field: FormField, value: any): string | true => {
    if (field.required && validators.required(value, field.label) !== true) {
      return validators.required(value, field.label);
    }
    if (field.validator) {
      const [validatorName, ...args] = field.validator.split(':');
      const validatorFn = validators[validatorName];
      if (validatorFn) {
        if (args.length > 0) {
          switch (validatorName) {
            case 'minLength':
            case 'maxLength': {
              const length = Number(args[0]);
              const result = validatorFn(value, length);
              return result;
            }
            case 'range': {
              const min = Number(args[0]);
              const max = Number(args[1]);
              const result = validatorFn(value, min, max);
              return result;
            }
            default:
              return validatorFn(value);
          }
        } else {
          return validatorFn(value);
        }
      }
    }
    switch (field.type) {
      case 'number':
        return validators.number(value);
      default:
        return true;
    }
  };

  const [formState, setFormState] = useState<Record<string, any>>(() => {
    const initialState: Record<string, any> = {};
    fields.forEach(field => {
      initialState[field.id] = field.defaultValue !== undefined ? field.defaultValue : '';
    });
    return initialState;
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const handleChange = (fieldId: string, value: any) => {
    setFormState(prev => ({
      ...prev,
      [fieldId]: value
    }));
    if (errors[fieldId]) {
      setErrors(prev => {
        const updated = { ...prev };
        delete updated[fieldId];
        return updated;
      });
    }
  };
  const validateForm = (): ValidationResult => {
    const newErrors: Record<string, string> = {};
    let isValid = true;
    fields.forEach(field => {
      const value = formState[field.id];
      const result = validateField(field, value);
      if (result !== true) {
        newErrors[field.id] = result;
        isValid = false;
      }
    });
    setErrors(newErrors);
    return { isValid, errors: newErrors };
  };
  const resetForm = () => {
    const initialState: Record<string, any> = {};
    fields.forEach(field => {
      initialState[field.id] = field.defaultValue !== undefined ? field.defaultValue : '';
    });
    setFormState(initialState);
    setErrors({});
  };
  return {
    formState,
    errors,
    handleChange,
    validateForm,
    resetForm,
    setFormState
  };
};

export default useChatForm; 