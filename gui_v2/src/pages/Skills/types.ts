/**
 * Skills Page特有TypeDefinition
 * BaseType请从 @/types/domain/skill Import
 */

// 从 domain 层ImportBaseType
import type { Skill } from '@/types/domain/skill';
export type { Skill } from '@/types/domain/skill';
export { SkillLevel, SkillStatus } from '@/types/domain/skill';

export interface SkillsAPIResponseData {
    token: string;
    skills: Skill[];
    message: string;
}