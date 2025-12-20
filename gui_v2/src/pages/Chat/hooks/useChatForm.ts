import { useTranslation } from 'react-i18next';
import { FormField } from '../types/chat';

// 校验器ToolFunction
export const getValidators = (t: any) => ({
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
});

type ValidatorFn = (...args: any[]) => string | true;

// 单Field校验Function
export const validateField = (field: FormField, value: any, t: any): string | true => {
  const validators = getValidators(t) as Record<string, ValidatorFn>;
  if (field.required && validators.required(value, field.label) !== true) {
    return validators.required(value, field.label);
  }
  if (field.validator) {
    const [validatorName, ...args] = field.validator.split(':');
    const validatorFn = validators[validatorName] as ValidatorFn | undefined;
    if (validatorFn) {
      if (args.length > 0) {
        switch (validatorName) {
          case 'minLength':
          case 'maxLength': {
            const length = Number(args[0]);
            return validatorFn(value, length);
          }
          case 'range': {
            const min = Number(args[0]);
            const max = Number(args[1]);
            return validatorFn(value, min, max);
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