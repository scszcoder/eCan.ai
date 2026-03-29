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
import { useTranslation } from 'react-i18next';

import { useNodeRenderContext } from '../../../hooks';
import { useConditionPortOrderStore } from '../../../stores/condition-port-order-store';
import { getConditionType, getOrderedConditions } from '../port-order';
// No port rendering here; ports are handled by engine via node meta defaultPorts

interface ConditionValue {
  key: string;
  value?: ConditionRowValueType;
}

export function ConditionInputs() {
  const { t } = useTranslation('skillEditor');
  const { readonly, node } = useNodeRenderContext();
  const preferredPortOrder = useConditionPortOrderStore((state) => state.getPortOrder(node.id));

  const handleValueChange = useCallback((field: any, value: ConditionValue, newValue: any) => {
    const newValues = [...(field.value || [])];
    const targetIndex = newValues.findIndex(item => item.key === value.key);
    if (targetIndex !== -1) {
      newValues[targetIndex] = { ...newValues[targetIndex], value: newValue };
      field.onChange(getOrderedConditions(newValues));
    }
  }, []);

  return (
    <FieldArray<ConditionValue> name="conditions">
      {({ field }) => {
        // Sort conditions to ensure proper order
        const sortedValues = getOrderedConditions(field.value || [], preferredPortOrder);

        return (
          <>
            {sortedValues.map((value, index) => {
              const conditionType = getConditionType(value.key);
              const displayType = conditionType === 'elif' ? 'elsif' : conditionType;
              const isElse = conditionType === 'else';
              const isIf = conditionType === 'if';
              
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
                            <div style={{ flex: 1, color: 'var(--semi-color-text-2)' }}>{t('nodes.condition.elseBranch')}</div>
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
                              { label: t('nodes.condition.modes.stateCondition'), value: 'state.condition' },
                              { label: t('nodes.condition.modes.custom'), value: 'custom' },
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
                              placeholder={t('nodes.condition.conditionPlaceholder')}
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
                              field.onChange(getOrderedConditions(newValue));
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
                    
                    field.onChange(getOrderedConditions(newValue));
                  }}
                >
                  {t('nodes.condition.addElsif')}
                </Button>
              </div>
            )}
          </>
        );
      }}
    </FieldArray>
  );
}
