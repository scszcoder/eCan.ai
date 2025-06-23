import { FlowDocumentJSON } from './node';

export interface SkillInfo {
  skillId: string;
  skillName: string;
  version: string;
  lastModified: string;
  workFlow: FlowDocumentJSON;
} 