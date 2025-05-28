import { useCallback } from 'react';

import { useClientContext, usePlayground } from '@flowgram.ai/free-layout-editor';
import { Button, Tooltip } from '@douyinfe/semi-ui';
import { IconTerminal } from '@douyinfe/semi-icons';

import { useModal } from '../../hooks/use-code-editor-modal';

export const Console = () => {
  const ctx = useClientContext();
  const playground = usePlayground();

  const handleOk = useCallback((content: string) => {
    try {
      const data = JSON.parse(content);
      ctx.document.clear();
      ctx.document.fromJSON(data);
      return true;
    } catch (error) {
      console.error('Failed to apply JSON:', error);
      return false;
    }
  }, [ctx.document]);

  const { openModal, modal } = useModal('', 'json', handleOk);

  const consoleJSON = useCallback(async () => {
    const jsonData = JSON.stringify(ctx.document.toJSON(), null, 2);
    openModal(jsonData);
  }, [ctx, openModal]);

  return (
    <>
      <Tooltip content={'Edit JSON Data'}>
        <Button
          disabled={playground.config.readonly}
          type="tertiary"
          icon={<IconTerminal />}
          theme="borderless"
          onClick={consoleJSON}
        />
      </Tooltip>
      {modal}
    </>
  );
};
