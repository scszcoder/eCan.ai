/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger } from '@flowgram.ai/free-layout-editor';
import { createInferInputsPlugin, DisplayOutputs } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { defaultFormMeta } from '../default-form-meta';
import { FormHeader, FormContent, FormInputs } from '../../form-components';
import { FormCallable } from '../../form-components/form-callable';

export const renderForm = (_props: FormRenderProps<FlowNodeJSON>) => {

  return (
    <>
      <FormHeader />
      <FormContent>
        <div className="mcp-node-form">
          {/* 1) Tool selector */}
          <FormCallable />
          {/* 2) Dynamic tool inputs */}
          <div style={{ height: 1, background: '#e8e8e8', margin: '12px 0', width: '100%' }} />
          <div style={{ fontWeight: 600, marginBottom: 8 }}>Tool Inputs</div>
          {/* Dynamic inputs based on selected tool schema (data.callable.params) */}
          <FormInputs />
          {/* 3) Outputs */}
          <div style={{ height: 1, background: '#e8e8e8', margin: '12px 0', width: '100%' }} />
          <DisplayOutputs displayFromScope />

          {/* Node State panel is rendered globally in BaseNode; omit here to avoid duplication */}
        </div>
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: defaultFormMeta.validate,
  effect: {
    ...defaultFormMeta.effect,
    // When tool selection changes, project its params schema into data.inputs
    'data.callable': [({ form, formValues }: any) => {
      try { console.log('[MCP] MCP effect data.callable triggered with:', (formValues as any)?.data?.callable); } catch {}
      try {
        const callable = (formValues as any)?.data?.callable;
        const paramsSchema = callable?.params || { type: 'object', properties: {} };
        const rootProps = paramsSchema?.properties || {};
        const rootReq: string[] = Array.isArray(paramsSchema?.required) ? paramsSchema.required : [];
        // If schema is { properties: { input: { type:'object', properties:{...} } } }, flatten to input's properties
        const hasInputObject = rootProps.input && typeof rootProps.input === 'object' && rootProps.input.type === 'object';
        const rawProperties = hasInputObject ? (rootProps.input.properties || {}) : rootProps;
        const rawRequired: string[] = hasInputObject
          ? (Array.isArray(rootProps.input.required) ? rootProps.input.required : Object.keys(rawProperties))
          : (rootReq.length ? rootReq : Object.keys(rawProperties));

        // Normalize non-standard types to JSONSchema-friendly
        const normalizeType = (t: any): any => {
          if (!t || typeof t !== 'string') return t;
          const s = t.trim().toLowerCase();
          if (s === 'float') return 'number';
          if (s === 'dict') return 'object';
          if (s === '[int]' || s === '[integer]') return { type: 'array', items: { type: 'integer' } };
          if (s === '[string]' || s === '[str]') return { type: 'array', items: { type: 'string' } };
          return t; // 'string' | 'integer' | 'number' | 'boolean' | 'object' | 'array' kept as is
        };
        const properties: Record<string, any> = {};
        Object.keys(rawProperties).forEach((k) => {
          const rawDef = (rawProperties as any)[k];
          const def = rawDef ? { ...rawDef } : {};
          const nt = normalizeType(def.type);
          if (typeof nt === 'object' && nt && 'type' in nt) {
            properties[k] = { ...def, ...nt };
          } else {
            properties[k] = { ...def, type: nt || 'string' };
          }
        });
        try {
          const keys = Object.keys(properties);
          console.log('[MCP][Params] parsed property keys:', keys);
          console.log('[MCP][Params] raw required list:', rawRequired);
          if ((callable?.name || '').toLowerCase() === 'mouse_click') {
            console.log('[MCP][Params][mouse_click] expecting keys: loc, post_move_delay, post_click_delay');
            console.log('[MCP][Params][mouse_click] actual keys:', keys);
          }
        } catch {}
        // Alias mismatched keys from backend (e.g., mouse_scroll: required 'amount' but property named 'duration')
        try {
          const name = callable?.name || '';
          const needsAmountAlias = rawRequired.includes('amount') && !('amount' in properties) && ('duration' in properties);
          if (needsAmountAlias && /scroll/i.test(name)) {
            properties['amount'] = { ...properties['duration'] };
            delete properties['duration'];
            console.log('[MCP] Aliased duration -> amount for scroll tool');
          }
        } catch {}

        // Guard required keys to only those present in properties
        const required = rawRequired.filter((k) => k in properties);
        // Update inputs schema used by FormInputs
        const nextInputs = {
          type: 'object',
          properties,
          required,
        } as any;
        form.setFieldValue('inputs', nextInputs); // consumed by <FormInputs />
        form.setFieldValue('data.inputs', nextInputs); // keep mirrored for default formatters
        try { console.log('[MCP] Applied tool params schema to inputs:', nextInputs); } catch {}
        // Prefill missing inputsValues keys for required fields with empty FlowValue
        const currentInputsValues = { ...(((formValues as any)?.data?.inputsValues) || {}) };
        required.forEach((k) => {
          if (!(k in currentInputsValues)) {
            currentInputsValues[k] = { type: 'constant', content: '' } as any;
          }
        });
        form.setFieldValue('data.inputsValues', currentInputsValues);
        try { console.log('[MCP] Prefilled inputsValues(required):', currentInputsValues); } catch {}
      } catch {}
    }],
  } as any,
  plugins: [
    createInferInputsPlugin({ sourceKey: 'inputsValues', targetKey: 'inputs' }),
  ],
};
