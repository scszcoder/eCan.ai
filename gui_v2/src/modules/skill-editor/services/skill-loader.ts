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
import { sanitizeApiKeysDeep } from '../utils/sanitize-utils';

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
export async function loadSkillFile(
  filePath: string,
  options: {
    autoSaveMigrated?: boolean;
  } = {}
): Promise<SkillLoadResult> {
  const ipcApi = IPCAPI.getInstance();
  const autoSaveMigrated = options.autoSaveMigrated !== false;
  const nowIso = new Date().toISOString();
  
  try {
    console.log('[SkillLoader] Loading skill file:', filePath);
    
    // 1. Read the main skill file
    let fileResponse = await ipcApi.openSkillFile(filePath).catch((e: any) => {
      return {
        success: false,
        error: e?.message || String(e),
      } as any;
    });
    if (!fileResponse.success || !fileResponse.data) {
      // Fallback for older backends that don't implement open_skill_file yet
      const fallbackResp = await ipcApi.readSkillFile(filePath);
      if (!fallbackResp.success || !fallbackResp.data) {
        const err1 = typeof (fileResponse as any).error === 'string' ? (fileResponse as any).error : '';
        const err2 = typeof fallbackResp.error === 'string' ? fallbackResp.error : '';
        return {
          success: false,
          filePath,
          migrated: false,
          error: err2 || err1 || 'Failed to read skill file',
        };
      }
      fileResponse = fallbackResp as any;
    }
    
    const parsed = JSON.parse(fileResponse.data.content);
    let migrated = false;
    let bundle: SheetsBundle | undefined;
    let bundlePath: string | undefined;

    // Derive a stable skill name from file path (folder before diagram_dir or filename)
    let nameFromPath = '';
    try {
      const norm = String(filePath).replace(/\\/g, '/');
      const parts = norm.split('/');
      const diagramIdx = parts.lastIndexOf('diagram_dir');
      if (diagramIdx > 0) {
        const folder = parts[diagramIdx - 1];
        nameFromPath = folder?.replace(/_skill$/i, '') || '';
      }
      if (!nameFromPath) {
        const fileName = parts[parts.length - 1] || '';
        nameFromPath = fileName.replace(/\.json$/i, '').replace(/_skill$/i, '');
      }
    } catch {
      // ignore
    }

    // If the selected file itself is a bundle JSON, load it as bundle (multi-sheet)
    if (looksLikeBundle(parsed)) {
      const normalizedBundle = normalizeBundle(parsed);
      if (!normalizedBundle) {
        return {
          success: false,
          filePath,
          migrated: false,
          error: 'Invalid bundle format',
        };
      }

      const bundleFromMainFile = normalizedBundle;
      bundle = bundleFromMainFile;
      bundlePath = filePath;

      const mainSheet =
        bundleFromMainFile.sheets.find((s) => s.id === bundleFromMainFile.mainSheetId) || bundleFromMainFile.sheets[0];
      const mainDoc = (mainSheet as any)?.document || { nodes: [], edges: [] };

      const syntheticSkillInfo: SkillInfo = {
        skillId: '',
        skillName: nameFromPath || 'Skill',
        version: '1.0.0',
        lastModified: nowIso,
        workFlow: mainDoc as any,
        schemaVersion: (parsed as any)?.schemaVersion,
      };

      const bundleMigrationResult = migrateBundle(bundleFromMainFile);
      migrated = bundleMigrationResult.migratedCount > 0;
      if (migrated) {
        console.log('[SkillLoader] Bundle migration applied (main file bundle):', bundleMigrationResult);
      } else {
        console.log('[SkillLoader] Bundle migration not applied (main file bundle):', bundleMigrationResult);
      }

      // IMPORTANT: if the main selected file is the bundle itself, never overwrite it with SkillInfo JSON
      if (migrated && autoSaveMigrated) {
        try {
          const sanitizedBundle = JSON.parse(JSON.stringify(bundleFromMainFile));
          (sanitizedBundle as any).schemaVersion = CURRENT_SCHEMA_VERSION;
          sanitizeApiKeysDeep(sanitizedBundle);
          await ipcApi.writeSkillFile(bundlePath, JSON.stringify(sanitizedBundle, null, 2));
          console.log('[SkillLoader] Saved migrated bundle file (main file bundle):', bundlePath);
        } catch (saveErr) {
          console.warn('[SkillLoader] Failed to auto-save migrated bundle (main file bundle):', saveErr);
        }
      }

      return {
        success: true,
        skillInfo: syntheticSkillInfo,
        bundle,
        filePath,
        bundlePath,
        migrated,
      };
    }

    const skillInfo = parsed as SkillInfo;

    // 1.5. Normalize skillName (remove _skill suffix, derive from folder if needed)
    try {
      if (nameFromPath) {
        skillInfo.skillName = nameFromPath;
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
    if (migrated && autoSaveMigrated) {
      console.log('[SkillLoader] Auto-saving migrated files...');
      
      // Update schemaVersion on skillInfo
      (skillInfo as any).schemaVersion = CURRENT_SCHEMA_VERSION;
      skillInfo.lastModified = new Date().toISOString();
      
      try {
        // Create sanitized copies for saving (remove real API keys)
        const sanitizedSkillInfo = JSON.parse(JSON.stringify(skillInfo));
        sanitizeApiKeysDeep(sanitizedSkillInfo);
        
        // Save main skill file
        await ipcApi.writeSkillFile(filePath, JSON.stringify(sanitizedSkillInfo, null, 2));
        console.log('[SkillLoader] Saved migrated skill file:', filePath);
        
        // Save bundle file if exists
        if (bundle && bundlePath) {
          const sanitizedBundle = JSON.parse(JSON.stringify(bundle));
          sanitizedBundle.schemaVersion = CURRENT_SCHEMA_VERSION;
          sanitizeApiKeysDeep(sanitizedBundle);
          
          await ipcApi.writeSkillFile(bundlePath, JSON.stringify(sanitizedBundle, null, 2));
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
