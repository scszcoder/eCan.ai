/**
 * Knowledge Domain Types
 * 知识库相关的类型定义
 */

/**
 * 知识类型
 */
export enum KnowledgeType {
  DOCUMENT = 'document',
  DATABASE = 'database',
  API = 'api',
  FILE = 'file',
  WEB = 'web',
  OTHER = 'other',
}

/**
 * 知识状态
 */
export enum KnowledgeStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  DEPRECATED = 'deprecated',
  DRAFT = 'draft',
}

/**
 * 知识库条目类型
 */
export interface Knowledge {
  // 基础信息
  id: string;
  name: string;
  title?: string;
  description?: string;
  owner: string;
  
  // 知识属性
  knowledge_type?: KnowledgeType | string;
  version?: string;
  path?: string;
  level?: number; // 复杂度级别 1-5
  
  // 内容
  content?: string;
  tags?: string[];
  categories?: string[];
  category?: string; // 兼容旧字段
  
  // 配置
  config?: Record<string, any>;
  access_methods?: string[];
  limitations?: string[];
  
  // 访问和定价
  public?: boolean;
  rentable?: boolean;
  price?: number;
  price_model?: string; // free, per_access, subscription
  
  // 状态
  status?: KnowledgeStatus | string;
  
  // 元数据
  settings?: Record<string, any>;
  
  // 时间戳
  createdAt?: string;
  updatedAt?: string;
  created_at?: string; // 兼容后端字段
  updated_at?: string; // 兼容后端字段
}

/**
 * 问答对类型
 */
export interface QAPair {
  id: string;
  question: string;
  answer: string;
  asker?: string;
  category?: string;
  relatedKnowledgeIds?: string[];
  createdAt?: string;
  updatedAt?: string;
}

/**
 * 知识分类类型
 */
export interface KnowledgeCategory {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  children?: KnowledgeCategory[];
}

/**
 * 创建知识的输入类型
 */
export interface CreateKnowledgeInput {
  name: string;
  description?: string;
  owner: string;
  knowledge_type?: KnowledgeType;
  content?: string;
  tags?: string[];
  categories?: string[];
}

/**
 * 更新知识的输入类型
 */
export interface UpdateKnowledgeInput {
  name?: string;
  description?: string;
  knowledge_type?: KnowledgeType;
  version?: string;
  content?: string;
  tags?: string[];
  categories?: string[];
  status?: KnowledgeStatus;
  level?: number;
}

