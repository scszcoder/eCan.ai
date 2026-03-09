/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { Field } from '@flowgram.ai/free-layout-editor';
import { DisplayOutputs, IJsonSchema, JsonSchemaEditor } from '@flowgram.ai/form-materials';
import { Divider } from '@douyinfe/semi-ui';
import { useTranslation } from 'react-i18next';

import { useIsSidebar, useNodeRenderContext } from '../../../hooks';
import { FormItem } from '../../../form-components';

export function Outputs() {
  const { t } = useTranslation('skillEditor');
  const { readonly } = useNodeRenderContext();
  const isSidebar = useIsSidebar();

  if (!isSidebar) {
    return (
      <>
        <Divider />
        <Field<IJsonSchema> name="outputs">
          {({ field }) => <DisplayOutputs value={field.value} />}
        </Field>
      </>
    );
  }

  return (
    <>
      <Divider />
      <FormItem name="outputs" label={t('nodeState.fields.outputs')} type="object" vertical>
        <Field<IJsonSchema> name="outputs">
          {({ field }) => (
            <JsonSchemaEditor
              readonly={readonly}
              value={field.value}
              onChange={(value) => field.onChange(value)}
            />
          )}
        </Field>
      </FormItem>
    </>
  );
}
