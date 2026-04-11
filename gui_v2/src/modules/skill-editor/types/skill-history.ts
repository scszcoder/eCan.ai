/**
 * Skill History Types
 * Type definitions for skill version history functionality
 */

export interface SkillHistoryRecord {
  id: string;
  skill_id: string;
  skill_name: string;
  owner: string;
  version: string;
  version_number: number;
  description?: string;
  version_label?: string;
  path?: string;
  source: string;
  level?: string;
  config?: Record<string, any>;
  diagram?: Record<string, any>;
  tags?: string[];
  skill_data?: Record<string, any>;
  file_size?: number;
  change_summary?: string;
  save_type: 'manual' | 'auto_save' | 'restore' | 'restore_backup' | 'save_as';
  created_at: number;
  updated_at: number;
}

export interface SkillHistoryListResponse {
  history_list: SkillHistoryRecord[];
  total: number;
  limit: number;
  offset: number;
  max_history: number;
}

export interface RestoreResult {
  success: boolean;
  skill_id: string;
  restored_from: {
    history_id: string;
    version: string;
    version_number: number;
    created_at: number;
    skill_name: string;
  };
  skill_data: Record<string, any>;
}

export interface HistoryCompareResult {
  version1: {
    id: string;
    version: string;
    version_number: number;
    created_at: number;
    skill_name: string;
  };
  version2: {
    id: string;
    version: string;
    version_number: number;
    created_at: number;
    skill_name: string;
  };
  differences: {
    changed_fields: Array<{ field: string; old_value: any; new_value: any }>;
    added_fields: string[];
    removed_fields: string[];
  };
}
