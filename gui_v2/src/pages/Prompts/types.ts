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
  | 'additional'
  | 'custom'
  | 'tools_to_use';

export interface PromptSection {
  id: string;
  type: PromptSectionType;
  items: string[];
  customLabel?: string; // For custom sections, user-defined label
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
