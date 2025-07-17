/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useLayoutEffect } from 'react';

import { nanoid } from 'nanoid';
import { Field, FieldArray, WorkflowNodePortsData } from '@flowgram.ai/free-layout-editor';
import { ConditionRow, ConditionRowValueType } from '@flowgram.ai/form-materials';
import { Button } from '@douyinfe/semi-ui';
import { IconPlus, IconCrossCircleStroked } from '@douyinfe/semi-icons';
import { useCallback } from 'react';

import { useNodeRenderContext } from '../../../hooks';
import { FormItem, Feedback } from '../../../form-components';
import { ConditionPort } from './styles';

interface ConditionValue {
  key: string;
  value?: ConditionRowValueType;
}

type ConditionType = 'if' | 'elif' | 'else';

const getConditionType = (key: string): ConditionType => {
  if (key.startsWith('if_')) return 'if';
  if (key.startsWith('elif_')) return 'elif';
  if (key.startsWith('else_')) return 'else';
  return 'elif'; // default to elif for backward compatibility
};

const sortConditions = (conditions: ConditionValue[]): ConditionValue[] => {
  // Create a map to preserve existing values
  const valueMap = new Map(conditions.map(condition => [condition.key, condition.value]));
  
  // Sort the conditions
  const sorted = [...conditions].sort((a, b) => {
    const typeA = getConditionType(a.key);
    const typeB = getConditionType(b.key);
    if (typeA === 'if') return -1;
    if (typeB === 'if') return 1;
    if (typeA === 'else') return 1;
    if (typeB === 'else') return -1;
    return 0;
  });

  // Restore the values from the map
  return sorted.map(condition => ({
    key: condition.key,
    value: valueMap.get(condition.key)
  }));
};

export function ConditionInputs() {
  const { node, readonly } = useNodeRenderContext();

  useLayoutEffect(() => {
    window.requestAnimationFrame(() => {
      node.getData<WorkflowNodePortsData>(WorkflowNodePortsData).updateDynamicPorts();
    });
  }, [node]);

  const handleValueChange = useCallback((field: any, value: ConditionValue, newValue: any) => {
    const newValues = [...(field.value || [])];
    const targetIndex = newValues.findIndex(item => item.key === value.key);
    if (targetIndex !== -1) {
      newValues[targetIndex] = { ...newValues[targetIndex], value: newValue };
      field.onChange(sortConditions(newValues));
    }
  }, []);

  return (
    <FieldArray<ConditionValue> name="conditions">
      {({ field }) => {
        // Sort conditions to ensure proper order
        const sortedValues = sortConditions(field.value || []);

        return (
          <>
            {sortedValues.map((value, index) => {
              const conditionType = getConditionType(value.key);
              const isElse = conditionType === 'else';
              const isIf = conditionType === 'if';
              
              return (
                <div key={value.key}>
                  <FormItem name={conditionType} type="boolean" required={true} labelWidth={60}>
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                      <ConditionRow
                        readonly={readonly || isElse}
                        style={{ flexGrow: 1 }}
                        value={value.value}
                        onChange={(v) => handleValueChange(field, value, v)}
                      />
                      <Button
                        theme="borderless"
                        icon={<IconCrossCircleStroked />}
                        onClick={() => {
                          if (field.value) {
                            const newValue = field.value.filter(v => v.key !== value.key);
                            field.onChange(sortConditions(newValue));
                          }
                        }}
                        disabled={isIf || isElse}
                      />
                    </div>
                    <ConditionPort data-port-id={value.key} data-port-type="output" />
                  </FormItem>
                </div>
              );
            })}
            {!readonly && (
              <div>
                <Button
                  theme="borderless"
                  icon={<IconPlus />}
                  onClick={() => {
                    // Find the index of the else condition
                    const elseIndex = field.value?.findIndex(v => v.key.startsWith('else_')) ?? -1;
                    const insertIndex = elseIndex === -1 ? field.value?.length ?? 0 : elseIndex;
                    
                    // Insert the new elif condition before else
                    const newValue = [...(field.value || [])];
                    newValue.splice(insertIndex, 0, {
                      key: `elif_${nanoid(6)}`,
                      value: {}
                    });
                    
                    field.onChange(sortConditions(newValue));
                  }}
                >
                  Add
                </Button>
              </div>
            )}
          </>
        );
      }}
    </FieldArray>
  );
}
