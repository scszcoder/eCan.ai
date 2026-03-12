import React from 'react';
import { useTranslation } from 'react-i18next';

import { FlowNodeRegistry } from '@flowgram.ai/free-layout-editor';

import { useIsSidebar, useNodeRenderContext } from '../../hooks';
import { FormTitleDescription, FormWrapper } from './styles';

/**
 * @param props
 * @constructor
 */
export function FormContent(props: { children?: React.ReactNode }) {
  const { t } = useTranslation('skillEditor');
  const { node, expanded } = useNodeRenderContext();
  const isSidebar = useIsSidebar();
  const registry = node.getNodeRegistry<FlowNodeRegistry>();
  
  // Translate description if it's an i18n key
  const description = registry.info?.description;
  const translatedDescription = description?.startsWith('nodes.') ? t(description) : description;
  
  return (
    <FormWrapper>
      <>
        {isSidebar && <FormTitleDescription>{translatedDescription}</FormTitleDescription>}
        {(expanded || isSidebar) && props.children}
      </>
    </FormWrapper>
  );
}
