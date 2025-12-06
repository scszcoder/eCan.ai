/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { useCallback } from 'react';

import { nanoid } from 'nanoid';
import { FieldArray } from '@flowgram.ai/free-layout-editor';
import { ConditionRowValueType } from '@flowgram.ai/form-materials';
import { Button, Select, Input } from '@douyinfe/semi-ui';
import { IconPlus, IconCrossCircleStroked } from '@douyinfe/semi-icons';

import { useNodeRenderContext } from '../../../hooks';
// No port rendering here; ports are handled by engine via node meta defaultPorts

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
  const { readonly } = useNodeRenderContext();

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
        console.log('Conditions:', field.value, 'Sorted:', sortedValues);

        return (
          <>
            {sortedValues.map((value, index) => {
              // Enforce standard syntax: 
              // 1. First item is IF
              // 2. Last item is ELSE (if there's more than one item)
              // 3. Others are ELSIF
              const isFirst = index === 0;
              const isLast = index === sortedValues.length - 1;
              
              // We treat the last item as ELSE to ensure valid structure, unless it's the only item (IF)
              const treatAsElse = isLast && sortedValues.length > 1;
              
              const displayType = isFirst ? 'if' : (treatAsElse ? 'else' : 'elsif');
              const isElse = treatAsElse; 
              const isIf = isFirst;
              
              return (
                <div key={value.key} style={{ position: 'relative', width: '100%', maxWidth: '100%', overflow: 'visible' }}>
                  {/* Custom label display */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 12 }}>
                    <div style={{ width: 80, fontSize: 14, fontWeight: 500, color: 'var(--semi-color-text-0)', paddingTop: 8, flexShrink: 0 }}>
                      {displayType}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ width: '100%' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', maxWidth: '100%', paddingRight: 36, boxSizing: 'border-box', overflow: 'hidden' }}>
                          {isElse ? (
                            <div style={{ flex: 1, color: 'var(--semi-color-text-2)' }}>Else branch</div>
                          ) : (
                            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: '100%' }}>
                              {/* Mode selector */}
                              <Select
                            value={(value.value as any)?.mode || 'state.condition'}
                            onChange={(val) => {
                              const mode = String(val);
                              if (mode === 'state.condition') {
                                handleValueChange(field, value, {
                                  mode,
                                  // fixed check: state.condition is true
                                  left: { type: 'ref', content: ['state', 'condition'] },
                                  operator: 'is_true',
                                });
                              } else {
                                handleValueChange(field, value, { mode, expr: '' });
                              }
                            }}
                            optionList={[
                              { label: 'state.condition', value: 'state.condition' },
                              { label: 'custom expression', value: 'custom' },
                            ]}
                            disabled={readonly}
                            size="small"
                            style={{ width: '100%' }}
                            dropdownMatchSelectWidth
                          />
                          {/* Custom expression input */}
                          {((value.value as any)?.mode || 'state.condition') === 'custom' && (
                            <Input
                              value={(value.value as any)?.expr || ''}
                              onChange={(val) => handleValueChange(field, value, { ...(value.value as any), mode: 'custom', expr: val })}
                              placeholder={'Enter condition expression'}
                              disabled={readonly}
                              style={{ width: '100%' }}
                            />
                          )}
                        </div>
                      )}
                      {!readonly && !isElse && !(isIf && index === 0) && (
                        <Button
                          theme="borderless"
                          disabled={readonly}
                          icon={<IconCrossCircleStroked />}
                          size="small"
                          onClick={() => {
                            if (field.value) {
                              const newValue = field.value.filter(v => v.key !== value.key);
                              field.onChange(sortConditions(newValue));
                            }
                          }}
                        />
                      )}
                    </div>
                      </div>
                    </div>
                  </div>
                  {/* No inline port markers here; relying on form-meta port markers */}
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
                  Add elsif
                </Button>
              </div>
            )}
          </>
        );
      }}
    </FieldArray>
  );
}
