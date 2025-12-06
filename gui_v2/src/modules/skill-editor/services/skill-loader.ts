/**
 * Skill Loader Service
 * 
 * Unified entry point for loading skill files with automatic schema migration.
 * All file loading should go through this service to ensure:
 * 1. Consistent migration handling
 * 2. Automatic save after migration
 * 3. Proper schemaVersion tracking
 */

import { IPCAPI } from '../../../services/ipc/api';
import '../../../services/ipc/file-api';
import { SkillInfo } from '../typings/skill-info';
import { migrateDocument, migrateBundle, CURRENT_SCHEMA_VERSION } from './schema-migration';
import { normalizeBundle, looksLikeBundle, SheetsBundle } from '../utils/bundle-utils';

export interface SkillLoadResult {
  success: boolean;
  skillInfo?: SkillInfo;
  bundle?: SheetsBundle;
  filePath: string;
  bundlePath?: string;
  migrated: boolean;
  error?: string;
}

/**
 * Load a skill file with automatic migration
 * This is the unified entry point for all skill file loading
 */
export async function loadSkillFile(filePath: string): Promise<SkillLoadResult> {
  const ipcApi = IPCAPI.getInstance();
  
  try {
    console.log('[SkillLoader] Loading skill file:', filePath);
    
    // 1. Read the main skill file
    const fileResponse = await ipcApi.readSkillFile(filePath);
    if (!fileResponse.success || !fileResponse.data) {
      return {
        success: false,
        filePath,
        migrated: false,
        error: typeof fileResponse.error === 'string' ? fileResponse.error : 'Failed to read skill file',
      };
    }
    
    const skillInfo = JSON.parse(fileResponse.data.content) as SkillInfo;
    let migrated = false;
    let bundle: SheetsBundle | undefined;
    let bundlePath: string | undefined;
    
    // 1.5. Normalize skillName (remove _skill suffix, derive from folder if needed)
    try {
      const norm = String(filePath).replace(/\\/g, '/');
      const parts = norm.split('/');
      const diagramIdx = parts.lastIndexOf('diagram_dir');
      let nameFromFolder = '';
      if (diagramIdx > 0) {
        const folder = parts[diagramIdx - 1];
        nameFromFolder = folder?.replace(/_skill$/i, '') || '';
      }
      if (!nameFromFolder) {
        const fileName = parts[parts.length - 1] || '';
        nameFromFolder = fileName.replace(/\.json$/i, '').replace(/_skill$/i, '');
      }
      // Always use the normalized name from folder/filename
      if (nameFromFolder) {
        skillInfo.skillName = nameFromFolder;
      }
    } catch {
      // Keep original skillName if normalization fails
    }
    
    // 2. Try to load bundle file
    const idx = filePath.toLowerCase().lastIndexOf('.json');
    const base = idx !== -1 ? filePath.slice(0, idx) : filePath;
    const bundleCandidates = [`${base}_bundle.json`, `${base}-bundle.json`];
    
    for (const candidatePath of bundleCandidates) {
      try {
        const bundleResp = await ipcApi.readSkillFile(candidatePath);
        if (bundleResp.success && bundleResp.data) {
          const maybeBundle = JSON.parse(bundleResp.data.content);
          if (looksLikeBundle(maybeBundle)) {
            const normalizedBundle = normalizeBundle(maybeBundle);
            if (normalizedBundle) {
              bundle = normalizedBundle;
              bundlePath = candidatePath;
              console.log('[SkillLoader] Found bundle:', candidatePath, 'sheets:', bundle.sheets.length);
              break;
            }
          }
        }
      } catch {
        // Bundle file doesn't exist or failed to parse, continue
      }
    }
    
    // 3. Apply migration
    if (bundle) {
      // Migrate bundle (which migrates all sheet documents)
      const bundleMigrationResult = migrateBundle(bundle);
      migrated = bundleMigrationResult.migratedCount > 0;
      
      if (migrated) {
        console.log('[SkillLoader] Bundle migration applied:', bundleMigrationResult);
      } else {
        console.log('[SkillLoader] Bundle migration not applied:', bundleMigrationResult);
      }
    } else if (skillInfo.workFlow) {
      // Migrate single skill document
      // Pass skillInfo.schemaVersion to help determine if migration is needed
      const docMigrationResult = migrateDocument(skillInfo.workFlow, (skillInfo as any).schemaVersion);
      migrated = docMigrationResult.migrated;
      
      if (migrated) {
        console.log('[SkillLoader] Document migration applied:', docMigrationResult);
      } else {
        console.log('[SkillLoader] Document migration not applied:', docMigrationResult);
      }
    }
    
    // 4. Auto-save if migration was applied
    if (migrated) {
      console.log('[SkillLoader] Auto-saving migrated files...');
      
      // Update schemaVersion on skillInfo
      (skillInfo as any).schemaVersion = CURRENT_SCHEMA_VERSION;
      skillInfo.lastModified = new Date().toISOString();
      
      try {
        // Save main skill file
        await ipcApi.writeSkillFile(filePath, JSON.stringify(skillInfo, null, 2));
        console.log('[SkillLoader] Saved migrated skill file:', filePath);
        
        // Save bundle file if exists
        if (bundle && bundlePath) {
          (bundle as any).schemaVersion = CURRENT_SCHEMA_VERSION;
          await ipcApi.writeSkillFile(bundlePath, JSON.stringify(bundle, null, 2));
          console.log('[SkillLoader] Saved migrated bundle file:', bundlePath);
        }
      } catch (saveErr) {
        console.warn('[SkillLoader] Failed to auto-save migrated files:', saveErr);
        // Continue even if save fails - data is migrated in memory
      }
    }
    
    return {
      success: true,
      skillInfo,
      bundle,
      filePath,
      bundlePath,
      migrated,
    };
  } catch (error) {
    console.error('[SkillLoader] Error loading skill file:', error);
    return {
      success: false,
      filePath,
      migrated: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

/**
 * Load only bundle file with automatic migration
 * Used when bundle path is already known
 */
export async function loadBundleFile(bundlePath: string): Promise<{
  success: boolean;
  bundle?: SheetsBundle;
  migrated: boolean;
  error?: string;
}> {
  const ipcApi = IPCAPI.getInstance();
  
  try {
    console.log('[SkillLoader] Loading bundle file:', bundlePath);
    
    const bundleResp = await ipcApi.readSkillFile(bundlePath);
    if (!bundleResp.success || !bundleResp.data) {
      return {
        success: false,
        migrated: false,
        error: typeof bundleResp.error === 'string' ? bundleResp.error : 'Failed to read bundle file',
      };
    }
    
    const maybeBundle = JSON.parse(bundleResp.data.content);
    if (!looksLikeBundle(maybeBundle)) {
      return {
        success: false,
        migrated: false,
        error: 'File is not a valid bundle',
      };
    }
    
    const bundle = normalizeBundle(maybeBundle);
    if (!bundle) {
      return {
        success: false,
        migrated: false,
        error: 'Failed to normalize bundle',
      };
    }
    
    // Apply migration
    const migrationResult = migrateBundle(bundle);
    const migrated = migrationResult.migratedCount > 0;
    
    if (migrated) {
      console.log('[SkillLoader] Bundle migration applied:', migrationResult);
      
      // Auto-save
      try {
        (bundle as any).schemaVersion = CURRENT_SCHEMA_VERSION;
        await ipcApi.writeSkillFile(bundlePath, JSON.stringify(bundle, null, 2));
        console.log('[SkillLoader] Saved migrated bundle file:', bundlePath);
      } catch (saveErr) {
        console.warn('[SkillLoader] Failed to auto-save migrated bundle:', saveErr);
      }
    }
    
    return {
      success: true,
      bundle,
      migrated,
    };
  } catch (error) {
    console.error('[SkillLoader] Error loading bundle file:', error);
    return {
      success: false,
      migrated: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}
