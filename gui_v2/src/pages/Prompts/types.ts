export type PromptSectionType =
  | 'role'
  | 'tone'
  | 'background'
  | 'goals'
  | 'guidelines'
  | 'rules'
  | 'instructions'
  | 'examples'
  | 'variables';

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
  sections: PromptSection[];
  humanInputs: string[]; // user prompt inputs
  lastModified?: string;
  source?: 'my_prompts' | 'sample_prompts';
  readOnly?: boolean;
}
