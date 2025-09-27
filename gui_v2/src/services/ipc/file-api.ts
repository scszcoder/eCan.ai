/**
 * File operation API extensions for IPC
 * Platform-aware file dialog and file I/O operations
 */

import { IPCAPI, APIResponse } from './api';

/**
 * File dialog filter interface
 */
export interface FileFilter {
  name: string;
  extensions: string[];
}

/**
 * File dialog response interface
 */
export interface FileDialogResponse {
  filePath?: string;
  fileName?: string;
  cancelled?: boolean;
}

/**
 * File content response interface
 */
export interface FileContentResponse {
  content: string;
  filePath: string;
  fileName: string;
  fileSize: number;
}

/**
 * File write response interface
 */
export interface FileWriteResponse {
  filePath: string;
  fileName: string;
  fileSize: number;
  success: boolean;
}

/**
 * Extend IPCAPI with file operation methods
 */
declare module './api' {
  interface IPCAPI {
    showOpenDialog<T = FileDialogResponse>(filters?: FileFilter[]): Promise<APIResponse<T>>;
    showSaveDialog<T = FileDialogResponse>(defaultFilename?: string, filters?: FileFilter[]): Promise<APIResponse<T>>;
    readSkillFile<T = FileContentResponse>(filePath: string): Promise<APIResponse<T>>;
    writeSkillFile<T = FileWriteResponse>(filePath: string, content: string): Promise<APIResponse<T>>;
  }
}

// Extend the IPCAPI prototype with file operation methods
IPCAPI.prototype.showOpenDialog = function<T = FileDialogResponse>(filters?: FileFilter[]): Promise<APIResponse<T>> {
  return this.executeRequest<T>('show_open_dialog', { filters });
};

IPCAPI.prototype.showSaveDialog = function<T = FileDialogResponse>(
  defaultFilename?: string, 
  filters?: FileFilter[]
): Promise<APIResponse<T>> {
  return this.executeRequest<T>('show_save_dialog', { defaultFilename, filters });
};

IPCAPI.prototype.readSkillFile = function<T = FileContentResponse>(filePath: string): Promise<APIResponse<T>> {
  return this.executeRequest<T>('read_skill_file', { filePath });
};

IPCAPI.prototype.writeSkillFile = function<T = FileWriteResponse>(
  filePath: string, 
  content: string
): Promise<APIResponse<T>> {
  return this.executeRequest<T>('write_skill_file', { filePath, content });
};

export { IPCAPI };
