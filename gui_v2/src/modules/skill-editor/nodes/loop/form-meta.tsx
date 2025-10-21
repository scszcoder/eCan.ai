/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FlowNodeJSON, Field, FormMeta } from '@flowgram.ai/free-layout-editor';
import { SubCanvasRender } from '@flowgram.ai/free-container-plugin';
import {
  BatchOutputs,
  createBatchOutputsFormPlugin,
  DisplayOutputs,
  IFlowRefValue,
} from '@flowgram.ai/form-materials';

import { defaultFormMeta } from '../default-form-meta';
import { useIsSidebar, useNodeRenderContext } from '../../hooks';
import { FormHeader, FormContent, FormItem, Feedback } from '../../form-components';
import { Select, Input } from '@douyinfe/semi-ui';

interface LoopNodeJSON extends FlowNodeJSON {
  data: {
    loopFor: IFlowRefValue;
  };
}

export const LoopFormRender = ({}: FormRenderProps<LoopNodeJSON>) => {
  const isSidebar = useIsSidebar();
  const { readonly } = useNodeRenderContext();
  const formHeight = 85;

  // Loop mode + while expression row
  const loopModeAndExpr = (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      {/* Loop mode selector */}
      <FormItem name={'loopMode'} type={'string'} vertical>
        <Field<string> name={'loopMode'}>
          {({ field }) => (
            <Select
              value={field.value || 'loopFor'}
              onChange={(val) => field.onChange(val as string)}
              optionList={[
                { label: 'loopFor', value: 'loopFor' },
                { label: 'loopWhile', value: 'loopWhile' },
              ]}
              style={{ width: 160 }}
              size="small"
              disabled={readonly}
            />
          )}
        </Field>
      </FormItem>

      {/* While exit condition expression */}
      <FormItem name={'loopWhileExpr'} type={'string'} vertical>
        <Field<string> name={'loopWhileExpr'}>
          {({ field }) => (
            <Field<string> name={'loopMode'}>
              {({ field: modeField }) => (
                <Input
                  value={field.value || ''}
                  onChange={(val) => field.onChange(val)}
                  placeholder={modeField.value === 'loopWhile' ? 'Enter exit condition expression' : 'Exit condition (loopWhile)'}
                  disabled={readonly || modeField.value !== 'loopWhile'}
                  style={{ width: '100%' }}
                />
              )}
            </Field>
          )}
        </Field>
      </FormItem>
    </div>
  );

  const loopFor = (
    <Field<string> name={`loopCountExpr`}>
      {({ field, fieldState }) => (
        <FormItem name={'loopCountExpr'} type={'string'} required>
          <Input
            value={field.value || ''}
            onChange={(val) => field.onChange(val)}
            placeholder={'Enter loop count (number or expression)'}
            disabled={readonly}
            style={{ width: '100%' }}
          />
          <Feedback errors={fieldState?.errors} />
        </FormItem>
      )}
    </Field>
  );

  const loopOutputs = (
    <Field<Record<string, IFlowRefValue | undefined> | undefined> name={`loopOutputs`}>
      {({ field, fieldState }) => (
        <FormItem name="loopOutputs" type="object" vertical>
          <BatchOutputs
            style={{ width: '100%' }}
            value={field.value}
            onChange={(val) => field.onChange(val)}
            readonly={readonly}
            hasError={Object.keys(fieldState?.errors || {}).length > 0}
          />
          <Feedback errors={fieldState?.errors} />
        </FormItem>
      )}
    </Field>
  );

  if (isSidebar) {
    return (
      <>
        <FormHeader />
        <FormContent>
          {loopModeAndExpr}
          {/* Show loopFor selector only when loopMode is loopFor */}
          <Field<string> name={'loopMode'}>
            {({ field: modeField }) => (
              modeField.value === 'loopFor' ? loopFor : <></>
            )}
          </Field>
          {loopOutputs}
        </FormContent>
      </>
    );
  }
  return (
    <>
      <FormHeader />
      <FormContent>
        {loopModeAndExpr}
        <Field<string> name={'loopMode'}>
          {({ field: modeField }) => (
            modeField.value === 'loopFor' ? loopFor : <></>
          )}
        </Field>
        <SubCanvasRender offsetY={-formHeight} />
        <DisplayOutputs displayFromScope />
      </FormContent>
    </>
  );
};

export const formMeta: FormMeta = {
  ...defaultFormMeta,
  render: LoopFormRender,
  effect: {
    // loopFor array binding removed; loopCountExpr is a simple string now
  },
  plugins: [createBatchOutputsFormPlugin({ outputKey: 'loopOutputs' })],
};
