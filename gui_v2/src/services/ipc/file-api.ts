/**
 * File operation API extensions for IPC
 * Platform-aware file dialog and file I/O operations
 */

import { IPCAPI, APIResponse } from './api';
import { apiRouter } from '../api/api-router';
import { GRAPHQL_QUERIES, GRAPHQL_MUTATIONS, Channel } from '../api/api-config';
import { detectPlatform } from '../../config/platform';
import { useUserStore } from '../../stores/userStore';
import { userStorageManager } from '../storage/UserStorageManager';
import { webAuthSession } from '../auth/webAuthSession';

/**
 * Get current username from store for API calls
 * This is the sanitized username (e.g., "user_gmail_com")
 */
function getCurrentUsername(): string | undefined {
  const fromStore = useUserStore.getState().username;
  if (fromStore) return fromStore;

  // After hard refresh, Zustand may be empty while sessionStorage still has userInfo.
  const fromWebSession = webAuthSession.getUserInfo()?.username;
  if (fromWebSession) return fromWebSession;

  const fromStorage = userStorageManager.getUserInfo()?.username;
  return fromStorage || undefined;
}

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
 * File write input interface
 */
export interface FileWriteInput {
  filePath: string;
  content: string;
}

/**
 * File write response interface
 */
export interface FileWriteResponse {
  filePath: string;
  fileName: string;
  fileSize: number;
  skillName?: string;
  updatedAt?: string;
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
 * Skill file list item interface
 */
export interface SkillFileItem {
  filePath: string;
  fileName?: string;
  fileSize?: number;
  skillName?: string;
  updatedAt?: string;
}

/**
 * Check skill exists response interface
 */
export interface CheckSkillExistsResponse {
  exists: boolean;
  name: string;
}

/**
 * Skill revision item interface
 */
export interface SkillRevisionItem {
  key: string;
  fileName: string;
  timestamp: string;
  size: number;
  lastModified: string;
}

/**
 * Skill revision revert result interface
 */
export interface SkillRevisionRevertResult {
  success: boolean;
  restoredFrom: string;
  restoredTo: string;
  size?: number;
}

/**
 * Extend IPCAPI with file operation methods
 */
declare module './api' {
  interface IPCAPI {
    showOpenDialog<T = FileDialogResponse>(filters?: FileFilter[]): Promise<APIResponse<T>>;
    showSaveDialog<T = FileDialogResponse>(defaultFilename?: string, filters?: FileFilter[]): Promise<APIResponse<T>>;
    readSkillFile<T = FileContentResponse>(filePath: string): Promise<APIResponse<T>>;
    openSkillFile<T = FileContentResponse>(filePath: string, skillName?: string): Promise<APIResponse<T>>;
    writeSkillFile<T = FileWriteResponse | FileWriteResponse[]>(input: FileWriteInput | FileWriteInput[]): Promise<APIResponse<T>>;
    listSkillFiles<T = SkillFileItem[]>(prefix?: string, limit?: number, nextToken?: string): Promise<APIResponse<T>>;
    checkSkillExists<T = CheckSkillExistsResponse>(name: string): Promise<APIResponse<T>>;
    /**
     * Scaffold a new skill with standard directory structure
     * Creates: my_skills/<name>_skill/diagram_dir/<name>_skill.json + <name>_skill_bundle.json + <name>_data_mapping.json
     * @param name - Skill base name (without _skill suffix)
     * @param description - Optional skill description
     * @param kind - 'diagram' (default) or 'code'
     * @param skillJson - Optional skill JSON content (for diagram type)
     * @param bundleJson - Optional bundle JSON content (for diagram type)
     * @param mappingJson - Optional mapping JSON content (for diagram type)
     */
    scaffoldSkill<T = SkillScaffoldResponse>(
      name: string,
      description?: string,
      kind?: 'diagram' | 'code',
      skillJson?: any,
      bundleJson?: any,
      mappingJson?: any
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
    /** List revision snapshots for a skill */
    listSkillRevisions<T = SkillRevisionItem[]>(skillName: string): Promise<APIResponse<T>>;
    /** Revert a skill file to a specific revision */
    revertSkillRevision<T = SkillRevisionRevertResult>(skillName: string, revisionKey: string): Promise<APIResponse<T>>;
  }
}

// Native file dialogs block on human input (browsing, typing a filename via
// IME) — the default 30s request timeout routinely fires while the dialog is
// still open, discarding the user's selection. Wait slightly longer than the
// backend's own dialog wait (600s in file_handler.py) so its timeout/cancel
// response reaches us instead of an abort.
const DIALOG_TIMEOUT_MS = 630_000;

// Extend the IPCAPI prototype with file operation methods
IPCAPI.prototype.showOpenDialog = function<T = FileDialogResponse>(filters?: FileFilter[]): Promise<APIResponse<T>> {
  return this.executeRequest<T>('show_open_dialog', { filters }, DIALOG_TIMEOUT_MS);
};

IPCAPI.prototype.showSaveDialog = function<T = FileDialogResponse>(
  defaultFilename?: string,
  filters?: FileFilter[]
): Promise<APIResponse<T>> {
  return this.executeRequest<T>('show_save_dialog', { defaultFilename, filters }, DIALOG_TIMEOUT_MS);
};

IPCAPI.prototype.readSkillFile = function<T = FileContentResponse>(filePath: string): Promise<APIResponse<T>> {
  console.log('[FileAPI] readSkillFile: sending request', { filePath });
  
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    const userId = getCurrentUsername();
    console.log('[FileAPI] readSkillFile: using GraphQL for web mode, userId:', userId);
    const p = apiRouter.execute<T>(
      {
        method: 'read_skill_file',
        graphql: {
          query: GRAPHQL_QUERIES.READ_SKILL_FILE,
          resultPath: 'readSkillFile'
        }
      },
      { filePath, userId }
    );
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
  }
  
  // In desktop mode, use IPC
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

IPCAPI.prototype.openSkillFile = function<T = FileContentResponse>(
  filePath: string,
  skillName?: string
): Promise<APIResponse<T>> {
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    const userId = getCurrentUsername();
    console.log('[FileAPI] openSkillFile: using GraphQL for web mode, userId:', userId);
    return apiRouter.execute<T>(
      {
        method: 'open_skill_file',
        graphql: {
          query: GRAPHQL_QUERIES.OPEN_SKILL_FILE,
          resultPath: 'openSkillFile'
        }
      },
      { filePath, skillName, userId }
    );
  }
  
  // In desktop mode, use IPC
  return this.executeRequest<T>('open_skill_file', { filePath, skillName });
};

IPCAPI.prototype.writeSkillFile = function<T = FileWriteResponse | FileWriteResponse[]>(
  input: FileWriteInput | FileWriteInput[]
): Promise<APIResponse<T>> {
  // Support both single file and batch write
  const payload = Array.isArray(input) ? input : [input];
  
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    // Add userId to each item in the payload for proper S3 path resolution
    const userId = getCurrentUsername();
    const payloadWithUserId = payload.map(item => ({ ...item, userId }));
    console.log('[FileAPI] writeSkillFile: using GraphQL for web mode', { fileCount: payload.length, userId });
    return apiRouter.execute<T>(
      {
        method: 'write_skill_file',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.WRITE_SKILL_FILE,
          resultPath: 'writeSkillFile'
        }
      },
      { input: payloadWithUserId }
    );
  }
  
  // In desktop mode, use IPC
  return this.executeRequest<T>('write_skill_file', { input: payload });
};

IPCAPI.prototype.listSkillFiles = function<T = SkillFileItem[]>(
  prefix?: string,
  limit?: number,
  nextToken?: string
): Promise<APIResponse<T>> {
  // In web mode, use GraphQL/AppSync directly via API router
  const platform = detectPlatform();
  if (platform === 'web') {
    const userId = getCurrentUsername();
    console.log('[FileAPI] listSkillFiles: using GraphQL for web mode, userId:', userId);
    return apiRouter.execute<T>(
      { 
        method: 'listSkillFiles', 
        graphql: { 
          query: GRAPHQL_QUERIES.LIST_SKILL_FILES,
          resultPath: 'listSkillFiles'
        } 
      },
      { prefix, limit, nextToken, userId }
    );
  }
  // In desktop mode, use IPC
  return this.executeRequest<T>('list_skill_files', { prefix, limit, nextToken });
};

IPCAPI.prototype.checkSkillExists = function<T = CheckSkillExistsResponse>(
  name: string
): Promise<APIResponse<T>> {
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    console.log('[FileAPI] checkSkillExists: using GraphQL for web mode', { name });
    return apiRouter.execute<T>(
      {
        method: 'check_skill_exists',
        graphql: {
          query: GRAPHQL_QUERIES.CHECK_SKILL_EXISTS,
          resultPath: 'checkSkillExists'
        }
      },
      { name }
    );
  }
  
  // In desktop mode, use IPC
  return this.executeRequest<T>('check_skill_exists', { name });
};

IPCAPI.prototype.scaffoldSkill = function<T = SkillScaffoldResponse>(
  name: string,
  description?: string,
  kind: 'diagram' | 'code' = 'diagram',
  skillJson?: any,
  bundleJson?: any,
  mappingJson?: any
): Promise<APIResponse<T>> {
  console.log('[FileAPI] scaffoldSkill: creating skill structure', { name, description, kind });
  
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    const userId = getCurrentUsername();
    console.log('[FileAPI] scaffoldSkill: using GraphQL for web mode, userId:', userId);
    return apiRouter.execute<T>(
      {
        method: 'skills.scaffold',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.SCAFFOLD_SKILL,
          resultPath: 'scaffoldSkill'
        }
      },
      { input: { name, description, kind, skillJson, bundleJson, mappingJson, userId } }
    );
  }
  
  // In desktop mode, use IPC
  return this.executeRequest<T>('skills.scaffold', { name, description, kind, skillJson, bundleJson, mappingJson });
};

IPCAPI.prototype.copySkillTo = function<T = SkillCopyResponse>(
  sourcePath: string,
  newName: string,
  skillJson?: any,
  bundleJson?: any,
  targetDir?: string
): Promise<APIResponse<T>> {
  console.log('[FileAPI] copySkillTo: copying skill to new location', { sourcePath, newName, targetDir });
  
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    const userId = getCurrentUsername();
    console.log('[FileAPI] copySkillTo: using GraphQL for web mode, userId:', userId);
    return apiRouter.execute<T>(
      {
        method: 'skills.copyTo',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.COPY_SKILL_TO,
          resultPath: 'copySkillTo'
        }
      },
      { input: { sourcePath, newName, skillJson, bundleJson, targetDir, userId } }
    );
  }
  
  // In desktop mode, use IPC
  return this.executeRequest<T>('skills.copyTo', { sourcePath, newName, skillJson, bundleJson, targetDir });
};

IPCAPI.prototype.checkSkillExists = function(
  name: string
): Promise<APIResponse<{ exists: boolean; name: string }>> {
  console.log('[FileAPI] checkSkillExists: checking if skill exists', { name });
  
  // In web mode, use GraphQL/AppSync via apiRouter
  const platform = detectPlatform();
  if (platform === 'web') {
    return apiRouter.execute<{ exists: boolean; name: string }>(
      {
        method: 'check_skill_exists',
        graphql: {
          query: GRAPHQL_QUERIES.CHECK_SKILL_EXISTS,
          resultPath: 'checkSkillExists'
        }
      },
      { name }
    );
  }
  
  // In desktop mode, use IPC with scaffold checkOnly flag
  return this.executeRequest<{ exists: boolean; name: string }>('skills.scaffold', { name, checkOnly: true });
};

IPCAPI.prototype.listSkillRevisions = function<T = SkillRevisionItem[]>(
  skillName: string
): Promise<APIResponse<T>> {
  const platform = detectPlatform();
  if (platform === 'web') {
    return apiRouter.execute<T>(
      {
        method: 'listSkillRevisions',
        graphql: {
          query: GRAPHQL_QUERIES.LIST_SKILL_REVISIONS,
          resultPath: 'listSkillRevisions'
        }
      },
      { input: { skillName } }
    );
  }
  return this.executeRequest<T>('skill.list_revisions', { skillName });
};

IPCAPI.prototype.revertSkillRevision = function<T = SkillRevisionRevertResult>(
  skillName: string,
  revisionKey: string
): Promise<APIResponse<T>> {
  const platform = detectPlatform();
  if (platform === 'web') {
    return apiRouter.execute<T>(
      {
        method: 'revertSkillRevision',
        graphql: {
          mutation: GRAPHQL_MUTATIONS.REVERT_SKILL_REVISION,
          resultPath: 'revertSkillRevision'
        }
      },
      { input: { skillName, revisionKey } }
    );
  }
  return this.executeRequest<T>('skill.revert_revision', { skillName, revisionKey });
};

export { IPCAPI };
