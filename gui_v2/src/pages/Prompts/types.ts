export type PromptSectionType =
  | 'role'
  | 'tone'
  | 'background'
  | 'goals'
  | 'guidelines'
  | 'rules'
  | 'instructions'
  | 'examples'
  | 'variables'
  | 'additional';

export interface PromptSection {
  id: string;
  type: PromptSectionType;
  items: string[];
}

export interface Prompt {
  id: string;
  title: string;
  topic: string; // topic phrase for list item
  usageCount: number;
  sections: PromptSection[]; // system prompt sections
  userSections: PromptSection[]; // user prompt sections
  humanInputs: string[]; // legacy field, kept for backward compatibility
  lastModified?: string;
  source?: 'my_prompts' | 'sample_prompts';
  readOnly?: boolean;
}
