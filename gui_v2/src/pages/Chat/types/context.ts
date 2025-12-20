/**
 * Context Panel Types
 */

export type ContextItemType = 
  | 'text'
  | 'tool_call'
  | 'db_access'
  | 'api_call'
  | 'code_execution'
  | 'file_operation'
  | 'system_event';

export type ContextItemGenerator = 'agent' | 'human' | 'system';

export interface ContextItemContent {
  message?: string;
  description?: string;
  toolName?: string;
  toolParams?: Record<string, any>;
  toolResult?: any;
  code?: string;
  codeLanguage?: string;
  json?: Record<string, any>;
  error?: string;
}

export interface ContextItem {
  uid: string;
  type: ContextItemType;
  timestamp: string;
  generator: ContextItemGenerator;
  generatorName: string; // Agent name or "User" or "System"
  content: ContextItemContent;
}

export interface ChatContext {
  uid: string;
  title: string;
  messageCount: number;
  mostRecentTimestamp: string;
  mostRecentMessage: string;
  items: ContextItem[];
  isArchived?: boolean;
}

export interface ContextPanelState {
  contexts: ChatContext[];
  searchQuery: string;
}
