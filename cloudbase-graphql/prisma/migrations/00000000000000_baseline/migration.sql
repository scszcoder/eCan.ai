-- CreateTable
CREATE TABLE "agents" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "gender" TEXT,
    "birthday" TEXT,
    "avatar_resource_id" TEXT,
    "capabilities" JSONB NOT NULL DEFAULT '{}',
    "personalities" JSONB NOT NULL DEFAULT '[]',
    "rank" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "title" JSONB NOT NULL DEFAULT '{}',
    "supervisor_id" TEXT,
    "vehicle_id" TEXT,
    "url" TEXT,
    "version" TEXT,
    "org_id" TEXT,
    "org_ids" JSONB NOT NULL DEFAULT '[]',
    "skills" JSONB NOT NULL DEFAULT '[]',
    "tasks" JSONB NOT NULL DEFAULT '[]',
    "extra_data" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_skills" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "category" TEXT,
    "tags" JSONB NOT NULL DEFAULT '[]',
    "config" JSONB NOT NULL DEFAULT '{}',
    "capabilities" JSONB NOT NULL DEFAULT '[]',
    "limitations" JSONB NOT NULL DEFAULT '[]',
    "examples" JSONB NOT NULL DEFAULT '[]',
    "diagram" JSONB NOT NULL DEFAULT '{}',
    "inputModes" JSONB NOT NULL DEFAULT '["text"]',
    "outputModes" JSONB NOT NULL DEFAULT '["text"]',
    "askid" INTEGER,
    "apps" JSONB NOT NULL DEFAULT '[]',
    "level" TEXT,
    "price" INTEGER NOT NULL DEFAULT 0,
    "price_model" TEXT,
    "source" TEXT,
    "path" TEXT,
    "public" BOOLEAN NOT NULL DEFAULT true,
    "rentable" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'active',
    "version" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_skills_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_tasks" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "priority" TEXT NOT NULL DEFAULT 'normal',
    "task_type" TEXT,
    "trigger_type" TEXT,
    "action" TEXT,
    "duration" INTEGER,
    "org_id" TEXT,
    "objectives" JSONB NOT NULL DEFAULT '[]',
    "result" JSONB NOT NULL DEFAULT '{}',
    "schedule" JSONB NOT NULL DEFAULT '{}',
    "error_message" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_tasks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "vehicles" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "vehicle_type" TEXT,
    "platform" TEXT,
    "architecture" TEXT,
    "environment" TEXT,
    "status" TEXT NOT NULL DEFAULT 'offline',
    "url" TEXT,
    "hostname" TEXT,
    "ip_address" TEXT,
    "port" INTEGER,
    "access_token" TEXT,
    "ssl_enabled" BOOLEAN NOT NULL DEFAULT false,
    "security_level" TEXT,
    "location" TEXT,
    "timezone" TEXT,
    "capabilities" JSONB NOT NULL DEFAULT '{}',
    "limitations" JSONB NOT NULL DEFAULT '{}',
    "settings" JSONB NOT NULL DEFAULT '{}',
    "extra_metadata" JSONB NOT NULL DEFAULT '{}',
    "gpu_info" JSONB NOT NULL DEFAULT '{}',
    "cpu_cores" INTEGER,
    "memory_gb" DOUBLE PRECISION,
    "storage_gb" DOUBLE PRECISION,
    "max_concurrent_tasks" INTEGER,
    "health_score" DOUBLE PRECISION,
    "uptime_seconds" BIGINT,
    "last_heartbeat" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "vehicles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "orgs" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "org_type" TEXT,
    "parent_id" TEXT,
    "level" INTEGER NOT NULL DEFAULT 0,
    "sort_order" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'active',
    "settings" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "orgs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "prompts" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "prompt" JSONB NOT NULL,
    "version" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "prompts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "avatars" (
    "id" TEXT NOT NULL,
    "owner" TEXT,
    "name" TEXT,
    "description" TEXT,
    "resource_type" TEXT NOT NULL,
    "image_path" TEXT,
    "video_path" TEXT,
    "image_hash" TEXT,
    "video_hash" TEXT,
    "cloud_image_key" TEXT,
    "cloud_video_key" TEXT,
    "cloud_image_url" TEXT,
    "cloud_video_url" TEXT,
    "cloud_synced" BOOLEAN NOT NULL DEFAULT false,
    "avatar_metadata" JSONB NOT NULL DEFAULT '{}',
    "is_public" BOOLEAN NOT NULL DEFAULT false,
    "usage_count" INTEGER NOT NULL DEFAULT 0,
    "last_used_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "avatars_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_knowledge" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "content" TEXT,
    "knowledge_type" TEXT,
    "categories" JSONB NOT NULL DEFAULT '[]',
    "tags" JSONB NOT NULL DEFAULT '[]',
    "access_methods" JSONB NOT NULL DEFAULT '[]',
    "limitations" JSONB NOT NULL DEFAULT '[]',
    "level" INTEGER,
    "price" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "price_model" TEXT,
    "path" TEXT,
    "public" BOOLEAN NOT NULL DEFAULT false,
    "rentable" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'active',
    "settings" JSONB NOT NULL DEFAULT '{}',
    "config" JSONB NOT NULL DEFAULT '{}',
    "version" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_knowledge_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_tools" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "tool_type" TEXT,
    "capabilities" JSONB NOT NULL DEFAULT '[]',
    "limitations" JSONB NOT NULL DEFAULT '[]',
    "dependencies" JSONB NOT NULL DEFAULT '[]',
    "settings" JSONB NOT NULL DEFAULT '{}',
    "config" JSONB NOT NULL DEFAULT '{}',
    "level" INTEGER,
    "price" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "price_model" TEXT,
    "path" TEXT,
    "public" BOOLEAN NOT NULL DEFAULT false,
    "rentable" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'active',
    "version" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_tools_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "settings" (
    "id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "value" JSONB NOT NULL,
    "owner" TEXT NOT NULL DEFAULT '__global__',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "settings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_skill_rels" (
    "id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "proficiency_level" INTEGER NOT NULL DEFAULT 0,
    "experience_points" INTEGER NOT NULL DEFAULT 0,
    "certification_level" INTEGER NOT NULL DEFAULT 0,
    "usage_count" INTEGER NOT NULL DEFAULT 0,
    "success_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "last_used" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'active',
    "is_favorite" BOOLEAN NOT NULL DEFAULT false,
    "priority" INTEGER NOT NULL DEFAULT 0,
    "config" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_skill_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_task_rels" (
    "id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "vehicle_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'assigned',
    "priority" INTEGER NOT NULL DEFAULT 0,
    "progress" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "scheduled_start" TIMESTAMP(3),
    "actual_start" TIMESTAMP(3),
    "estimated_end" TIMESTAMP(3),
    "actual_end" TIMESTAMP(3),
    "result" JSONB NOT NULL DEFAULT '{}',
    "error_message" TEXT,
    "logs" TEXT,
    "cpu_usage" DOUBLE PRECISION,
    "memory_usage" DOUBLE PRECISION,
    "execution_time" DOUBLE PRECISION,
    "execution_context" JSONB NOT NULL DEFAULT '{}',
    "retry_count" INTEGER NOT NULL DEFAULT 0,
    "max_retries" INTEGER NOT NULL DEFAULT 3,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_task_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_tool_rels" (
    "id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "tool_id" TEXT NOT NULL,
    "permission" TEXT,
    "granted_at" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'active',
    "config" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_tool_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_org_rels" (
    "id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "org_id" TEXT NOT NULL,
    "role" TEXT,
    "access_level" TEXT NOT NULL DEFAULT 'member',
    "status" TEXT NOT NULL DEFAULT 'active',
    "permissions" JSONB NOT NULL DEFAULT '[]',
    "join_date" TIMESTAMP(3),
    "leave_date" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_org_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_skill_tool_rels" (
    "id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "tool_id" TEXT NOT NULL,
    "dependency_type" TEXT,
    "usage_frequency" INTEGER NOT NULL DEFAULT 0,
    "importance" INTEGER NOT NULL DEFAULT 0,
    "tool_config" JSONB NOT NULL DEFAULT '{}',
    "parameters" JSONB NOT NULL DEFAULT '{}',
    "usage_count" INTEGER NOT NULL DEFAULT 0,
    "success_rate" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "last_used" TIMESTAMP(3),
    "status" TEXT NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_skill_tool_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_skill_knowledge_rels" (
    "id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "knowledge_id" TEXT NOT NULL,
    "dependency_type" TEXT,
    "usage_frequency" INTEGER NOT NULL DEFAULT 0,
    "importance" INTEGER NOT NULL DEFAULT 0,
    "access_pattern" TEXT,
    "knowledge_scope" JSONB NOT NULL DEFAULT '{}',
    "access_count" INTEGER NOT NULL DEFAULT 0,
    "last_accessed" TIMESTAMP(3),
    "average_query_time" DOUBLE PRECISION,
    "status" TEXT NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_skill_knowledge_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_task_skill_rels" (
    "id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "role" TEXT,
    "execution_order" INTEGER NOT NULL DEFAULT 0,
    "is_required" BOOLEAN NOT NULL DEFAULT true,
    "skill_config" JSONB NOT NULL DEFAULT '{}',
    "parameters" JSONB NOT NULL DEFAULT '{}',
    "constraints_json" JSONB NOT NULL DEFAULT '{}',
    "estimated_duration" DOUBLE PRECISION,
    "estimated_cost" DOUBLE PRECISION,
    "resource_requirements" JSONB NOT NULL DEFAULT '{}',
    "success_criteria" JSONB NOT NULL DEFAULT '{}',
    "quality_threshold" DOUBLE PRECISION,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "actual_duration" DOUBLE PRECISION,
    "actual_cost" DOUBLE PRECISION,
    "quality_score" DOUBLE PRECISION,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_task_skill_rels_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skill_editor_events" (
    "eventId" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "flowgram_id" TEXT,
    "event_type" TEXT NOT NULL,
    "payload" JSONB NOT NULL DEFAULT '{}',
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "skill_editor_events_pkey" PRIMARY KEY ("eventId")
);

-- CreateTable
CREATE TABLE "worker_launch_requests" (
    "request_id" TEXT NOT NULL,
    "owner_id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "run_id" TEXT,
    "error" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "worker_launch_requests_pkey" PRIMARY KEY ("request_id")
);

-- CreateTable
CREATE TABLE "cloud_task_runs" (
    "owner_id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "run_id" TEXT NOT NULL,
    "schedule" TEXT NOT NULL DEFAULT '',
    "meta_data" JSONB NOT NULL DEFAULT '{}',
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "cloud_task_runs_pkey" PRIMARY KEY ("owner_id","task_id")
);

-- CreateTable
CREATE TABLE "cloud_task_run_history" (
    "id" BIGSERIAL NOT NULL,
    "owner_id" TEXT NOT NULL,
    "task_id" TEXT NOT NULL,
    "run_id" TEXT NOT NULL,
    "schedule" TEXT NOT NULL DEFAULT '',
    "meta_data" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "cloud_task_run_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "agent_endpoints" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "machine_id" TEXT NOT NULL,
    "org" TEXT NOT NULL,
    "name" TEXT,
    "role" TEXT,
    "skills" TEXT,
    "skills_hash" TEXT,
    "a2a_relay_channel" TEXT NOT NULL,
    "lan_hint" TEXT,
    "ecan_ver" TEXT,
    "os" TEXT,
    "last_seen" BIGINT NOT NULL,
    "ttl" INTEGER NOT NULL DEFAULT 180,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_endpoints_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "a2a_messages" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "to_agent_id" TEXT NOT NULL,
    "from_agent_id" TEXT NOT NULL,
    "org" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "a2a_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "rag_documents" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "fid" TEXT NOT NULL,
    "pid" TEXT NOT NULL,
    "file" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "format" TEXT NOT NULL,
    "options" JSONB NOT NULL,
    "version" TEXT NOT NULL,
    "object_key" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "rag_documents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "long_llm_tasks" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "acct_site_id" TEXT,
    "agent_id" TEXT,
    "work_type" TEXT,
    "task_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "input" JSONB NOT NULL DEFAULT '{}',
    "results" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "long_llm_tasks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skill_editor_chat_sessions" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "flowgram_id" TEXT,
    "state" TEXT NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "skill_editor_chat_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skill_editor_chat_messages" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "attachments" JSONB NOT NULL DEFAULT '[]',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "skill_editor_chat_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "legacy_records" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "kind" TEXT NOT NULL,
    "external_id" TEXT NOT NULL,
    "data" JSONB NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "legacy_records_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "wan_messages" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "chat_id" TEXT,
    "sender" TEXT,
    "receiver" TEXT,
    "type" TEXT,
    "contents" TEXT,
    "parameters" TEXT,
    "timestamp" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "wan_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "api_credentials" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "key_hash" TEXT NOT NULL,
    "key_prefix" TEXT NOT NULL,
    "label" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revoked_at" TIMESTAMP(3),

    CONSTRAINT "api_credentials_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "agents_owner_idx" ON "agents"("owner");

-- CreateIndex
CREATE INDEX "agents_status_idx" ON "agents"("status");

-- CreateIndex
CREATE INDEX "agents_org_id_idx" ON "agents"("org_id");

-- CreateIndex
CREATE INDEX "agent_skills_owner_idx" ON "agent_skills"("owner");

-- CreateIndex
CREATE INDEX "agent_skills_name_idx" ON "agent_skills"("name");

-- CreateIndex
CREATE INDEX "agent_skills_category_idx" ON "agent_skills"("category");

-- CreateIndex
CREATE INDEX "agent_skills_public_idx" ON "agent_skills"("public");

-- CreateIndex
CREATE INDEX "agent_tasks_owner_idx" ON "agent_tasks"("owner");

-- CreateIndex
CREATE INDEX "agent_tasks_status_idx" ON "agent_tasks"("status");

-- CreateIndex
CREATE INDEX "agent_tasks_priority_idx" ON "agent_tasks"("priority");

-- CreateIndex
CREATE INDEX "vehicles_owner_idx" ON "vehicles"("owner");

-- CreateIndex
CREATE INDEX "vehicles_status_idx" ON "vehicles"("status");

-- CreateIndex
CREATE INDEX "orgs_parent_id_idx" ON "orgs"("parent_id");

-- CreateIndex
CREATE INDEX "orgs_level_idx" ON "orgs"("level");

-- CreateIndex
CREATE INDEX "prompts_owner_idx" ON "prompts"("owner");

-- CreateIndex
CREATE INDEX "avatars_owner_idx" ON "avatars"("owner");

-- CreateIndex
CREATE INDEX "avatars_resource_type_idx" ON "avatars"("resource_type");

-- CreateIndex
CREATE INDEX "agent_knowledge_owner_idx" ON "agent_knowledge"("owner");

-- CreateIndex
CREATE INDEX "agent_knowledge_name_idx" ON "agent_knowledge"("name");

-- CreateIndex
CREATE INDEX "agent_knowledge_knowledge_type_idx" ON "agent_knowledge"("knowledge_type");

-- CreateIndex
CREATE INDEX "agent_tools_owner_idx" ON "agent_tools"("owner");

-- CreateIndex
CREATE INDEX "settings_owner_idx" ON "settings"("owner");

-- CreateIndex
CREATE UNIQUE INDEX "settings_owner_key_key" ON "settings"("owner", "key");

-- CreateIndex
CREATE INDEX "agent_skill_rels_agent_id_idx" ON "agent_skill_rels"("agent_id");

-- CreateIndex
CREATE INDEX "agent_skill_rels_skill_id_idx" ON "agent_skill_rels"("skill_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_skill_rels_agent_id_skill_id_key" ON "agent_skill_rels"("agent_id", "skill_id");

-- CreateIndex
CREATE INDEX "agent_task_rels_agent_id_idx" ON "agent_task_rels"("agent_id");

-- CreateIndex
CREATE INDEX "agent_task_rels_task_id_idx" ON "agent_task_rels"("task_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_task_rels_agent_id_task_id_key" ON "agent_task_rels"("agent_id", "task_id");

-- CreateIndex
CREATE INDEX "agent_tool_rels_agent_id_idx" ON "agent_tool_rels"("agent_id");

-- CreateIndex
CREATE INDEX "agent_tool_rels_tool_id_idx" ON "agent_tool_rels"("tool_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_tool_rels_agent_id_tool_id_key" ON "agent_tool_rels"("agent_id", "tool_id");

-- CreateIndex
CREATE INDEX "agent_org_rels_agent_id_idx" ON "agent_org_rels"("agent_id");

-- CreateIndex
CREATE INDEX "agent_org_rels_org_id_idx" ON "agent_org_rels"("org_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_org_rels_agent_id_org_id_key" ON "agent_org_rels"("agent_id", "org_id");

-- CreateIndex
CREATE INDEX "agent_skill_tool_rels_skill_id_idx" ON "agent_skill_tool_rels"("skill_id");

-- CreateIndex
CREATE INDEX "agent_skill_tool_rels_tool_id_idx" ON "agent_skill_tool_rels"("tool_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_skill_tool_rels_skill_id_tool_id_key" ON "agent_skill_tool_rels"("skill_id", "tool_id");

-- CreateIndex
CREATE INDEX "agent_skill_knowledge_rels_skill_id_idx" ON "agent_skill_knowledge_rels"("skill_id");

-- CreateIndex
CREATE INDEX "agent_skill_knowledge_rels_knowledge_id_idx" ON "agent_skill_knowledge_rels"("knowledge_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_skill_knowledge_rels_skill_id_knowledge_id_key" ON "agent_skill_knowledge_rels"("skill_id", "knowledge_id");

-- CreateIndex
CREATE INDEX "agent_task_skill_rels_task_id_idx" ON "agent_task_skill_rels"("task_id");

-- CreateIndex
CREATE INDEX "agent_task_skill_rels_skill_id_idx" ON "agent_task_skill_rels"("skill_id");

-- CreateIndex
CREATE UNIQUE INDEX "agent_task_skill_rels_task_id_skill_id_key" ON "agent_task_skill_rels"("task_id", "skill_id");

-- CreateIndex
CREATE INDEX "skill_editor_events_session_id_idx" ON "skill_editor_events"("session_id");

-- CreateIndex
CREATE INDEX "skill_editor_events_owner_session_id_idx" ON "skill_editor_events"("owner", "session_id");

-- CreateIndex
CREATE INDEX "skill_editor_events_owner_idx" ON "skill_editor_events"("owner");

-- CreateIndex
CREATE INDEX "skill_editor_events_flowgram_id_idx" ON "skill_editor_events"("flowgram_id");

-- CreateIndex
CREATE INDEX "skill_editor_events_timestamp_idx" ON "skill_editor_events"("timestamp" DESC);

-- CreateIndex
CREATE INDEX "worker_launch_requests_owner_id_task_id_idx" ON "worker_launch_requests"("owner_id", "task_id");

-- CreateIndex
CREATE INDEX "cloud_task_run_history_owner_id_task_id_created_at_idx" ON "cloud_task_run_history"("owner_id", "task_id", "created_at" DESC);

-- CreateIndex
CREATE INDEX "agent_endpoints_owner_org_idx" ON "agent_endpoints"("owner", "org");

-- CreateIndex
CREATE INDEX "agent_endpoints_org_last_seen_idx" ON "agent_endpoints"("org", "last_seen");

-- CreateIndex
CREATE INDEX "a2a_messages_owner_to_agent_id_timestamp_idx" ON "a2a_messages"("owner", "to_agent_id", "timestamp" DESC);

-- CreateIndex
CREATE INDEX "rag_documents_owner_pid_idx" ON "rag_documents"("owner", "pid");

-- CreateIndex
CREATE UNIQUE INDEX "rag_documents_owner_pid_fid_key" ON "rag_documents"("owner", "pid", "fid");

-- CreateIndex
CREATE INDEX "long_llm_tasks_owner_status_idx" ON "long_llm_tasks"("owner", "status");

-- CreateIndex
CREATE INDEX "skill_editor_chat_sessions_owner_updated_at_idx" ON "skill_editor_chat_sessions"("owner", "updated_at" DESC);

-- CreateIndex
CREATE INDEX "skill_editor_chat_messages_owner_session_id_timestamp_idx" ON "skill_editor_chat_messages"("owner", "session_id", "timestamp");

-- CreateIndex
CREATE INDEX "legacy_records_owner_kind_idx" ON "legacy_records"("owner", "kind");

-- CreateIndex
CREATE UNIQUE INDEX "legacy_records_owner_kind_external_id_key" ON "legacy_records"("owner", "kind", "external_id");

-- CreateIndex
CREATE INDEX "wan_messages_owner_chat_id_timestamp_idx" ON "wan_messages"("owner", "chat_id", "timestamp" DESC);

-- CreateIndex
CREATE UNIQUE INDEX "api_credentials_key_hash_key" ON "api_credentials"("key_hash");

-- CreateIndex
CREATE INDEX "api_credentials_owner_status_idx" ON "api_credentials"("owner", "status");

-- AddForeignKey
ALTER TABLE "agent_skill_rels" ADD CONSTRAINT "agent_skill_rels_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_skill_rels" ADD CONSTRAINT "agent_skill_rels_skill_id_fkey" FOREIGN KEY ("skill_id") REFERENCES "agent_skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_task_rels" ADD CONSTRAINT "agent_task_rels_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_task_rels" ADD CONSTRAINT "agent_task_rels_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "agent_tasks"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_tool_rels" ADD CONSTRAINT "agent_tool_rels_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_tool_rels" ADD CONSTRAINT "agent_tool_rels_tool_id_fkey" FOREIGN KEY ("tool_id") REFERENCES "agent_tools"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_org_rels" ADD CONSTRAINT "agent_org_rels_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_org_rels" ADD CONSTRAINT "agent_org_rels_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "orgs"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_skill_tool_rels" ADD CONSTRAINT "agent_skill_tool_rels_skill_id_fkey" FOREIGN KEY ("skill_id") REFERENCES "agent_skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_skill_tool_rels" ADD CONSTRAINT "agent_skill_tool_rels_tool_id_fkey" FOREIGN KEY ("tool_id") REFERENCES "agent_tools"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_skill_knowledge_rels" ADD CONSTRAINT "agent_skill_knowledge_rels_skill_id_fkey" FOREIGN KEY ("skill_id") REFERENCES "agent_skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_skill_knowledge_rels" ADD CONSTRAINT "agent_skill_knowledge_rels_knowledge_id_fkey" FOREIGN KEY ("knowledge_id") REFERENCES "agent_knowledge"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_task_skill_rels" ADD CONSTRAINT "agent_task_skill_rels_task_id_fkey" FOREIGN KEY ("task_id") REFERENCES "agent_tasks"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "agent_task_skill_rels" ADD CONSTRAINT "agent_task_skill_rels_skill_id_fkey" FOREIGN KEY ("skill_id") REFERENCES "agent_skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "skill_editor_chat_messages" ADD CONSTRAINT "skill_editor_chat_messages_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "skill_editor_chat_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

