/**
 * Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
 * SPDX-License-Identifier: MIT
 */

import { FlowDocumentJSON } from './node';
import { CURRENT_SCHEMA_VERSION } from '../services/schema-migration';

/**
 * ============================================================================
 * SkillInfo - Skill Document Structure
 * ============================================================================
 * 
 * VERSION FIELDS EXPLAINED:
 * 
 * 1. `version` (Skill Version)
 *    - User-defined version of the skill content
 *    - Semantic versioning (e.g., "1.0.0", "2.1.3")
 *    - Updated by user when they make significant changes to the skill logic
 *    - Used for skill release management, user tracking, and content versioning
 *    - Example: User creates v1.0.0, then updates to v1.1.0 after adding features
 * 
 * 2. `schemaVersion` (Workflow Schema Version)
 *    - Internal version tracking the workflow data structure/architecture
 *    - Managed automatically by the editor, NOT by users
 *    - Used for backward compatibility and data migration
 *    - Tracks structural changes like: port ID format, node data structure, edge format
 *    - When loading old files, the migration system checks this version
 *      and applies necessary transformations
 *    - Example: "1.0.0" used if_out/else_out, "1.1.0" uses dynamic condition keys
 * 
 * HOW SCHEMA VERSION MIGRATION WORKS:
 * 
 * 1. When a skill file is loaded:
 *    - System checks `schemaVersion` (or infers from data structure if missing)
 *    - If version < CURRENT_SCHEMA_VERSION, migrations are applied
 *    - See: services/data-migration.ts for migration logic
 * 
 * 2. When a skill file is saved:
 *    - `schemaVersion` is always set to CURRENT_SCHEMA_VERSION
 *    - This ensures the file is marked as up-to-date
 * 
 * 3. Migration is transparent to users:
 *    - Old files are automatically upgraded when opened
 *    - No user action required
 * 
 * RELATED FILES:
 * - services/schema-migration.ts: Migration logic and version constants
 * - stores/sheets-store.ts: Applies migrations during data loading
 * - components/tools/save.tsx: Sets schemaVersion when saving
 * ============================================================================
 */
export interface SkillInfo {
  skillId: string;
  skillName: string;
  /** 
   * Skill version - User-defined, for tracking skill content changes.
   * This is NOT the schema version. Users update this when they
   * make changes to their skill logic, layout, or content (e.g., "1.0.0" -> "1.1.0").
   */
  version: string;
  lastModified: string;
  workFlow: FlowDocumentJSON;
  /**
   * Workflow schema version - System-managed, for backward compatibility.
   * Tracks the workflow data structure/architecture format. When loading old files,
   * the migration system uses this to determine which transformations to apply.
   * Always set to CURRENT_SCHEMA_VERSION when saving.
   * @see services/schema-migration.ts for version history and migration logic
   */
  schemaVersion?: string;
  mode?: 'development' | 'released';  // UI editor state (editable vs readonly)
  run_mode?: 'developing' | 'released';  // Backend runtime mode (for mapping rules selection)
  // Optional per-skill config. We use this to promote node.data.mapping_rules
  // into a runtime-friendly location consumed by the agent backend.
  config?: {
    nodes?: Record<string, {
      mapping_rules?: any;
      [key: string]: any;
    }>;
    skill_mapping?: any;  // Skill-level mapping rules from START node
    [key: string]: any;
  };
}

// @ts-ignore
const genUUID = () => (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`;

// ToolFunction：生成一个新的 SkillInfo 对象
export function createSkillInfo(workFlow: FlowDocumentJSON): SkillInfo {
  return {
    skillId: genUUID(),
    skillName: 'Untitled Workflow Skill',
    version: '1.0.0',
    lastModified: new Date().toISOString(),
    schemaVersion: CURRENT_SCHEMA_VERSION,  // Current workflow schema version
    mode: 'development',
    workFlow,
  };
}