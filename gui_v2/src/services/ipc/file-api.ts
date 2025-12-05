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
 * Skill scaffold response interface
 */
export interface SkillScaffoldResponse {
  skillRoot: string;    // Path to the skill root directory (e.g., my_skills/xxx_skill/)
  name: string;         // Skill base name (without _skill suffix)
  diagramPath: string;  // Full path to the diagram JSON file (e.g., my_skills/xxx_skill/diagram_dir/xxx_skill.json)
}

/**
 * Skill copy response interface
 */
export interface SkillCopyResponse {
  skillRoot: string;    // Path to the new skill root directory
  name: string;         // New skill base name (without _skill suffix)
  diagramPath: string;  // Full path to the new diagram JSON file
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
    /**
     * Scaffold a new skill with standard directory structure
     * Creates: my_skills/<name>_skill/diagram_dir/<name>_skill.json + <name>_skill_bundle.json
     * @param name - Skill base name (without _skill suffix)
     * @param description - Optional skill description
     * @param kind - 'diagram' (default) or 'code'
     * @param skillJson - Optional skill JSON content (for diagram type)
     * @param bundleJson - Optional bundle JSON content (for diagram type)
     */
    scaffoldSkill<T = SkillScaffoldResponse>(
      name: string,
      description?: string,
      kind?: 'diagram' | 'code',
      skillJson?: any,
      bundleJson?: any
    ): Promise<APIResponse<T>>;
    /**
     * Copy entire skill directory to a new location with a new name (Save As)
     * @param sourcePath - Current skill file path
     * @param newName - New skill base name (without _skill suffix)
     * @param skillJson - Updated skill JSON content
     * @param bundleJson - Updated bundle JSON content
     * @param targetDir - Optional target directory (defaults to my_skills/)
     */
    copySkillTo<T = SkillCopyResponse>(
      sourcePath: string,
      newName: string,
      skillJson?: any,
      bundleJson?: any,
      targetDir?: string
    ): Promise<APIResponse<T>>;
    /**
     * Check if a skill with the given name already exists
     * @param name - Skill base name (without _skill suffix)
     */
    checkSkillExists(name: string): Promise<APIResponse<{ exists: boolean; name: string }>>;
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
  console.log('[FileAPI] readSkillFile: sending request', { filePath });
  const p = this.executeRequest<T>('read_skill_file', { filePath });
  p.then((resp) => {
    try {
      const data: any = resp?.data as any;
      console.log('[FileAPI] readSkillFile: response', {
        success: resp?.success,
        filePath: data?.filePath,
        fileName: data?.fileName,
        fileSize: data?.fileSize,
        contentPreview: typeof data?.content === 'string' ? data.content.slice(0, 120) : undefined,
      });
    } catch (e) {
      console.warn('[FileAPI] readSkillFile: log parse error', e);
    }
  }).catch((err) => {
    console.error('[FileAPI] readSkillFile: request error', err);
  });
  return p;
};

IPCAPI.prototype.writeSkillFile = function<T = FileWriteResponse>(
  filePath: string, 
  content: string
): Promise<APIResponse<T>> {
  return this.executeRequest<T>('write_skill_file', { filePath, content });
};

IPCAPI.prototype.scaffoldSkill = function<T = SkillScaffoldResponse>(
  name: string,
  description?: string,
  kind: 'diagram' | 'code' = 'diagram',
  skillJson?: any,
  bundleJson?: any
): Promise<APIResponse<T>> {
  console.log('[FileAPI] scaffoldSkill: creating skill structure', { name, description, kind });
  return this.executeRequest<T>('skills.scaffold', { name, description, kind, skillJson, bundleJson });
};

IPCAPI.prototype.copySkillTo = function<T = SkillCopyResponse>(
  sourcePath: string,
  newName: string,
  skillJson?: any,
  bundleJson?: any,
  targetDir?: string
): Promise<APIResponse<T>> {
  console.log('[FileAPI] copySkillTo: copying skill to new location', { sourcePath, newName, targetDir });
  return this.executeRequest<T>('skills.copyTo', { sourcePath, newName, skillJson, bundleJson, targetDir });
};

IPCAPI.prototype.checkSkillExists = function(
  name: string
): Promise<APIResponse<{ exists: boolean; name: string }>> {
  console.log('[FileAPI] checkSkillExists: checking if skill exists', { name });
  return this.executeRequest<{ exists: boolean; name: string }>('skills.scaffold', { name, checkOnly: true });
};

export { IPCAPI };
