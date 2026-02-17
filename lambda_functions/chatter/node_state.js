/**
 * NodeState definition for LangGraph-based Chatter Lambda.
 *
 * Mirrors the Python NodeState TypedDict from agent/ec_skill.py,
 * adapted for the cloud chatter use-case.
 *
 * LangGraph JS uses Annotation.Root to define channels (state keys)
 * with optional reducers.  For simple overwrite semantics we just
 * list the keys; for list-append semantics we provide a reducer.
 */

import { Annotation } from "@langchain/langgraph";

// ---------------------------------------------------------------------------
// Reducers
// ---------------------------------------------------------------------------

/** Append-only reducer for arrays (mimics Python `operator.add`). */
function appendReducer(current, update) {
  if (!current) return update ?? [];
  if (!update) return current;
  return [...current, ...update];
}

/** Overwrite reducer — last write wins (default LangGraph behaviour). */
// Not needed explicitly; LangGraph uses overwrite by default.

// ---------------------------------------------------------------------------
// Graph State Annotation
// ---------------------------------------------------------------------------

/**
 * ChatterState — the state object flowing through the LangGraph.
 *
 * Field groups:
 *   Context   — input, attachments, prompts, history, messages
 *   Result    — result (dict), tool_calls, tool_result
 *   Control   — error, retries, n_steps, max_steps
 *   Metadata  — attributes, metadata, this_node
 */
export const ChatterState = Annotation.Root({
  // ── Context ──────────────────────────────────────────────
  /** The current user input text. */
  input:        Annotation({ reducer: (a, b) => b ?? a, default: () => "" }),
  /** File attachments from the user message. */
  attachments:  Annotation({ reducer: (a, b) => b ?? a, default: () => [] }),
  /** System / agent prompts built for this invocation. */
  prompts:      Annotation({ reducer: (a, b) => b ?? a, default: () => [] }),
  /** Raw chat history from DynamoDB. */
  history:      Annotation({ reducer: (a, b) => b ?? a, default: () => [] }),
  /** LangChain BaseMessage[] fed to the LLM. */
  messages:     Annotation({ reducer: appendReducer, default: () => [] }),

  // ── Result / Tool ────────────────────────────────────────
  /**
   * Structured result dict. Always contains at minimum:
   *   { msg_to_sender, qa_to_sender, topic_switched,
   *     work_related, request_answered, need_human_input, next_actions }
   */
  result:       Annotation({ reducer: (a, b) => ({ ...(a ?? {}), ...(b ?? {}) }), default: () => ({
    msg_to_sender: "",
    qa_to_sender: {},
    topic_switched: false,
    work_related: true,
    request_answered: false,
    need_human_input: false,
    next_actions: [],
  })}),
  /**
   * List of tool calls the LLM wants executed.
   * Each item: { tool_name: string, tool_input: object }
   */
  tool_calls:   Annotation({ reducer: (a, b) => b ?? a, default: () => [] }),
  /**
   * Collected results from tool execution.
   * Each item: { tool_name, success, output, error? }
   */
  tool_results: Annotation({ reducer: appendReducer, default: () => [] }),

  // ── Control ──────────────────────────────────────────────
  /** Last error message (empty string = no error). */
  error:        Annotation({ reducer: (a, b) => b ?? a, default: () => "" }),
  /** Current retry count for the active node. */
  retries:      Annotation({ reducer: (a, b) => b ?? a, default: () => 0 }),
  /** Number of outer-loop iterations completed. */
  n_steps:      Annotation({ reducer: (a, b) => b ?? a, default: () => 0 }),
  /** Maximum outer-loop iterations before forced exit. */
  max_steps:    Annotation({ reducer: (a, b) => b ?? a, default: () => 3 }),

  // ── Metadata / Routing ──────────────────────────────────
  /** Arbitrary key-value attributes. */
  attributes:   Annotation({ reducer: (a, b) => ({ ...(a ?? {}), ...(b ?? {}) }), default: () => ({}) }),
  /** Per-invocation metadata (channelId, sessionId, senderId, etc.). */
  metadata:     Annotation({ reducer: (a, b) => ({ ...(a ?? {}), ...(b ?? {}) }), default: () => ({}) }),
  /** Current node name (set automatically by graph). */
  this_node:    Annotation({ reducer: (a, b) => b ?? a, default: () => "" }),
});

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

/**
 * Create an initial ChatterState for a new invocation.
 *
 * @param {object} opts
 * @param {string} opts.input          - User's message text
 * @param {Array}  opts.attachments    - File attachments
 * @param {Array}  opts.prompts        - System prompts
 * @param {Array}  opts.history        - Raw chat history items
 * @param {Array}  opts.messages       - Pre-built LangChain messages
 * @param {object} opts.metadata       - channelId, sessionId, senderId, recipientId, etc.
 * @param {number} opts.max_steps      - Max outer-loop iterations (default 3)
 * @returns {object}
 */
export function createInitialState({
  input = "",
  attachments = [],
  prompts = [],
  history = [],
  messages = [],
  metadata = {},
  max_steps = 3,
} = {}) {
  return {
    input,
    attachments,
    prompts,
    history,
    messages,
    result: {
      msg_to_sender: "",
      qa_to_sender: {},
      topic_switched: false,
      work_related: true,
      request_answered: false,
      need_human_input: false,
      next_actions: [],
    },
    tool_calls: [],
    tool_results: [],
    error: "",
    retries: 0,
    n_steps: 0,
    max_steps,
    attributes: {},
    metadata,
    this_node: "",
  };
}
