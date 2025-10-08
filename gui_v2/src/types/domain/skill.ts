/**
 * Skill Domain Types
 * 技能相关的类型定义
 *
 * 匹配 DBAgentSkill 和 EC_Skill 的数据结构
 */

/**
 * 技能级别 - 匹配 EC_Skill.level
 */
export enum SkillLevel {
  ENTRY = 'entry',
  INTERMEDIATE = 'intermediate',
  ADVANCED = 'advanced',
}

/**
 * 技能状态 - 用于 UI 显示
 */
export enum SkillStatus {
  ACTIVE = 'active',
  LEARNING = 'learning',
  PLANNED = 'planned',
  INACTIVE = 'inactive',
}

/**
 * 技能运行模式 - 匹配 EC_Skill.run_mode
 */
export enum SkillRunMode {
  DEVELOPMENT = 'development',
  RELEASED = 'released',
}

/**
 * UI 信息 - 匹配 EC_Skill.ui_info
 */
export interface SkillUIInfo {
  text?: string;
  icon?: string;
}

/**
 * 需要的输入 - 匹配 EC_Skill.need_inputs
 */
export interface SkillNeedInput {
  name: string;
  type?: string;
  description?: string;
  required?: boolean;
  default?: any;
}

/**
 * 映射规则 - 匹配 EC_Skill.mapping_rules
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
 * 技能类型 - 完整匹配 DBAgentSkill 和 EC_Skill
 */
export interface Skill {
  // ========== DBAgentSkill 基础字段 ==========
  // 主键和标识
  id: string;
  askid?: number;

  // 基础信息
  name: string;
  owner: string;
  description?: string;

  // 版本和路径
  version: string;
  path?: string;

  // 技能属性
  level?: SkillLevel | string; // entry/intermediate/advanced

  // 配置
  config?: Record<string, any> | string; // JSON 配置

  // EC_Skill 字段
  tags?: string[]; // 标签列表
  examples?: string[]; // 示例列表
  inputModes?: string[]; // 输入模式
  outputModes?: string[]; // 输出模式

  // 扩展字段
  apps?: any[] | string; // 应用列表
  limitations?: any[] | string; // 限制列表
  price?: number; // 价格
  price_model?: string; // 价格模型
  public?: boolean; // 是否公开
  rentable?: boolean; // 是否可租用

  // ========== EC_Skill 额外字段 ==========
  ui_info?: SkillUIInfo; // UI 信息
  objectives?: string[]; // 目标列表
  need_inputs?: SkillNeedInput[]; // 需要的输入
  run_mode?: SkillRunMode | string; // 运行模式: development/released
  mapping_rules?: SkillMappingRule | null; // 映射规则

  // ========== UI 扩展字段 ==========
  status?: SkillStatus | string; // UI 状态
  category?: string; // 分类

  // 使用统计
  usageCount?: number;
  lastUsed?: string;

  // 时间戳 (TimestampMixin)
  createdAt?: string;
  updatedAt?: string;

  // 扩展数据 (ExtensibleMixin)
  extra_data?: Record<string, any>;
}

/**
 * 创建技能的输入类型
 */
export interface CreateSkillInput {
  // 必填字段
  name: string;
  owner: string;
  version?: string;

  // 可选基础信息
  description?: string;
  level?: SkillLevel | string;
  path?: string;

  // 配置和元数据
  config?: Record<string, any>;
  tags?: string[];
  examples?: string[];

  // 输入输出模式
  inputModes?: string[];
  outputModes?: string[];

  // EC_Skill 字段
  ui_info?: SkillUIInfo;
  objectives?: string[];
  need_inputs?: SkillNeedInput[];
  run_mode?: SkillRunMode | string;
  mapping_rules?: SkillMappingRule | null;

  // 扩展字段
  apps?: any[];
  limitations?: any[];
  price?: number;
  price_model?: string;
  public?: boolean;
  rentable?: boolean;

  // UI 字段
  category?: string;
  status?: SkillStatus | string;
}

/**
 * 更新技能的输入类型
 */
export interface UpdateSkillInput {
  // 基础信息
  name?: string;
  description?: string;
  version?: string;
  level?: SkillLevel | string;
  path?: string;

  // 配置和元数据
  config?: Record<string, any>;
  tags?: string[];
  examples?: string[];

  // 输入输出模式
  inputModes?: string[];
  outputModes?: string[];

  // EC_Skill 字段
  ui_info?: SkillUIInfo;
  objectives?: string[];
  need_inputs?: SkillNeedInput[];
  run_mode?: SkillRunMode | string;
  mapping_rules?: SkillMappingRule | null;

  // 扩展字段
  apps?: any[];
  limitations?: any[];
  price?: number;
  price_model?: string;
  public?: boolean;
  rentable?: boolean;

  // UI 字段
  status?: SkillStatus | string;
  category?: string;
}

/**
 * 技能 API 响应数据
 */
export interface SkillsAPIResponseData {
  token?: string;
  skills: Skill[];
  message?: string;
}

