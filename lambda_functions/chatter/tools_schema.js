/**
 * Cloud MCP Tools Schema for Chatter Lambda
 * 
 * JavaScript port of agent/mcp/server/tool_schemas.py
 * Defines cloud-side MCP tool schemas that agents can reference.
 * 
 * Each tool schema follows the MCP Tool format:
 *   { name, description, inputSchema, outputSchema?, meta? }
 */

const toolSchemas = [];

function addToolSchema(schema) {
  toolSchemas.push(schema);
}

/**
 * Build all cloud MCP tool schemas.
 * Returns an array of tool schema objects.
 */
export function build_cloud_mcp_tools_schema() {
  // Clear any previously built schemas
  toolSchemas.length = 0;

  // ============================================================
  // OS Tools
  // ============================================================

  addToolSchema({
    name: "os_wait",
    description: "<category>OS</category><sub-category>Timer</sub-category>wait a few seconds.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["seconds"],
          properties: {
            seconds: { type: "integer", description: "number of seconds to wait" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "say_hello",
    description: "<category>OS</category><sub-category>General</sub-category>just a test.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "get_current_time",
    description: "<category>OS</category><sub-category>Timer</sub-category>Get the current date and time in yyyy-mm-dd hh:mm:ss format.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // S3 File System Tools
  // ============================================================

  const s3BaseProps = {
    bucket: { type: "string", description: "S3 bucket name" },
    user_name: { type: "string", description: "username for access-control gating — determines which key prefixes the user may read/write" },
  };

  addToolSchema({
    name: "s3_list_objects",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>List objects (files and prefixes) under an S3 key prefix. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key prefix to list (e.g. 'data/reports/'). Must end with '/' for directory-like listing." },
            pattern: { type: "string", description: "optional glob pattern to filter results (e.g. '*.csv'). Default is '*'." },
            recursive: { type: "boolean", description: "if true, list objects recursively under the prefix. Default is false." },
            max_keys: { type: "integer", description: "maximum number of keys to return. Default is 1000." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_create_folder",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Create a folder (zero-byte object with trailing '/') in S3. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key for the folder to create (must end with '/')" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_delete_folder",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Delete a folder and all objects under the given key prefix in S3. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key prefix of the folder to delete (must end with '/')" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_delete_object",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Delete a single object (file) in S3. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key of the object to delete" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_move_object",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Move (copy then delete) an object from one S3 location to another. Access is gated by user_name for both source and destination.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "src_key", "dest_key", "user_name"],
          properties: {
            ...s3BaseProps,
            src_key: { type: "string", description: "S3 key of the source object" },
            dest_key: { type: "string", description: "S3 key of the destination" },
            dest_bucket: { type: "string", description: "destination bucket if different from source bucket (optional)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_copy_object",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Copy an object from one S3 location to another. Access is gated by user_name for both source and destination.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "src_key", "dest_key", "user_name"],
          properties: {
            ...s3BaseProps,
            src_key: { type: "string", description: "S3 key of the source object" },
            dest_key: { type: "string", description: "S3 key of the destination" },
            dest_bucket: { type: "string", description: "destination bucket if different from source bucket (optional)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_get_object",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Download an object from S3 to a local /tmp path. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name", "local_path"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key of the object to download" },
            local_path: { type: "string", description: "local file path under /tmp to save the downloaded object (e.g. '/tmp/report.csv')" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "s3_put_object",
    description: "<category>Cloud</category><sub-category>S3 File System</sub-category>Upload/write content to an S3 object. Access is gated by user_name.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["bucket", "key", "user_name", "content"],
          properties: {
            ...s3BaseProps,
            key: { type: "string", description: "S3 key for the object to write" },
            content: { type: "string", description: "text content to upload" },
            content_type: { type: "string", description: "MIME type of the content (e.g. 'text/plain', 'application/json'). Default is 'application/octet-stream'." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });


  // ============================================================
  // RAG Tools
  // ============================================================

  addToolSchema({
    name: "ragify",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Index documents into RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["source"],
          properties: {
            source: { type: "string", description: "source path or URL to index" },
            chunk_size: { type: "integer", description: "optional chunk size for splitting documents" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "rag_query",
    description: "<category>RAG</category><sub-category>Query</sub-category>Query the RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["query"],
          properties: {
            query: { type: "string", description: "search query for the knowledge base" },
            top_k: { type: "integer", description: "number of top results to return" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "wait_for_rag_completion",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Wait for an async RAG indexing job to complete.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["job_id"],
          properties: {
            job_id: { type: "string", description: "ID of the RAG indexing job to wait for" },
            timeout: { type: "integer", description: "max seconds to wait" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "ragify_async",
    description: "<category>RAG</category><sub-category>Indexing</sub-category>Asynchronously index documents into RAG knowledge base.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["source"],
          properties: {
            source: { type: "string", description: "source path or URL to index" },
            chunk_size: { type: "integer", description: "optional chunk size for splitting documents" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Self-Introspection Tools
  // ============================================================

  addToolSchema({
    name: "describe_self",
    description: "<category>Agent</category><sub-category>Self</sub-category>Describe the agent's own capabilities and configuration.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "list_agents",
    description: "<category>Agent</category><sub-category>Self</sub-category>List all available agents and their statuses.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID to list agents for" },
            status_filter: { type: "string", enum: ["all", "online", "offline", "busy"], description: "filter agents by status. Default is 'all'." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "list_skills",
    description: "<category>Agent</category><sub-category>Self</sub-category>List all available skills and their statuses.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID to list skills for" },
            category: { type: "string", description: "optional category filter (e.g. 'automation', 'search', 'communication')" },
            status_filter: { type: "string", enum: ["all", "active", "inactive", "draft"], description: "filter skills by status. Default is 'all'." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "list_tasks",
    description: "<category>Agent</category><sub-category>Self</sub-category>List all available tasks and their statuses.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID to list tasks for" },
            agent_id: { type: "string", description: "optional agent ID to filter tasks assigned to a specific agent" },
            status_filter: { type: "string", enum: ["all", "running", "scheduled", "completed", "failed", "stopped"], description: "filter tasks by status. Default is 'all'." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "create_agent",
    description: "<category>Agent</category><sub-category>Self</sub-category>Create a new agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id", "agent_name"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID who will own the agent" },
            agent_name: { type: "string", description: "display name for the new agent" },
            agent_type: { type: "string", enum: ["worker", "supervisor", "specialist"], description: "type/role of the agent. Default is 'worker'." },
            description: { type: "string", description: "optional description of the agent's purpose" },
            config: { type: "object", description: "optional agent configuration (e.g. LLM provider, model, temperature)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "create_task_with_skill",
    description: "<category>Agent</category><sub-category>Self</sub-category>Create a new task.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id", "task_name", "skill_name"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID who will own the task" },
            task_name: { type: "string", description: "display name for the task" },
            skill_name: { type: "string", description: "name of the skill this task will use" },
            description: { type: "string", description: "optional description of what the task does" },
            parameters: { type: "object", description: "input parameters to pass to the skill when the task runs" },
            schedule: { type: "string", description: "optional cron expression or ISO datetime for scheduling (e.g. '0 9 * * MON-FRI' or '2026-03-01T09:00:00Z')" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "agent_add_tasks",
    description: "<category>Agent</category><sub-category>Self</sub-category>Assign one or more tasks to an agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id", "task_ids"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent to assign tasks to" },
            task_ids: { type: "array", items: { type: "string" }, description: "list of task IDs to assign to the agent" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "register_skill",
    description: "<category>Agent</category><sub-category>Self</sub-category>Register a new skill in the skill registry.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["owner_id", "name", "category"],
          properties: {
            owner_id: { type: "string", description: "owner/user ID who will own the skill" },
            name: { type: "string", description: "unique name for the skill" },
            category: { type: "string", description: "skill category (e.g. 'automation', 'search', 'communication', 'data_processing')" },
            description: { type: "string", description: "human-readable description of what the skill does" },
            input_schema: { type: "object", description: "JSON schema describing the skill's expected input parameters" },
            output_schema: { type: "object", description: "JSON schema describing the skill's output format" },
            triggers: { type: "array", items: { type: "object" }, description: "list of trigger configurations (e.g. schedule, event-based)" },
            nodes: { type: "array", items: { type: "object" }, description: "list of node definitions that make up the skill's workflow graph" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "schedule_task",
    description: "<category>Agent</category><sub-category>Task</sub-category>Schedule a task to run at a specific time or interval.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["task_id", "schedule"],
          properties: {
            task_id: { type: "string", description: "ID of the task to schedule" },
            schedule: { type: "string", description: "cron expression (e.g. '0 9 * * MON-FRI') or ISO datetime (e.g. '2026-03-01T09:00:00Z') for when to run" },
            timezone: { type: "string", description: "IANA timezone for the schedule (e.g. 'America/New_York'). Default is 'UTC'." },
            repeat: { type: "boolean", description: "if true, the schedule repeats per cron expression. If false, runs once at the specified time. Default is true for cron, false for ISO datetime." },
            parameters: { type: "object", description: "optional parameters to override the task's default skill parameters for this schedule" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "stop_task",
    description: "<category>Agent</category><sub-category>Task</sub-category>Stop a running task.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["task_id"],
          properties: {
            task_id: { type: "string", description: "ID of the task to stop" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "remove_task",
    description: "<category>Agent</category><sub-category>Task</sub-category>Remove a task.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["task_id"],
          properties: {
            task_id: { type: "string", description: "ID of the task to remove" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  
  addToolSchema({
    name: "subscribe_skill",
    description: "<category>Agent</category><sub-category>Skill</sub-category>Subscribe an agent to a skill so it can use it.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id", "skill_id"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent subscribing to the skill" },
            skill_id: { type: "string", description: "ID of the skill to subscribe to" },
            role: { type: "string", enum: ["executor", "observer", "owner"], description: "agent's role for this skill subscription. Default is 'executor'." },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  
  addToolSchema({
    name: "unsubscribe_skill",
    description: "<category>Agent</category><sub-category>Skill</sub-category>Unsubscribe an agent from a skill.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id", "skill_id"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent to unsubscribe" },
            skill_id: { type: "string", description: "ID of the skill to unsubscribe from" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });
  // ============================================================
  // Code Execution Tools
  // ============================================================

  addToolSchema({
    name: "run_code",
    description: "<category>System</category><sub-category>Run Code</sub-category>Execute code in a sandboxed environment.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["language", "code"],
          properties: {
            language: { type: "string", description: "programming language (python, javascript, bash)" },
            code: { type: "string", description: "source code to execute" },
            arguments: { type: "array", items: { type: "object" }, description: "command-line arguments to pass to the code at runtime" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });


  addToolSchema({
    name: "grep_search",
    description: "<category>System</category><sub-category>Search</sub-category>Search for text patterns in files using grep.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["pattern", "path"],
          properties: {
            pattern: { type: "string", description: "search pattern (regex supported)" },
            path: { type: "string", description: "directory or file path to search in" },
            recursive: { type: "boolean", description: "search recursively in subdirectories" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "find_files",
    description: "<category>System</category><sub-category>Search</sub-category>Find files matching a pattern.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["path"],
          properties: {
            path: { type: "string", description: "directory to search in" },
            name: { type: "string", description: "file name pattern to match" },
            type: { type: "string", description: "file type filter (f=file, d=directory)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });


  addToolSchema({
    name: "list_chat_agents",
    description: "<category>Communication</category><sub-category>Chat</sub-category>List available agents for chat communication.",
    inputSchema: { type: "object", required: [], properties: {} },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "get_chat_history",
    description: "<category>Communication</category><sub-category>Chat</sub-category>Get chat history with a specific agent.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["agent_id"],
          properties: {
            agent_id: { type: "string", description: "ID of the agent to get chat history with" },
            limit: { type: "integer", description: "max number of messages to return" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  // ============================================================
  // Cloud Cost Monitoring Tools
  // ============================================================

  addToolSchema({
    name: "aws_read_billing",
    description: "<category>Cloud</category><sub-category>AWS</sub-category>Read AWS billing and cost data.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["period"],
          properties: {
            period: { type: "string", description: "billing period (e.g., 'current_month', 'last_month', or ISO date range)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });

  addToolSchema({
    name: "aws_shutdown",
    description: "<category>Cloud</category><sub-category>AWS</sub-category>Emergency shutdown of AWS resources to control costs.",
    inputSchema: {
      type: "object",
      required: ["input"],
      properties: {
        input: {
          type: "object",
          required: ["resource_type"],
          properties: {
            resource_type: { type: "string", description: "type of AWS resource to shut down (ec2, rds, ecs, etc.)" },
            resource_id: { type: "string", description: "specific resource ID to shut down (optional - shuts down all of type if omitted)" },
          },
        },
      },
    },
    meta: { run_in_cloud: true },
  });



  console.log(`[tools_schema] Built ${toolSchemas.length} cloud MCP tool schemas`);
  return [...toolSchemas];
}

/**
 * Get all tool schemas (builds them if not yet built).
 */
export function get_cloud_mcp_tools_schema() {
  if (toolSchemas.length === 0) {
    build_cloud_mcp_tools_schema();
  }
  return [...toolSchemas];
}
