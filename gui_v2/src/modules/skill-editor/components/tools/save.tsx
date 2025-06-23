import { useCallback } from 'react';

import { useClientContext, WorkflowJSON } from '@flowgram.ai/free-layout-editor';
import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconSave } from '@douyinfe/semi-icons';
import { useUserStore } from '../../../../stores/userStore';
import { APIResponse, IPCAPI } from '@/services/ipc/api';
// 添加 File System Access API 的类型定义
declare global {
  interface Window {
    showSaveFilePicker(options?: {
      suggestedName?: string;
      types?: Array<{
        description: string;
        accept: Record<string, string[]>;
      }>;
    }): Promise<FileSystemFileHandle>;
  }

  interface FileSystemFileHandle {
    createWritable(): Promise<FileSystemWritableFileStream>;
  }

  interface FileSystemWritableFileStream extends WritableStream {
    write(data: any): Promise<void>;
    close(): Promise<void>;
  }
}

interface SaveProps {
  disabled?: boolean;
}

export async function saveFile(workflow_json: WorkflowJSON, username?: string) {
  try {
    const jsonString = JSON.stringify(workflow_json, null, 2);
    const blob = new Blob([jsonString], { type: 'application/json' });
    const handle = await window.showSaveFilePicker({
      suggestedName: 'workflow.json',
      types: [{
        description: 'JSON Files',
        accept: { 'application/json': ['.json'] }
      }]
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    if (username) {
      await IPCAPI.getInstance().saveSkill(username, jsonString);
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      console.log('Save operation was cancelled by user');
    } else {
      console.error('Failed to save workflow:', error);
      // 如果 showSaveFilePicker 失败，回退到传统的下载方式
      try {
        const jsonString = JSON.stringify(workflow_json, null, 2);
        const blob = new Blob([jsonString], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = 'workflow.json';
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 100);
      } catch (fallbackError) {
        console.error('Fallback save also failed:', fallbackError);
      }
    }
  }
}

export const Save = ({ disabled }: SaveProps) => {
  const { document: workflowDocument } = useClientContext();
  const username = useUserStore((state) => state.username);

  const handleSave = useCallback(async () => {
    console.log('handleSave', workflowDocument, username);
    await saveFile(workflowDocument.toJSON(), username || undefined);
  }, [workflowDocument]);

  return (
    <Tooltip content="Save">
      <IconButton
        type="tertiary"
        theme="borderless"
        icon={<IconSave />}
        disabled={disabled}
        onClick={handleSave}
      />
    </Tooltip>
  );
};
