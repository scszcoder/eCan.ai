import { useCallback } from 'react';
import { useClientContext } from '@flowgram.ai/free-layout-editor';

import { Tooltip, IconButton } from '@douyinfe/semi-ui';
import { IconSave } from '@douyinfe/semi-icons';
import { useUserStore } from '../../../../stores/userStore';
import { useSkillInfoStore } from '../../stores/skill-info-store';
import { get_ipc_api } from '@/services/ipc_api';
import { SkillInfo } from '../../typings/skill-info';
import { hasIPCSupport, hasFullFilePaths } from '../../../../config/platform';
import '../../../../services/ipc/file-api'; // Import file API extensions
import { useRecentFilesStore, createRecentFile } from '../../stores/recent-files-store';
import { useSheetsStore } from '../../stores/sheets-store';
import { saveSheetsBundleToPath } from '../../services/sheets-persistence';
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

export async function saveFile(dataToSave: SkillInfo, username?: string, currentFilePath?: string | null) {
  try {
    console.log('--- Debug Save: Data to Save ---', dataToSave);
    const jsonString = JSON.stringify(dataToSave, null, 2);
    console.log('--- Debug Save: Final JSON String ---', jsonString);

    if (ENABLE_LOCAL_DOWNLOAD) {
      if (hasIPCSupport() && hasFullFilePaths()) {
        // Desktop mode: Use IPC backend for full file path support
        const { IPCAPI } = await import('../../../../services/ipc/api');
        const ipcApi = IPCAPI.getInstance();
        
        let filePath = currentFilePath;
        
        if (!filePath) {
          // Show save dialog if no current file path
          const fileName = (dataToSave.skillName || 'skill-info') + '.json';
          const dialogResponse = await ipcApi.showSaveDialog(fileName, [
            { name: 'Skill Files', extensions: ['json'] },
            { name: 'All Files', extensions: ['*'] }
          ]);
          
          if (dialogResponse.success && dialogResponse.data && !dialogResponse.data.cancelled) {
            filePath = dialogResponse.data.filePath;
          } else {
            console.log('Save operation was cancelled by user');
            return { cancelled: true };
          }
        }
        
        if (filePath) {
          // Write file through IPC
          const writeResponse = await ipcApi.writeSkillFile(filePath, jsonString);
          
          if (writeResponse.success) {
            console.log('File saved successfully:', filePath);
            return { success: true, filePath };
          } else {
            console.error('Failed to write file:', writeResponse.error);
            throw new Error(writeResponse.error || 'Failed to write file');
          }
        }
      } else {
        // Web mode: Use browser File System Access API or fallback
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
          return { success: true };
        } catch (e) {
          // Fallback to download
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
          return { success: true };
        }
      }
    }
    
    // Also save to backend if username is provided
    if (username) {
      await get_ipc_api().saveSkill(username, dataToSave);
    }
    
    return { success: true };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      console.log('Save operation was cancelled by user');
      return { cancelled: true };
    } else {
      console.error('Failed to save workflow:', error);
      throw error;
    }
  }
}

export const Save = ({ disabled }: SaveProps) => {
  const { document } = useClientContext();
  const skillInfo = useSkillInfoStore((state) => state.skillInfo);
  const setSkillInfo = useSkillInfoStore((state) => state.setSkillInfo);
  const breakpoints = useSkillInfoStore((state) => state.breakpoints);
  const currentFilePath = useSkillInfoStore((state) => state.currentFilePath);
  const setCurrentFilePath = useSkillInfoStore((state) => state.setCurrentFilePath);
  const setHasUnsavedChanges = useSkillInfoStore((state) => state.setHasUnsavedChanges);
  const addRecentFile = useRecentFilesStore((state) => state.addRecentFile);
  const username = useUserStore((state) => state.username);
  const getAllSheets = useSheetsStore((s) => s.getAllSheets);
  const saveActiveSheetDoc = useSheetsStore((s) => s.saveActiveDocument);

  const handleSave = useCallback(async () => {
    if (!skillInfo) return;

    try {
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

      // 4. Save the file with platform-aware handling
      const saveResult = await saveFile(updatedSkillInfo, username || undefined, currentFilePath);

      if (saveResult && !saveResult.cancelled) {
        // Update the skill info store
        setSkillInfo(updatedSkillInfo);
        setHasUnsavedChanges(false);

        // Update file path if we got a new one (from Save As dialog)
        if (saveResult.filePath && saveResult.filePath !== currentFilePath) {
          setCurrentFilePath(saveResult.filePath);
        }

        // Add to recent files when saving (update last opened time)
        const finalFilePath = saveResult.filePath || currentFilePath;
        if (finalFilePath) {
          addRecentFile(createRecentFile(finalFilePath, updatedSkillInfo.skillName));
        }

        console.log('Skill saved successfully');

        // Also persist the multi-sheet bundle alongside the skill JSON
        try {
          // Persist current canvas into the active sheet before bundling
          saveActiveSheetDoc(diagram);
          const bundle = getAllSheets();
          // Derive bundle path/name: same folder, -bundle suffix
          let bundleTarget = 'skill-bundle.json';
          if (finalFilePath) {
            const idx = finalFilePath.lastIndexOf('.json');
            if (idx !== -1) {
              bundleTarget = `${finalFilePath.slice(0, idx)}-bundle.json`;
            } else {
              bundleTarget = `${finalFilePath}-bundle.json`;
            }
          } else if (updatedSkillInfo.skillName) {
            bundleTarget = `${updatedSkillInfo.skillName}-bundle.json`;
          }
          await saveSheetsBundleToPath(bundleTarget, bundle);
          console.log('Multi-sheet bundle saved:', bundleTarget);
        } catch (e) {
          console.warn('Bundle save failed (non-fatal):', (e as Error).message);
        }
      }
    } catch (error) {
      console.error('Failed to save skill:', error);
      // TODO: Show user-friendly error message
    }
  }, [skillInfo, username, document, breakpoints, currentFilePath, setSkillInfo, setCurrentFilePath, setHasUnsavedChanges]);

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
