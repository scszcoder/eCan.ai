import React, { useState, useCallback } from 'react';
import { useClientContext, usePlayground } from '@flowgram.ai/free-layout-editor';
import { Button, Tooltip, Toast } from '@douyinfe/semi-ui';
import { IconTerminal } from '@douyinfe/semi-icons';
import { CodeOutlined } from '@ant-design/icons';

import { useCodeEditor } from '../code-editor';

const TOOLTIP_CONTENT = 'Edit JSON Data';
const JSON_PARSE_ERROR_MESSAGE = 'Invalid JSON format. Please check your input.';

interface DocumentData {
  [key: string]: any;
}

/**
 * Console component that allows editing document data in JSON format
 * @returns JSX.Element
 */
export const Console = () => {
  const ctx = useClientContext();
  const playground = usePlayground();

  const handleSave = useCallback((content: string) => {
    try {
      const data = JSON.parse(content) as DocumentData;
      ctx.document.clear();
      ctx.document.fromJSON(data);
      return true;
    } catch (error) {
      Toast.error(JSON_PARSE_ERROR_MESSAGE);
      console.error('Failed to apply JSON:', error);
      return false;
    }
  }, [ctx.document]);

  const { openEditor, editor } = useCodeEditor({
    initialContent: '',
    language: 'json',
    onSave: handleSave,
  });

  const handleOpenConsole = useCallback(async () => {
    try {
      const jsonData = JSON.stringify(ctx.document.toJSON(), null, 2);
      openEditor(jsonData);
    } catch (error) {
      console.error('Failed to stringify document:', error);
      Toast.error('Failed to open console');
    }
  }, [ctx.document, openEditor]);

  return (
    <>
      <Tooltip content={TOOLTIP_CONTENT}>
        <Button
          disabled={playground.config.readonly}
          type="tertiary"
          icon={<IconTerminal />}
          theme="borderless"
          onClick={handleOpenConsole}
        />
      </Tooltip>
      {editor}
    </>
  );
};
