/**
 * Knowledge Domain Types
 * Type definitions for knowledge base
 */

/**
 * Knowledge type
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
 * Knowledge status
 */
export enum KnowledgeStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  DEPRECATED = 'deprecated',
  DRAFT = 'draft',
}

/**
 * Knowledge entry type
 */
export interface Knowledge {
  // Basic information
  id: string;
  name: string;
  title?: string;
  description?: string;
  owner: string;
  
  // Knowledge attributes
  knowledge_type?: KnowledgeType | string;
  version?: string;
  path?: string;
  level?: number; // Complexity level 1-5
  
  // Content
  content?: string;
  tags?: string[];
  categories?: string[];
  category?: string; // Compatible with old field
  
  // Configuration
  config?: Record<string, any>;
  access_methods?: string[];
  limitations?: string[];
  
  // Access and pricing
  public?: boolean;
  rentable?: boolean;
  price?: number;
  price_model?: string; // free, per_access, subscription
  
  // Status
  status?: KnowledgeStatus | string;
  
  // Metadata
  settings?: Record<string, any>;
  
  // Timestamps
  createdAt?: string;
  updatedAt?: string;
  created_at?: string; // Compatible with backend fields
  updated_at?: string; // Compatible with backend fields
}

/**
 * Q&A pair type
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
 * Knowledge category type
 */
export interface KnowledgeCategory {
  id: string;
  name: string;
  description?: string;
  parent_id?: string;
  children?: KnowledgeCategory[];
}

/**
 * Create knowledge input type
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
 * Update knowledge input type
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

