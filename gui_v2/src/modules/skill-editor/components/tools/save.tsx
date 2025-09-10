import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';

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

export async function saveFile(dataToSave: SkillInfo, username?: string) {
  try {
    console.log('--- Debug Save: Data to Save ---', dataToSave);
    const jsonString = JSON.stringify(dataToSave, null, 2);
    console.log('--- Debug Save: Final JSON String ---', jsonString);

    if (ENABLE_LOCAL_DOWNLOAD) {
      const blob = new Blob([jsonString], { type: 'application/json' });
      const fileName = (dataToSave.skillName || 'skill-info') + '.json';
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
      await get_ipc_api().saveSkill(username, dataToSave);
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
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const username = useUserStore((state) => state.username);

  const handleSave = useCallback(async () => {
    if (!skillInfo) return;

    // 1. Get the latest diagram state
    const diagram = document.toJSON();

    // 2. Inject breakpoint information into the diagram
    diagram.nodes.forEach((node: any) => {
      if (breakpoints.includes(node.id)) {
        if (!node.data) {
          node.data = {};
        }
        node.data.break_point = true;
      } else {
        // Ensure the flag is removed if the breakpoint was removed
        if (node.data?.break_point) {
          delete node.data.break_point;
        }
      }
    });

    // 3. Create the updated skillInfo object
    const updatedSkillInfo = {
      ...skillInfo,
      workFlow: diagram,
      lastModified: new Date().toISOString(),
    };

    // 4. Now, save the updated state to the file by passing it directly
    await saveFile(updatedSkillInfo, username || undefined);
  }, [skillInfo, username, document, breakpoints]);

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
