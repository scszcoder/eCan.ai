/**
 * Skills 页面特有类型定义
 * 基础类型请从 @/types/domain/skill 导入
 */

// 从 domain 层导入基础类型
import type { Skill } from '@/types/domain/skill';
export type { Skill } from '@/types/domain/skill';
export { SkillLevel, SkillStatus } from '@/types/domain/skill';

export interface SkillsAPIResponseData {
    token: string;
    skills: Skill[];
    message: string;
}