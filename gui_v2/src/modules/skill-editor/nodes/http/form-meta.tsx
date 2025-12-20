/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { Field, FormMeta, FormRenderProps } from '@flowgram.ai/free-layout-editor';
import { createInferInputsPlugin, DisplayOutputs, IJsonSchema, validateFlowValue } from '@flowgram.ai/form-materials';
import { Divider, Input } from '@douyinfe/semi-ui';
import styled from 'styled-components';

import { FormHeader, FormContent, FormItem } from '../../form-components';
import { HTTPNodeJSON } from './types';
import { Timeout } from './components/timeout';
import { Params } from './components/params';
import { Headers } from './components/headers';
import { Body } from './components/body';
import { Api } from './components/api';
import { defaultFormMeta } from '../default-form-meta';

// Wrapper to set min-width for HTTP node content when expanded
const HTTPFormContentWrapper = styled.div`
  min-width: 300px;
`;

export const FormRender = ({ form }: FormRenderProps<HTTPNodeJSON>) => (
  <>
    <FormHeader />
    <FormContent>
      <HTTPFormContentWrapper>
        <Api />
        <Divider />
        {/* API Key input */}
        <FormItem name="apiKey" type="string" vertical>
          <Field<string> name="inputsValues.apiKey">
            {({ field }) => (
              <Input
                value={field.value}
                onChange={(val) => field.onChange(val)}
                placeholder="Enter API Key"
                mode="password"
              />
            )}
          </Field>
        </FormItem>
        <Divider />
        <Headers />
        <Divider />
        <Params />
        <Divider />
        <Body />
        <Divider />
        <Timeout />
        <DisplayOutputs displayFromScope />
      </HTTPFormContentWrapper>
    </FormContent>
  </>
);

export const formMeta: FormMeta = {
  render: (props) => <FormRender {...props} />,
  validate: {
    // Override the default validation for api.url to do nothing.
    // This prevents the frontend from trying to fetch the URL.
    'api.url': () => undefined,
  },
  effect: defaultFormMeta.effect,
  plugins: [
    createInferInputsPlugin({ sourceKey: 'headersValues', targetKey: 'headers' }),
    createInferInputsPlugin({ sourceKey: 'paramsValues', targetKey: 'params' }),
  ],
};
