export interface Skill {
    id: number;
    name: string;
    description: string;
    category: string;
    level: number;
    status: 'active' | 'learning' | 'planned';
    lastUsed: string;
    usageCount: number;
}

export interface SkillsAPIResponseData {
    token: string;
    skills: Skill[];
    message: string;
} 