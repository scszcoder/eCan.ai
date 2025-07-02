/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FormRenderProps, FlowNodeJSON, Field } from '@flowgram.ai/free-layout-editor';
import { SubCanvasRender } from '@flowgram.ai/free-container-plugin';
import { BatchOutputs, BatchVariableSelector, IFlowRefValue } from '@flowgram.ai/form-materials';

import { useIsSidebar, useNodeRenderContext } from '../../hooks';
import { FormHeader, FormContent, FormOutputs, FormItem, Feedback } from '../../form-components';

interface LoopNodeJSON extends FlowNodeJSON {
  data: {
    batchFor: IFlowRefValue;
  };
}

export const LoopFormRender = ({ form }: FormRenderProps<LoopNodeJSON>) => {
  const isSidebar = useIsSidebar();
  const { readonly } = useNodeRenderContext();
  const formHeight = 85;

  const batchFor = (
    <Field<IFlowRefValue> name={`batchFor`}>
      {({ field, fieldState }) => (
        <FormItem name={'batchFor'} type={'array'} required>
          <BatchVariableSelector
            style={{ width: '100%' }}
            value={field.value?.content}
            onChange={(val) => field.onChange({ type: 'ref', content: val })}
            readonly={readonly}
            hasError={Object.keys(fieldState?.errors || {}).length > 0}
          />
          <Feedback errors={fieldState?.errors} />
        </FormItem>
      )}
    </Field>
  );

  const batchOutputs = (
    <Field<Record<string, IFlowRefValue | undefined> | undefined> name={`batchOutputs`}>
      {({ field, fieldState }) => (
        <FormItem name="batchOutputs" type="object" vertical>
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
          {batchFor}
          {batchOutputs}
          <FormOutputs />
        </FormContent>
      </>
    );
  }
  return (
    <>
      <FormHeader />
      <FormContent>
        {batchFor}
        <SubCanvasRender offsetY={-formHeight} />
        <FormOutputs />
      </FormContent>
    </>
  );
};
