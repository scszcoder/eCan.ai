/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FormMeta, ValidateTrigger, Field } from '@flowgram.ai/free-layout-editor';
import React from 'react';
import i18n from '../../../../i18n';
import { useNodeRenderContext } from '../../hooks';
import { autoRenameRefEffect } from '@flowgram.ai/form-materials';

import { FlowNodeJSON } from '../../typings';
import { FormHeader, FormContent } from '../../form-components';
import { ConditionInputs } from './condition-inputs';
import { useNodeFlipStore } from '../../stores/node-flip-store';
import { useConditionPortOrderStore } from '../../stores/condition-port-order-store';
import { getOrderedConditions } from './port-order';

// Constants for port positioning
const HEADER_HEIGHT = 40;  // Height of FormHeader
const ROW_HEIGHT = 48;     // Height of each condition row when expanded
const COLLAPSED_ROW_HEIGHT = 28; // Height of each port row when collapsed
const FIRST_ROW_OFFSET = 20; // Offset for first row from header

interface ConditionValue {
  key: string;
  value?: any;
}

/**
 * Dynamic output port markers for Condition Node.
 * Renders one port per condition (if, elsif, else) with dynamic positioning.
 */
const ConditionPortMarkers: React.FC<{ expanded: boolean }> = ({ expanded }) => {
  const { node } = useNodeRenderContext();
  const { isFlipped } = useNodeFlipStore();
  const preferredPortOrder = useConditionPortOrderStore((state) => state.getPortOrder(node.id));
  const hFlip = isFlipped(node.id);
  
  // Calculate port vertical position based on index and expanded state
  const getPortTop = (index: number): number => {
    if (expanded) {
      // Align with form rows when expanded
      return HEADER_HEIGHT + FIRST_ROW_OFFSET + (index * ROW_HEIGHT) + (ROW_HEIGHT / 2) - 6;
    }
    // Compact layout when collapsed
    return HEADER_HEIGHT + FIRST_ROW_OFFSET + (index * COLLAPSED_ROW_HEIGHT);
  };
  
  // Port style with dynamic positioning
  const getPortStyle = (index: number): React.CSSProperties => ({
    position: 'absolute',
    top: getPortTop(index),
    ...(hFlip 
      ? { left: -10, right: 'auto', transform: 'translate(0, -50%) rotate(180deg)' } 
      : { right: -10, left: 'auto', transform: 'translate(0, -50%)' }
    ),
    width: 20,
    height: 20,
    zIndex: 250 + index,
    pointerEvents: 'auto',
    cursor: 'crosshair',
  });

  // Get display label for condition type
  const getDisplayType = (index: number, total: number): string => {
    if (index === 0) return 'if';
    if (index === total - 1 && total > 1) return 'else';
    return 'elsif';
  };
  
  return (
    <Field<ConditionValue[]> name="conditions">
      {({ field }) => {
        const conditions = getOrderedConditions(field.value || [], preferredPortOrder);
        
        return (
          <div className="se-condition-ports" style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'visible' }}>
            {conditions.map((condition, index) => (
              <div
                key={condition.key}
                className="se-cond-port"
                data-port-id={condition.key}
                data-port-key={condition.key}
                data-port-type="output"
                data-port-location={hFlip ? 'left' : 'right'}
                data-port-direction="output"
                data-port-group="conditions"
                data-port="true"
                style={getPortStyle(index)}
                title={getDisplayType(index, conditions.length)}
              />
            ))}
          </div>
        );
      }}
    </Field>
  );
};

// Main render function
export const renderForm = (_props: FormRenderProps<FlowNodeJSON>) => {
  const { expanded } = useNodeRenderContext();
  
  return (
    <>
      <FormHeader />
      <FormContent>
        <ConditionInputs />
      </FormContent>
      {/* Port markers rendered OUTSIDE FormContent so they're visible when collapsed */}
      <ConditionPortMarkers expanded={expanded} />
    </>
  );
};

export const formMeta: FormMeta<FlowNodeJSON> = {
  render: renderForm,
  validateTrigger: ValidateTrigger.onChange,
  validate: {
    title: ({ value }: { value: string }) => (value ? undefined : i18n.t('nodes.common.titleRequired', { ns: 'skillEditor' })),
    'conditions.*': ({ value }) => {
      const key: string | undefined = value?.key;
      const isElse = typeof key === 'string' && key.startsWith('else_');
      if (isElse) return undefined;
      if (!value?.value) return i18n.t('nodes.condition.conditionRequired', { ns: 'skillEditor' });
      return undefined;
    },
  },
  effect: {
    conditions: autoRenameRefEffect,
  },
};
