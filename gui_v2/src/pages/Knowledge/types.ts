// 知识条目类型
export interface KnowledgeEntry {
  id: number;
  title: string;
  content: string;
  category: string;
  tags?: string[];
  createdAt: string;
  updatedAt: string;
}

// 问答对类型
export interface QAPair {
  id: number;
  question: string;
  answer: string;
  asker: string;
  createdAt: string;
  category?: string;
  relatedKnowledgeIds?: number[];
}

// 知识分类类型
export interface KnowledgeCategory {
  id: number;
  name: string;
  description?: string;
} 