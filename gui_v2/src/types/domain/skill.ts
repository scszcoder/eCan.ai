/**
 * Skill Domain Types
 * Type definitions for skills
 *
 * Matches DBAgentSkill and EC_Skill data structures
 */

/**
 * Skill level - matches EC_Skill.level
 */
export enum SkillLevel {
  ENTRY = 'entry',
  INTERMEDIATE = 'intermediate',
  ADVANCED = 'advanced',
}

/**
 * Skill status - used for UI display
 */
export enum SkillStatus {
  ACTIVE = 'active',
  LEARNING = 'learning',
  PLANNED = 'planned',
  INACTIVE = 'inactive',
}

/**
 * Skill run mode - matches EC_Skill.run_mode
 */
export enum SkillRunMode {
  DEVELOPMENT = 'development',
  RELEASED = 'released',
}

/**
 * Skill run environment - where the skill executes.
 * Supersedes deprecated run_in_cloud and hybrid_cloud_mode fields.
 *
 * Defined values:
 * - 'local': Skill runs entirely on local machine
 * - 'cloud': Skill runs entirely in the cloud (Lambda/serverless)
 * - 'hybrid': Skill runs with local+cloud components (hybrid mode)
 */
export enum SkillRunEnvironment {
  LOCAL = 'local',
  CLOUD = 'cloud',
  HYBRID = 'hybrid',
}

/**
 * Skill source - origin of the skill in the system.
 * 
 * Defined values:
 * - 'ui': Skill created through the UI (skill editor / scaffold)
 * - 'code': Built-in code-based skill from resource/my_skills (read-only, auto-built)
 * - 'subscribed': Third-party skill subscribed from marketplace (read-only, synced from cloud)
 * - 'external': Skill with files on disk but managed outside the system
 */
export type SkillSource = 'ui' | 'code' | 'subscribed' | 'external';

/**
 * UI information - matches EC_Skill.ui_info
 */
export interface SkillUIInfo {
  text?: string;
  icon?: string;
}

/**
 * Required inputs - matches EC_Skill.need_inputs
 */
export interface SkillNeedInput {
  name: string;
  type?: string;
  description?: string;
  required?: boolean;
  default?: any;
}

/**
 * Mapping rules - matches EC_Skill.mapping_rules
 */
export interface SkillMappingRule {
  [mode: string]: {
    mappings: Array<{
      from: string[];
      to: Array<{ target: string }>;
      transform?: string;
      on_conflict?: string;
    }>;
  };
}

/**
 * Skill type - fully matches DBAgentSkill and EC_Skill
 */
export interface Skill {
  // ========== DBAgentSkill base fields ==========
  // Primary key and identifier
  id: string;
  askid?: number;
  /** Cloud UUID when synced; used with local id to avoid duplicate list entries */
  cloud_id?: string;

  // Basic information
  name: string;
  owner: string;
  description?: string;

  // Version and path
  version: string;
  path?: string;

  // Skill attributes
  level?: SkillLevel | string; // entry/intermediate/advanced

  // Configuration
  // NOTE: run_in_cloud and hybrid_cloud_mode are deprecated in favor of run_environment
  config?: Record<string, any> | string; // JSON configuration

  // Execution environment: where the skill runs
  run_environment?: SkillRunEnvironment | string;

  // EC_Skill fields
  tags?: string[]; // Tag list
  examples?: string[]; // Example list
  inputModes?: string[]; // Input modes
  outputModes?: string[]; // Output modes

  // Extended fields
  apps?: any[] | string; // Application list
  limitations?: any[] | string; // Limitations list
  price?: number; // Price
  price_model?: string; // Price model
  public?: boolean; // Whether public
  rentable?: boolean; // Whether rentable

  // ========== EC_Skill additional fields ==========
  ui_info?: SkillUIInfo; // UI information
  objectives?: string[]; // Objectives list
  need_inputs?: SkillNeedInput[]; // Required inputs
  run_mode?: SkillRunMode | string; // Run mode: development/released
  mapping_rules?: SkillMappingRule | null; // Mapping rules
  diagram?: Record<string, any>; // Workflow/diagram data (nodes, edges, etc.)

  // ========== UI extended fields ==========
  status?: SkillStatus | string; // UI status
  category?: string; // Category

  // Source type: origin of the skill ('ui'/'code'/'subscribed'/'external')
  source?: SkillSource;

  // Original owner when the skill was copied/subscribed
  skillOwner?: string;

  // Usage statistics
  usageCount?: number;
  lastUsed?: string;

  // Rating / Reviews
  rating?: number;
  reviewCount?: number;
  rating_distribution?: Record<number, number>;

  // Timestamps (TimestampMixin)
  createdAt?: string;
  updatedAt?: string;

  // Extended data (ExtensibleMixin)
  extra_data?: Record<string, any>;
}

/**
 * Create skill input type
 */
export interface CreateSkillInput {
  // Required fields
  name: string;
  owner: string;
  version?: string;

  // Optional basic information
  description?: string;
  level?: SkillLevel | string;
  path?: string;

  // Configuration and metadata
  config?: Record<string, any>;
  tags?: string[];
  examples?: string[];

  // Input/output modes
  inputModes?: string[];
  outputModes?: string[];

  // EC_Skill fields
  ui_info?: SkillUIInfo;
  objectives?: string[];
  need_inputs?: SkillNeedInput[];
  run_mode?: SkillRunMode | string;
  mapping_rules?: SkillMappingRule | null;

  // Extended fields
  apps?: any[];
  limitations?: any[];
  price?: number;
  price_model?: string;
  public?: boolean;
  rentable?: boolean;

  // UI fields
  category?: string;
  status?: SkillStatus | string;
}

/**
 * Update skill input type
 */
export interface UpdateSkillInput {
  // Basic information
  name?: string;
  description?: string;
  version?: string;
  level?: SkillLevel | string;
  path?: string;

  // Configuration and metadata
  config?: Record<string, any>;
  tags?: string[];
  examples?: string[];

  // Input/output modes
  inputModes?: string[];
  outputModes?: string[];

  // EC_Skill fields
  ui_info?: SkillUIInfo;
  objectives?: string[];
  need_inputs?: SkillNeedInput[];
  run_mode?: SkillRunMode | string;
  mapping_rules?: SkillMappingRule | null;

  // Extended fields
  apps?: any[];
  limitations?: any[];
  price?: number;
  price_model?: string;
  public?: boolean;
  rentable?: boolean;

  // UI fields
  status?: SkillStatus | string;
  category?: string;
}

/**
 * Skills API response data
 */
export interface SkillsAPIResponseData {
  token?: string;
  skills: Skill[];
  message?: string;
}

/**
 * Subscribed skill - extends Skill with subscription metadata
 */
export interface SubscribedSkill extends Skill {
  subscribedAt?: string;
  subscribedBy?: string;
}

