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
  | 'exceptions'
  | 'extra_attentions'
  | 'custom'
  | 'tools_to_use';

export interface PromptSection {
  id: string;
  type: PromptSectionType;
  items: string[];
  customLabel?: string; // For custom sections, user-defined label
}

export type PromptFormat = 'json' | 'md';

export interface PromptAgentChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string; // ISO string
  /**
   * Set on assistant messages when the agent proposed an edit (the full
   * revised mdContent).  The UI shows an inline Apply/Discard card; once
   * applied or discarded the field is cleared.
   */
  proposedMdContent?: string;
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
  owner?: string;
  rawContent?: string;
  format?: PromptFormat; // 'json' (structured sections) or 'md' (markdown source)
  mdContent?: string; // markdown source text when format is 'md'
  /**
   * Per-prompt conversation thread with the prompt-editor chat agent.
   * Persisted to the prompt JSON so sessions survive reloads.
   */
  agentChatHistory?: PromptAgentChatMessage[];
}
