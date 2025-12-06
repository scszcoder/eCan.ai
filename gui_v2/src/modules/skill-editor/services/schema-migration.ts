/**
 * ============================================================================
 * SCHEMA MIGRATION SERVICE
 * ============================================================================
 * 
 * This module handles version-based schema migrations for skill editor documents.
 * It ensures backward compatibility when loading old workflow data structures
 * and provides a centralized place to manage all migration logic.
 * 
 * ============================================================================
 * IMPORTANT: schemaVersion vs version (Skill Version)
 * ============================================================================
 * 
 * - `schemaVersion`: Workflow data structure/schema version, managed by this migration system.
 *   Used to track structural changes in how workflow data is organized (e.g., port ID format,
 *   node data structure, edge format). Users don't see or modify this.
 * 
 * - `version` (in SkillInfo): User-defined skill version for their own tracking.
 *   Used for skill content versioning (logic changes, layout updates, etc.).
 *   This is NOT related to data migration.
 * 
 * ============================================================================
 * VERSION HISTORY
 * ============================================================================
 * 
 * v1.0.0 (Legacy - before 2025-12-06):
 *   - Condition Node edges used hardcoded port IDs: "if_out", "else_out"
 *   - No explicit dataVersion field in files
 * 
 * v1.0.1 (2025-12-06):
 *   - Condition Node edges now use dynamic condition keys: "if_xxxxx", "else_yyyyy"
 *   - Supports dynamic elsif conditions with corresponding output ports
 *   - Added schemaVersion field to SkillInfo for explicit schema version tracking
 * 
 * ============================================================================
 * HOW TO ADD A NEW MIGRATION
 * ============================================================================
 * 
 * When you need to make a breaking change to the data format:
 * 
 * 1. Update CURRENT_SCHEMA_VERSION to the new version (e.g., "1.2.0")
 * 
 * 2. Create a migration function:
 *    ```typescript
 *    function migrateXxx_V1_1_0_to_V1_2_0(doc: any): void {
 *      // Transform doc from old format to new format
 *      // Modify doc in place
 *    }
 *    ```
 * 
 * 3. Register the migration in MIGRATIONS array:
 *    ```typescript
 *    {
 *      fromVersion: '1.1.0',
 *      toVersion: '1.2.0',
 *      description: 'Description of what this migration does',
 *      migrate: migrateXxx_V1_1_0_to_V1_2_0,
 *      addedDate: '2025-XX-XX',
 *      canRemoveAfter: '2026-XX-XX',  // Optional: when it's safe to remove
 *    }
 *    ```
 * 
 * 4. Update the VERSION HISTORY section above
 * 
 * 5. Update typings/skill-info.ts documentation if needed
 * 
 * ============================================================================
 * WHERE MIGRATIONS ARE APPLIED
 * ============================================================================
 * 
 * - services/skill-loader.ts: loadSkillFile() - unified entry for RouteFileLoader & useAutoLoadRecentFile
 * - components/tools/open.tsx: handleOpen() - manual file open dialog
 * - components/tools/save.tsx: Sets schemaVersion = CURRENT_SCHEMA_VERSION on save
 * 
 * Note: Migration is automatically followed by auto-save to persist schemaVersion
 * 
 * ============================================================================
 * CREATED: 2025-12-06
 * ============================================================================
 */

// Current workflow schema version - increment when making breaking changes to data structure
export const CURRENT_SCHEMA_VERSION = '1.0.1';

// Alias for backward compatibility (deprecated, use CURRENT_SCHEMA_VERSION)
export const CURRENT_DATA_VERSION = CURRENT_SCHEMA_VERSION;

// Minimum supported version for migration
export const MIN_SUPPORTED_VERSION = '1.0.0';

/**
 * Migration function type
 */
type MigrationFn = (doc: any) => void;

/**
 * Migration definition
 */
interface Migration {
  fromVersion: string;
  toVersion: string;
  description: string;
  migrate: MigrationFn;
  addedDate: string;
  canRemoveAfter?: string; // Date after which this migration can be safely removed
}

/**
 * Compare semantic versions
 * Returns: -1 if a < b, 0 if a == b, 1 if a > b
 */
function compareVersions(a: string, b: string): number {
  const partsA = a.split('.').map(Number);
  const partsB = b.split('.').map(Number);
  
  for (let i = 0; i < Math.max(partsA.length, partsB.length); i++) {
    const numA = partsA[i] || 0;
    const numB = partsB[i] || 0;
    if (numA < numB) return -1;
    if (numA > numB) return 1;
  }
  return 0;
}

/**
 * ============================================================================
 * MIGRATION FUNCTIONS
 * ============================================================================
 */

/**
 * Migration: v1.0.0 -> v1.0.1
 * Convert legacy Condition Node edges from if_out/else_out to dynamic condition keys
 */
function migrateConditionEdges_V1_0_0_to_V1_0_1(doc: any): void {
  if (!doc || !doc.nodes || !doc.edges) return;
  
  const nodes: any[] = Array.isArray(doc.nodes) ? doc.nodes : [];
  const edges: any[] = Array.isArray(doc.edges) ? doc.edges : [];
  
  const conditionNodes = nodes.filter((n) => n && n.type === 'condition');
  if (conditionNodes.length === 0) return;
  
  conditionNodes.forEach((condNode) => {
    const conditions: any[] = condNode.data?.conditions || [];
    if (conditions.length === 0) return;
    
    // Sort conditions: if first, elsif in middle, else last
    const sorted = [...conditions].sort((a, b) => {
      const keyA = a.key || '';
      const keyB = b.key || '';
      if (keyA.startsWith('if_')) return -1;
      if (keyB.startsWith('if_')) return 1;
      if (keyA.startsWith('else_')) return 1;
      if (keyB.startsWith('else_')) return -1;
      return 0;
    });
    
    const ifKey = sorted[0]?.key;
    const elseKey = sorted.length > 1 ? sorted[sorted.length - 1]?.key : null;
    
    // Migrate edges that reference this condition node
    let migratedCount = 0;
    edges.forEach((edge) => {
      const sourceId = edge.source || edge.sourceNodeID;
      if (sourceId !== condNode.id) return;
      
      const portId = edge.sourcePortID || edge.sourcePortId;
      if (portId === 'if_out' && ifKey) {
        edge.sourcePortID = ifKey;
        edge.sourcePortId = ifKey;
        migratedCount++;
      } else if (portId === 'else_out' && elseKey) {
        edge.sourcePortID = elseKey;
        edge.sourcePortId = elseKey;
        migratedCount++;
      }
    });
    
    if (migratedCount > 0) {
      console.log(`[DataMigration] Migrated ${migratedCount} edges for condition node ${condNode.id}: if_out->${ifKey}, else_out->${elseKey}`);
    }
  });
}

/**
 * ============================================================================
 * MIGRATIONS REGISTRY
 * ============================================================================
 * Add new migrations here in order. They will be applied sequentially.
 */
const MIGRATIONS: Migration[] = [
  {
    fromVersion: '1.0.0',
    toVersion: '1.0.1',
    description: 'Convert Condition Node edges from if_out/else_out to dynamic condition keys',
    migrate: migrateConditionEdges_V1_0_0_to_V1_0_1,
    addedDate: '2025-12-06',
    canRemoveAfter: '2026-06-01',
  },
  // Add future migrations here:
  // {
  //   fromVersion: '1.0.1',
  //   toVersion: '1.0.2',
  //   description: 'Description of the migration',
  //   migrate: migrationFunction,
  //   addedDate: 'YYYY-MM-DD',
  //   canRemoveAfter: 'YYYY-MM-DD',
  // },
];

/**
 * ============================================================================
 * PUBLIC API
 * ============================================================================
 */

/**
 * Get the schema version from a document
 */
export function getSchemaVersion(doc: any): string {
  // Check for explicit schema version field (new format)
  if (doc?.schemaVersion) return doc.schemaVersion;
  // Backward compatibility: check old dataVersion field
  if (doc?.dataVersion) return doc.dataVersion;
  
  // Infer version from data structure
  // If any condition node edge uses if_out/else_out, it's v1.0.0
  if (doc?.edges) {
    const hasLegacyPorts = doc.edges.some((edge: any) => {
      const portId = edge.sourcePortID || edge.sourcePortId;
      return portId === 'if_out' || portId === 'else_out';
    });
    if (hasLegacyPorts) return '1.0.0';
  }
  
  // Default to current version for new documents
  return CURRENT_SCHEMA_VERSION;
}

// Alias for backward compatibility
export const getDocumentVersion = getSchemaVersion;

/**
 * Set the schema version on a document
 */
export function setSchemaVersion(doc: any, version: string = CURRENT_SCHEMA_VERSION): void {
  if (doc) {
    doc.schemaVersion = version;
  }
}

// Alias for backward compatibility
export const setDocumentVersion = setSchemaVersion;

/**
 * Get migrations needed to upgrade from one version to another
 */
export function getMigrationsForUpgrade(fromVersion: string, toVersion: string = CURRENT_SCHEMA_VERSION): Migration[] {
  return MIGRATIONS.filter((m) => {
    return compareVersions(m.fromVersion, fromVersion) >= 0 && 
           compareVersions(m.toVersion, toVersion) <= 0;
  });
}

/**
 * Migrate a document to the current schema version
 * This is the main entry point for data migration
 */
export function migrateDocument(doc: any): { migrated: boolean; fromVersion: string; toVersion: string } {
  if (!doc) return { migrated: false, fromVersion: 'unknown', toVersion: CURRENT_SCHEMA_VERSION };
  
  const fromVersion = getSchemaVersion(doc);
  
  // Already at current version
  if (compareVersions(fromVersion, CURRENT_SCHEMA_VERSION) >= 0) {
    return { migrated: false, fromVersion, toVersion: CURRENT_SCHEMA_VERSION };
  }
  
  // Check if version is too old
  if (compareVersions(fromVersion, MIN_SUPPORTED_VERSION) < 0) {
    console.warn(`[SchemaMigration] Schema version ${fromVersion} is older than minimum supported version ${MIN_SUPPORTED_VERSION}`);
  }
  
  // Apply migrations in order
  let currentVersion = fromVersion;
  const applicableMigrations = MIGRATIONS.filter((m) => {
    return compareVersions(m.fromVersion, fromVersion) >= 0 &&
           compareVersions(m.toVersion, CURRENT_SCHEMA_VERSION) <= 0;
  });
  
  if (applicableMigrations.length > 0) {
    console.log(`[SchemaMigration] Migrating document from v${fromVersion} to v${CURRENT_SCHEMA_VERSION}`);
    
    applicableMigrations.forEach((migration) => {
      if (compareVersions(currentVersion, migration.fromVersion) <= 0) {
        console.log(`[SchemaMigration] Applying migration: ${migration.description}`);
        try {
          migration.migrate(doc);
          currentVersion = migration.toVersion;
        } catch (error) {
          console.error(`[SchemaMigration] Migration failed: ${migration.description}`, error);
        }
      }
    });
  }
  
  // Update schema version
  setSchemaVersion(doc, CURRENT_SCHEMA_VERSION);
  
  return { migrated: true, fromVersion, toVersion: CURRENT_SCHEMA_VERSION };
}

/**
 * Migrate a sheet's document
 */
export function migrateSheetDocument(sheet: any): boolean {
  if (!sheet?.document) return false;
  const result = migrateDocument(sheet.document);
  return result.migrated;
}

/**
 * Migrate all sheets in a bundle
 */
export function migrateBundle(bundle: any): { migratedCount: number; totalSheets: number } {
  if (!bundle?.sheets || !Array.isArray(bundle.sheets)) {
    return { migratedCount: 0, totalSheets: 0 };
  }
  
  let migratedCount = 0;
  bundle.sheets.forEach((sheet: any) => {
    if (migrateSheetDocument(sheet)) {
      migratedCount++;
    }
  });
  
  // Update bundle schema version
  bundle.schemaVersion = CURRENT_SCHEMA_VERSION;
  
  return { migratedCount, totalSheets: bundle.sheets.length };
}

/**
 * Get migration status report (useful for debugging)
 */
export function getMigrationReport(): {
  currentSchemaVersion: string;
  minSupportedVersion: string;
  migrations: Array<{
    from: string;
    to: string;
    description: string;
    addedDate: string;
    canRemoveAfter?: string;
  }>;
} {
  return {
    currentSchemaVersion: CURRENT_SCHEMA_VERSION,
    minSupportedVersion: MIN_SUPPORTED_VERSION,
    migrations: MIGRATIONS.map((m) => ({
      from: m.fromVersion,
      to: m.toVersion,
      description: m.description,
      addedDate: m.addedDate,
      canRemoveAfter: m.canRemoveAfter,
    })),
  };
}
