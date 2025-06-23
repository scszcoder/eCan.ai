import { FlowDocumentJSON } from './node';

export interface SkillInfo {
  skillId: string;
  skillName: string;
  version: string;
  lastModified: string;
  workFlow: FlowDocumentJSON;
}

// @ts-ignore
const genUUID = () => (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`;

// 工具函数：生成一个新的 SkillInfo 对象
export function createSkillInfo(workFlow: FlowDocumentJSON): SkillInfo {
  return {
    skillId: genUUID(),
    skillName: 'Untitled Workflow Skill',
    version: '1.0.0',
    lastModified: new Date().toISOString(),
    workFlow,
  };
} 