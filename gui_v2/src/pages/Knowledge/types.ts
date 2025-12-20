/**
 * Knowledge Page特有TypeDefinition
 * BaseType请从 @/types/domain/knowledge Import
 */

// 从 domain 层ImportBaseType
export type { Knowledge } from '@/types/domain/knowledge';
export { KnowledgeType, KnowledgeStatus } from '@/types/domain/knowledge';

// Page特有Type - 问答对
export interface QAPair {
  id: number;
  question: string;
  answer: string;
  asker: string;
  createdAt: string;
  category?: string;
  relatedKnowledgeIds?: number[];
}

// Page特有Type - 知识Category
export interface KnowledgeCategory {
  id: number;
  name: string;
  description?: string;
} 