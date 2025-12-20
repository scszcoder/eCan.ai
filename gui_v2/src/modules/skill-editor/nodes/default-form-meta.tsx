/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';
import {
  autoRenameRefEffect,
  provideJsonSchemaOutputs,
  syncVariableTitle,
  DisplayOutputs,
  validateFlowValue,
  validateWhenVariableSync,
  listenRefSchemaChange,
} from '@flowgram.ai/form-materials';
import { Divider } from '@douyinfe/semi-ui';

import { FlowNodeJSON } from '../typings';
import { FormHeader, FormContent, FormInputs } from '../form-components';
import { isValidationDisabled } from '../services/validation-config';
 

export const renderForm = ({ form }: FormRenderProps<FlowNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <FormInputs />
      <Divider />
      <DisplayOutputs displayFromScope />
    </FormContent>
  </>
);

function normalizeFlowValueForSchema(val: any, schema: any) {
  const toSafeString = (v: any) => {
    if (v == null) return '';
    return typeof v === 'object' ? JSON.stringify(v, null, 2) : String(v);
  };

  try {
    if (!schema) return val;
    const t = schema.type;
    // If it's already a FlowValue with content, coerce content types as needed
    if (val && typeof val === 'object' && 'content' in val) {
      const c = (val as any).content;
      // Handle number type: convert empty strings to actual numbers or remove schema if empty
      if (t === 'number') {
        if (c === '' || c === null || c === undefined) {
          // Remove schema property for empty number fields
          const { schema: _, ...rest } = val as any;
          return rest;
        }
        // Ensure content is a number
        const num = typeof c === 'number' ? c : parseFloat(c);
        return { ...val, content: isNaN(num) ? 0 : num };
      }
      if (t === 'string' && typeof c !== 'string') {
        return { ...val, content: toSafeString(c) };
      }
      if ((t === 'array' || t === 'object') && typeof c !== 'string') {
        return { ...val, content: toSafeString(c) };
      }
      return val;
    }
    // If not a FlowValue, wrap for string/object/array to avoid editor crashes
    if (t === 'string') {
      return { type: 'constant', content: toSafeString(val) } as any;
    }
    if (t === 'number') {
      // Ensure number values are properly wrapped
      const num = typeof val === 'number' ? val : parseFloat(val);
      return { type: 'constant', content: isNaN(num) ? 0 : num } as any;
    }
    if (t === 'array' || t === 'object') {
      const defStr = t === 'array' ? '[]' : '{}';
      const safe = val == null ? defStr : (typeof val === 'string' ? val : JSON.stringify(val, null, 2));
      return { type: 'constant', content: safe } as any;
    }
  } catch (_) {}
  return val;
}

export const defaultFormMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  /**
   * Supported writing as:
   * 1: validate as options: { title: () => {} , ... }
   * 2: validate as dynamic function: (values,  ctx) => ({ title: () => {}, ... })
   */
  validate: (values, context) => {
    if (isValidationDisabled()) {
      return {};
    }
    return {
      title: ({ value }: any) => (value ? undefined : 'Title is required'),
      'inputsValues.*': ({ value, context, formValues, name }: any) => {
        const valuePropertyKey = name.replace(/^inputsValues\./, '');
        const required = formValues.inputs?.required || [];

        return validateFlowValue(value, {
          node: context.node,
          required: required.includes(valuePropertyKey),
          errorMessages: {
            required: `${valuePropertyKey} is required`,
          },
        });
      },
    } as any;
  },
  /**
   * Initialize (fromJSON) data transformation
   * Initialize(fromJSON) DataConvert
   * @param value
   * @param ctx
   */
  formatOnInit: (value, ctx) => {
    try {
      const v = { ...(value as any) };
      const data = v.data || {};
      const inputsValues = { ...(data.inputsValues || {}) };
      const inputsSchema = data.inputs?.properties || {};
      // normalize each inputsValues entry against its schema
      Object.keys(inputsValues).forEach((k) => {
        inputsValues[k] = normalizeFlowValueForSchema(inputsValues[k], inputsSchema[k]);
      });
      v.data = { ...data, inputsValues };
      return v;
    } catch {
      return value;
    }
  },
  /**
   * Save (toJSON) data transformation
   * Save(toJSON) DataConvert
   * @param value
   * @param ctx
   */
  formatOnSubmit: (value, ctx) => {
    try {
      const v = { ...(value as any) };
      const data = v.data || {};
      const inputsValues = { ...(data.inputsValues || {}) };
      const inputsSchema = data.inputs?.properties || {};
      Object.keys(inputsValues).forEach((k) => {
        inputsValues[k] = normalizeFlowValueForSchema(inputsValues[k], inputsSchema[k]);
      });
      v.data = { ...data, inputsValues };
      return v;
    } catch {
      return value;
    }
  },
  effect: {
    title: syncVariableTitle,
    outputs: provideJsonSchemaOutputs,
    inputsValues: [...autoRenameRefEffect, ...validateWhenVariableSync({ scope: 'public' })],
    'inputsValues.*': listenRefSchemaChange((_params) => {
      // Debug: Schema reference updated (disabled in production)
      // console.log(`[${_params.context.node.id}][${_params.name}] Schema Of Ref Updated`);
    }),
  },
};
