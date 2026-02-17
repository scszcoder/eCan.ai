/**
 * Tool Dispatcher — central router for all cloud-runnable tool handlers.
 *
 * Each tool handler lives in its own file under tools/ and exports an async
 * function whose name matches the tool_name.  This module builds a handler
 * map and provides a single `dispatch(toolName, toolInput)` entry point
 * that the LangGraph toolNode calls.
 */

// ── Imports ────────────────────────────────────────────────────────────

import { os_wait }            from "./os_wait.js";
import { say_hello }          from "./say_hello.js";
import { get_current_time }   from "./get_current_time.js";

// S3 File System
import { s3_list_objects }    from "./s3_list_objects.js";
import { s3_create_folder }   from "./s3_create_folder.js";
import { s3_delete_folder }   from "./s3_delete_folder.js";
import { s3_delete_object }   from "./s3_delete_object.js";
import { s3_move_object }     from "./s3_move_object.js";
import { s3_copy_object }     from "./s3_copy_object.js";
import { s3_get_object }      from "./s3_get_object.js";
import { s3_put_object }      from "./s3_put_object.js";

// RAG
import { ragify }             from "./ragify.js";
import { rag_query }          from "./rag_query.js";
import { wait_for_rag_completion } from "./wait_for_rag_completion.js";
import { ragify_async }       from "./ragify_async.js";

// Self-Introspection / Agent Management
import { describe_self }      from "./describe_self.js";
import { list_agents }        from "./list_agents.js";
import { list_skills }        from "./list_skills.js";
import { list_tasks }         from "./list_tasks.js";
import { create_agent }       from "./create_agent.js";
import { create_task_with_skill } from "./create_task_with_skill.js";
import { agent_add_tasks }    from "./agent_add_tasks.js";
import { register_skill }     from "./register_skill.js";
import { schedule_task }      from "./schedule_task.js";
import { stop_task }          from "./stop_task.js";
import { remove_task }        from "./remove_task.js";
import { subscribe_skill }    from "./subscribe_skill.js";
import { unsubscribe_skill }  from "./unsubscribe_skill.js";

// Code Execution / Search
import { run_code }           from "./run_code.js";
import { grep_search }        from "./grep_search.js";
import { find_files }         from "./find_files.js";

// Communication
import { list_chat_agents }   from "./list_chat_agents.js";
import { get_chat_history }   from "./get_chat_history.js";

// Cloud Cost Monitoring
import { aws_read_billing }   from "./aws_read_billing.js";
import { aws_shutdown }       from "./aws_shutdown.js";

// ── Handler Map ────────────────────────────────────────────────────────

const handlerMap = {
  os_wait,
  say_hello,
  get_current_time,
  s3_list_objects,
  s3_create_folder,
  s3_delete_folder,
  s3_delete_object,
  s3_move_object,
  s3_copy_object,
  s3_get_object,
  s3_put_object,
  ragify,
  rag_query,
  wait_for_rag_completion,
  ragify_async,
  describe_self,
  list_agents,
  list_skills,
  list_tasks,
  create_agent,
  create_task_with_skill,
  agent_add_tasks,
  register_skill,
  schedule_task,
  stop_task,
  remove_task,
  subscribe_skill,
  unsubscribe_skill,
  run_code,
  grep_search,
  find_files,
  list_chat_agents,
  get_chat_history,
  aws_read_billing,
  aws_shutdown,
};

// ── Dispatcher ─────────────────────────────────────────────────────────

/**
 * Dispatch a tool call to the appropriate handler.
 *
 * @param {string} toolName  — must match a tool name from tools_schema.js
 * @param {object} toolInput — the tool's input parameters (already unwrapped)
 * @returns {Promise<object>} — tool execution result
 * @throws {Error} if the tool handler is not found or execution fails
 */
export async function dispatch(toolName, toolInput) {
  const handler = handlerMap[toolName];
  if (typeof handler !== "function") {
    throw new Error(`No handler registered for tool: ${toolName}`);
  }
  return handler(toolInput);
}

/**
 * Check if a tool has a registered handler.
 */
export function hasHandler(toolName) {
  return typeof handlerMap[toolName] === "function";
}
