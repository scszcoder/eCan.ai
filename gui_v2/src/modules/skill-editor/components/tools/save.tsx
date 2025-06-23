import { useCallback } from 'react';

import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconSave } from '@douyinfe/semi-icons';
import { useUserStore } from '../../../../stores/userStore';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { get_ipc_api } from '@/services/ipc_api';
import { SkillInfo } from '../../typings/skill-info';
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

// 是否启用本地下载 SkillInfo 文件
const ENABLE_LOCAL_DOWNLOAD = true;

export async function saveFile(skillInfo: SkillInfo, username?: string) {
  try {
    const jsonString = JSON.stringify(skillInfo, null, 2);
    if (ENABLE_LOCAL_DOWNLOAD) {
      const blob = new Blob([jsonString], { type: 'application/json' });
      const fileName = (skillInfo.skillName || 'skill-info') + '.json';
      try {
        const handle = await window.showSaveFilePicker({
          suggestedName: fileName,
          types: [{
            description: 'JSON Files',
            accept: { 'application/json': ['.json'] }
          }]
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
      } catch (e) {
        // Fallback
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        }, 100);
      }
    }
    if (username) {
      await get_ipc_api().saveSkill(username, skillInfo);
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      console.log('Save operation was cancelled by user');
    } else {
      console.error('Failed to save workflow:', error);
      // fallback 已在主流程处理
    }
  }
}

export const Save = ({ disabled }: SaveProps) => {
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const username = useUserStore((state) => state.username);

  const handleSave = useCallback(async () => {
    if (!skillInfo) return;
    console.log('handleSave', skillInfo, username);
    await saveFile(skillInfo, username || undefined);
  }, [skillInfo, username]);

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
