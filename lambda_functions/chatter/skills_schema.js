/**
 * Cloud Skills Schema for Chatter Lambda
 * 
 * Defines the schema for agent skills that can be referenced in chat.
 * Based on the agent_skills table structure from skillService.js.
 * 
 * Each skill schema describes what a skill is, its fields, and
 * how it can be used or referenced in conversations.
 */

/**
 * Build the cloud skills schema definition.
 * Returns an object with:
 *   - schema: JSON Schema describing a skill object
 *   - fields: field metadata for skill properties
 *   - categories: known skill categories
 */
export function build_cloud_skills_schema() {
  const schema = {
    $schema: "http://json-schema.org/draft-07/schema#",
    title: "AgentSkill",
    description: "Schema for an eCan.ai agent skill definition",
    type: "object",
    required: ["id", "name", "owner"],
    properties: {
      id: {
        type: "string",
        description: "Unique skill identifier (e.g., skill_<hex>)",
        pattern: "^skill_[a-f0-9]+$",
      },
      askid: {
        type: "number",
        description: "Auto-increment numeric skill key",
        default: 0,
      },
      name: {
        type: "string",
        description: "Human-readable skill name",
        maxLength: 255,
      },
      owner: {
        type: "string",
        description: "Owner identifier (email, Cognito sub, or sanitized username)",
      },
      description: {
        type: ["string", "null"],
        description: "Detailed description of what the skill does",
      },
      version: {
        type: "string",
        description: "Semantic version of the skill",
        default: "1.0.0",
        pattern: "^\\d+\\.\\d+\\.\\d+$",
      },
      path: {
        type: ["string", "null"],
        description: "File system path to skill implementation (e.g., /skills/<name>/)",
      },
      source: {
        type: "string",
        description: "How the skill was created",
        enum: ["ui", "code", "import", "scaffold", "template"],
        default: "ui",
      },
      level: {
        type: ["string", "null"],
        description: "Skill complexity level",
        enum: ["basic", "intermediate", "advanced", "expert", null],
      },
      config: {
        type: ["object", "null"],
        description: "Skill configuration object (e.g., LLM settings, timeouts, retry policies)",
        properties: {
          llm_provider: { type: "string", description: "LLM provider (openai, anthropic, google)" },
          llm_model: { type: "string", description: "Model name" },
          temperature: { type: "number", description: "LLM temperature" },
          max_tokens: { type: "integer", description: "Max output tokens" },
          timeout: { type: "integer", description: "Execution timeout in seconds" },
          retry_count: { type: "integer", description: "Number of retries on failure" },
        },
      },
      diagram: {
        type: ["object", "null"],
        description: "Visual flowgram/diagram definition for the skill editor (nodes, edges, layout)",
      },
      tags: {
        type: ["array", "null"],
        items: { type: "string" },
        description: "Tags for categorization and search (e.g., ['rpa', 'browser', 'automation'])",
      },
      examples: {
        type: ["array", "null"],
        items: {
          type: "object",
          properties: {
            input: { type: "string", description: "Example input/prompt" },
            output: { type: "string", description: "Expected output" },
          },
        },
        description: "Usage examples for the skill",
      },
      inputModes: {
        type: ["array", "null"],
        items: {
          type: "string",
          enum: ["text", "image", "file", "audio", "video", "url", "json"],
        },
        description: "Supported input modalities",
      },
      outputModes: {
        type: ["array", "null"],
        items: {
          type: "string",
          enum: ["text", "image", "file", "audio", "video", "url", "json", "chart", "table"],
        },
        description: "Supported output modalities",
      },
      apps: {
        type: ["array", "null"],
        items: { type: "string" },
        description: "OS applications this skill interacts with (e.g., ['chrome', 'excel', 'gmail'])",
      },
      limitations: {
        type: ["array", "null"],
        items: { type: "string" },
        description: "Known limitations or constraints of the skill",
      },
      price: {
        type: "number",
        description: "Price per execution (0 = free)",
        default: 0,
      },
      price_model: {
        type: ["string", "null"],
        description: "Pricing model",
        enum: ["free", "per_run", "per_minute", "monthly", "credits", null],
      },
      public: {
        type: "boolean",
        description: "Whether the skill is publicly visible and usable",
        default: false,
      },
      rentable: {
        type: "boolean",
        description: "Whether the skill can be rented/subscribed to by other users",
        default: false,
      },
    },
  };

  // Field metadata for UI and validation
  const fields = [
    { name: "id",          type: "string",  required: true,  jsonField: false, editable: false,  label: "Skill ID" },
    { name: "askid",       type: "number",  required: false, jsonField: false, editable: false,  label: "Auto Key" },
    { name: "name",        type: "string",  required: true,  jsonField: false, editable: true,   label: "Name" },
    { name: "owner",       type: "string",  required: true,  jsonField: false, editable: false,  label: "Owner" },
    { name: "description", type: "string",  required: false, jsonField: false, editable: true,   label: "Description" },
    { name: "version",     type: "string",  required: false, jsonField: false, editable: true,   label: "Version" },
    { name: "path",        type: "string",  required: false, jsonField: false, editable: true,   label: "Path" },
    { name: "source",      type: "string",  required: false, jsonField: false, editable: true,   label: "Source" },
    { name: "level",       type: "string",  required: false, jsonField: false, editable: true,   label: "Level" },
    { name: "config",      type: "object",  required: false, jsonField: true,  editable: true,   label: "Config" },
    { name: "diagram",     type: "object",  required: false, jsonField: true,  editable: true,   label: "Diagram" },
    { name: "tags",        type: "array",   required: false, jsonField: true,  editable: true,   label: "Tags" },
    { name: "examples",    type: "array",   required: false, jsonField: true,  editable: true,   label: "Examples" },
    { name: "inputModes",  type: "array",   required: false, jsonField: true,  editable: true,   label: "Input Modes" },
    { name: "outputModes", type: "array",   required: false, jsonField: true,  editable: true,   label: "Output Modes" },
    { name: "apps",        type: "array",   required: false, jsonField: true,  editable: true,   label: "Apps" },
    { name: "limitations", type: "array",   required: false, jsonField: true,  editable: true,   label: "Limitations" },
    { name: "price",       type: "number",  required: false, jsonField: false, editable: true,   label: "Price" },
    { name: "price_model", type: "string",  required: false, jsonField: false, editable: true,   label: "Price Model" },
    { name: "public",      type: "boolean", required: false, jsonField: false, editable: true,   label: "Public" },
    { name: "rentable",    type: "boolean", required: false, jsonField: false, editable: true,   label: "Rentable" },
  ];

  // Relationship schemas
  const relationships = {
    skill_tool_rel: {
      description: "Links a skill to a tool it uses",
      table: "agent_skill_tool_rels",
      fields: {
        id: { type: "string", description: "Relationship ID" },
        skill_id: { type: "string", description: "Skill this relationship belongs to" },
        tool_id: { type: "string", description: "Tool the skill uses" },
        dependency_type: {
          type: "string",
          enum: ["required", "optional", "conditional"],
          default: "required",
          description: "How critical this tool is to the skill",
        },
        usage_frequency: {
          type: "string",
          enum: ["low", "medium", "high", "always"],
          default: "medium",
          description: "How often the tool is used during skill execution",
        },
        importance: {
          type: "number",
          default: 1,
          description: "Priority weight (higher = more important)",
        },
        tool_config: {
          type: "object",
          default: {},
          description: "Tool-specific config overrides for this skill",
        },
      },
    },
    skill_knowledge_rel: {
      description: "Links a skill to a knowledge base it accesses",
      table: "agent_skill_knowledge_rels",
      fields: {
        id: { type: "string", description: "Relationship ID" },
        skill_id: { type: "string", description: "Skill this relationship belongs to" },
        knowledge_id: { type: "string", description: "Knowledge base the skill accesses" },
        dependency_type: {
          type: "string",
          enum: ["required", "optional", "conditional"],
          default: "required",
          description: "How critical this knowledge is to the skill",
        },
        access_pattern: {
          type: "string",
          enum: ["read", "write", "read_write"],
          default: "read",
          description: "How the skill accesses the knowledge base",
        },
        knowledge_scope: {
          type: "array",
          items: { type: "string" },
          default: [],
          description: "Scoped topics/sections within the knowledge base",
        },
      },
    },
    agent_skill_rel: {
      description: "Subscription link between an agent and a skill",
      table: "agent_skill_rels",
      fields: {
        id: { type: "string", description: "Relationship ID" },
        agent_id: { type: "string", description: "Agent subscribing to the skill" },
        skill_id: { type: "string", description: "Skill being subscribed to" },
      },
    },
  };

  // Known skill categories for organization
  const categories = [
    { name: "RPA",                description: "Robotic Process Automation workflows" },
    { name: "Browser Automation", description: "Web browser control and interaction" },
    { name: "Data Processing",    description: "Data extraction, transformation, and analysis" },
    { name: "Communication",      description: "Email, chat, and messaging" },
    { name: "Search",             description: "Search engine and database queries" },
    { name: "Code Execution",     description: "Running code and scripts" },
    { name: "File Management",    description: "File and directory operations" },
    { name: "Cloud Operations",   description: "Cloud provider management (AWS, Azure, GCP)" },
    { name: "E-Commerce",         description: "Online marketplace integrations" },
    { name: "RAG",                description: "Retrieval-Augmented Generation" },
    { name: "System",             description: "OS-level operations and process management" },
    { name: "Custom",             description: "User-defined custom skills" },
  ];

  console.log(`[skills_schema] Built cloud skills schema with ${fields.length} fields, ${Object.keys(relationships).length} relationships, ${categories.length} categories`);

  return {
    schema,
    fields,
    relationships,
    categories,
    jsonFields: fields.filter(f => f.jsonField).map(f => f.name),
    editableFields: fields.filter(f => f.editable).map(f => f.name),
    requiredFields: fields.filter(f => f.required).map(f => f.name),
  };
}

/**
 * Get a simplified skill descriptor suitable for LLM context.
 * Pass a skill object and receive a condensed text description.
 */
export function describeSkill(skill) {
  if (!skill) return "No skill provided.";
  const parts = [
    `Skill: ${skill.name || "(unnamed)"}`,
    skill.description ? `Description: ${skill.description}` : null,
    skill.tags?.length ? `Tags: ${skill.tags.join(", ")}` : null,
    skill.level ? `Level: ${skill.level}` : null,
    skill.inputModes?.length ? `Input: ${skill.inputModes.join(", ")}` : null,
    skill.outputModes?.length ? `Output: ${skill.outputModes.join(", ")}` : null,
    skill.apps?.length ? `Apps: ${skill.apps.join(", ")}` : null,
    skill.public ? "Visibility: Public" : "Visibility: Private",
    skill.version ? `Version: ${skill.version}` : null,
  ];
  return parts.filter(Boolean).join("\n");
}

/**
 * Get a simplified list of skill names + descriptions for LLM context.
 */
export function describeSkillList(skills) {
  if (!skills?.length) return "No skills available.";
  return skills.map((s, i) => {
    const tags = s.tags?.length ? ` [${s.tags.join(", ")}]` : "";
    return `${i + 1}. ${s.name}${tags}: ${s.description || "(no description)"}`;
  }).join("\n");
}
