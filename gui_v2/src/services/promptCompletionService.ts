/**
 * Prompt Auto-Completion Service
 *
 * Provides two completion mechanisms:
 * 1. Template snippets — instant, local, for {{variables}} and markdown structures
 * 2. LLM ghost text — async, calls reqPromptAutoCompletion via AppSync
 */

import { appSyncRequest } from './web/appSyncClient';

// ─── Types ───

export interface PromptCompletionInput {
  prefix: string;
  suffix?: string;
  section?: string;
  prompt_name?: string;
  max_tokens?: number;
  temperature?: number;
  provider?: string;
  model?: string;
}

export interface PromptCompletionResult {
  reqPromptAutoCompletion: {
    completion: string;
    model?: string;
    error?: string;
  };
}

// ─── LLM Completion (Option 3a) ───

const COMPLETION_MUTATION = `
mutation ReqPromptAutoCompletion($input: PromptAutoCompletionInput!) {
  reqPromptAutoCompletion(input: $input) {
    completion
    model
    error
  }
}`;

let _abortController: AbortController | null = null;

/**
 * Request LLM-based auto-completion for prompt text.
 * Debouncing and cancellation should be handled by the caller.
 */
export async function requestPromptCompletion(
  input: PromptCompletionInput
): Promise<string | null> {
  // Cancel any in-flight request
  if (_abortController) {
    _abortController.abort();
  }
  _abortController = new AbortController();

  try {
    const result = await appSyncRequest<PromptCompletionResult>(
      COMPLETION_MUTATION,
      { input },
      { authMode: 'auto' },
      'reqPromptAutoCompletion'
    );

    const data = result?.reqPromptAutoCompletion;
    if (data?.error) {
      console.warn('[PromptCompletion] LLM error:', data.error);
      return null;
    }
    return data?.completion || null;
  } catch (err: any) {
    // Silently ignore abort errors
    if (err?.name === 'AbortError') return null;
    console.warn('[PromptCompletion] Request failed:', err?.message || err);
    return null;
  }
}

/**
 * Cancel any pending completion request.
 */
export function cancelPromptCompletion(): void {
  if (_abortController) {
    _abortController.abort();
    _abortController = null;
  }
}

// ─── Template Snippets (Option 1) ───

export interface SnippetItem {
  label: string;
  insertText: string;
  description?: string;
}

/**
 * Get variable snippet suggestions when the user types "{{".
 * Returns a list of system variables available for insertion.
 */
export function getVariableSnippets(filter?: string): SnippetItem[] {
  const allVars: SnippetItem[] = [
    { label: 'skills_schema', insertText: '{{skills_schema}}', description: 'Agent skills schema' },
    { label: 'tools_schema', insertText: '{{tools_schema}}', description: 'Agent tools schema' },
    { label: 'current_time', insertText: '{{current_time}}', description: 'Current UTC time' },
    { label: 'current_time_local', insertText: '{{current_time_local}}', description: 'Current local time' },
    { label: 'agent_name', insertText: '{{agent_name}}', description: 'Agent name' },
    { label: 'agent_id', insertText: '{{agent_id}}', description: 'Agent ID' },
    { label: 'chat_id', insertText: '{{chat_id}}', description: 'Chat session ID' },
    { label: 'task_id', insertText: '{{task_id}}', description: 'Current task ID' },
    { label: 'human_input', insertText: '{{human_input}}', description: 'User input text' },
    { label: 'step_count', insertText: '{{step_count}}', description: 'Current step count' },
    { label: 'max_steps', insertText: '{{max_steps}}', description: 'Maximum steps allowed' },
  ];

  if (!filter) return allVars;
  const lower = filter.toLowerCase();
  return allVars.filter(v => v.label.toLowerCase().includes(lower));
}

/**
 * Get markdown structure snippets (e.g., when typing # or > or ```).
 */
export function getMarkdownSnippets(trigger: string): SnippetItem[] {
  if (trigger === '#') {
    return [
      { label: '# Heading 1', insertText: '# ', description: 'Top-level heading' },
      { label: '## Heading 2', insertText: '## ', description: 'Section heading' },
      { label: '### Heading 3', insertText: '### ', description: 'Sub-section heading' },
    ];
  }
  if (trigger === '```') {
    return [
      { label: '```json```', insertText: '```json\n\n```', description: 'JSON code block' },
      { label: '```python```', insertText: '```python\n\n```', description: 'Python code block' },
      { label: '```text```', insertText: '```\n\n```', description: 'Plain code block' },
    ];
  }
  return [];
}
