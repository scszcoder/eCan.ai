export type SystemSectionType =
  | 'roleCharacter'
  | 'tone'
  | 'background'
  | 'goals'
  | 'guidelines'
  | 'rules'
  | 'examples'
  | 'instructions'
  | 'variables';

export interface SystemSection {
  id: string;
  type: SystemSectionType;
  items: string[];
  readOnly?: boolean;
}

export interface Prompt {
  id: string;
  title: string;
  topic: string; // topic phrase for list item
  usageCount: number;
  roleToneContext: string; // legacy support: merged into systemSections on load
  goals: string[];
  guidelines: string[];
  rules: string[];
  instructions: string[];
  sysInputs: string[]; // system prompt: inputs
  humanInputs: string[]; // human prompt: inputs
  systemSections?: SystemSection[];
  examples?: string[];
  readOnly?: boolean;
  lastModified?: string;
  location?: string;
}
