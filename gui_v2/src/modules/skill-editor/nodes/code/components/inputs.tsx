/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { Field } from '@flowgram.ai/free-layout-editor';
import { IFlowValue, InputsValues } from '@flowgram.ai/form-materials';

import { useNodeRenderContext } from '../../../hooks';
import { FormItem } from '../../../form-components';

export function Inputs() {
  const { readonly } = useNodeRenderContext();

  return (
    <FormItem name="inputs" type="object" vertical>
      <Field<Record<string, IFlowValue | undefined> | undefined> name="inputsValues">
        {({ field }) => (
          <InputsValues
            value={field.value}
            onChange={(value) => field.onChange(value)}
            readonly={readonly}
          />
        )}
      </Field>
    </FormItem>
  );
}
