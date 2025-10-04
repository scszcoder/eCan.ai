/**
 * Knowledge 页面特有类型定义
 * 基础类型请从 @/types/domain/knowledge 导入
 */

// 从 domain 层导入基础类型
export type { Knowledge } from '@/types/domain/knowledge';
export { KnowledgeType, KnowledgeStatus } from '@/types/domain/knowledge';

// 页面特有类型 - 问答对
export interface QAPair {
  id: number;
  question: string;
  answer: string;
  asker: string;
  createdAt: string;
  category?: string;
  relatedKnowledgeIds?: number[];
}

// 页面特有类型 - 知识分类
export interface KnowledgeCategory {
  id: number;
  name: string;
  description?: string;
} 