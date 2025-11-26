export interface Prompt {
  id: string;
  title: string;
  topic: string; // topic phrase for list item
  usageCount: number;
  roleToneContext: string; // system prompt: role/tone/context
  goals: string[];
  guidelines: string[];
  rules: string[];
  instructions: string[];
  sysInputs: string[]; // system prompt: inputs
  humanInputs: string[]; // human prompt: inputs
  lastModified?: string;
}
