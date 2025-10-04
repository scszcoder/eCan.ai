/**
 * Skill Domain Types
 * 技能相关的类型定义
 */

/**
 * 技能级别
 */
export enum SkillLevel {
  ENTRY = 'entry',
  INTERMEDIATE = 'intermediate',
  ADVANCED = 'advanced',
}

/**
 * 技能状态
 */
export enum SkillStatus {
  ACTIVE = 'active',
  LEARNING = 'learning',
  PLANNED = 'planned',
  INACTIVE = 'inactive',
}

/**
 * 技能类型
 */
export interface Skill {
  // 基础信息
  id: string;
  askid?: number;
  name: string;
  description?: string;
  owner: string;
  
  // 版本和路径
  version: string;
  latest_version?: string; // 最新版本号
  path?: string;
  
  // 技能属性
  level?: SkillLevel | string | number; // 支持枚举、字符串和数字（0-100）
  status?: SkillStatus | string; // 支持枚举和字符串
  category?: string;
  
  // 配置和元数据
  config?: Record<string, any> | string; // 支持对象或 JSON 字符串
  tags?: string[];
  examples?: string[];
  
  // 输入输出模式
  inputModes?: string[];
  outputModes?: string[];
  
  // 扩展字段
  apps?: any[] | string; // 支持数组或 JSON 字符串
  limitations?: any[] | string; // 支持数组或 JSON 字符串
  price?: number | string; // 支持数字或字符串
  price_model?: string;
  public?: boolean;
  rentable?: boolean;
  members?: string; // 成员列表
  
  // 使用统计
  usageCount?: number;
  lastUsed?: string;
  
  // 时间戳
  createdAt?: string;
  updatedAt?: string;
}

/**
 * 创建技能的输入类型
 */
export interface CreateSkillInput {
  name: string;
  description?: string;
  owner: string;
  version?: string;
  level?: SkillLevel;
  category?: string;
  tags?: string[];
  config?: Record<string, any>;
}

/**
 * 更新技能的输入类型
 */
export interface UpdateSkillInput {
  name?: string;
  description?: string;
  version?: string;
  level?: SkillLevel;
  status?: SkillStatus;
  category?: string;
  tags?: string[];
  config?: Record<string, any>;
  path?: string;
}

/**
 * 技能 API 响应数据
 */
export interface SkillsAPIResponseData {
  token?: string;
  skills: Skill[];
  message?: string;
}

