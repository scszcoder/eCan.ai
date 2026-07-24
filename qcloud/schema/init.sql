-- 腾讯云 TDSQL-C 数据库初始化脚本
-- 与 AWS Aurora MySQL 100% 兼容
-- 复用 lambda_functions/agentScheduler/schema/agents.sql 表结构

CREATE TABLE IF NOT EXISTS avatar_resources (
  id               VARCHAR(64) PRIMARY KEY,
  resource_type    VARCHAR(32) NOT NULL,
  name             VARCHAR(128),
  description      VARCHAR(512),
  image_path       VARCHAR(512),
  video_path       VARCHAR(512),
  image_hash       VARCHAR(64),
  video_hash       VARCHAR(64),
  cloud_image_url  VARCHAR(512),
  cloud_video_url  VARCHAR(512),
  cloud_image_key  VARCHAR(512),
  cloud_video_key  VARCHAR(512),
  cloud_synced     BOOLEAN DEFAULT FALSE,
  avatar_metadata  JSON,
  usage_count      INT DEFAULT 0,
  last_used_at     DATETIME(6),
  owner            VARCHAR(128),
  is_public        BOOLEAN DEFAULT FALSE,
  created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_orgs (
  id          VARCHAR(64) PRIMARY KEY,
  name        VARCHAR(128) NOT NULL,
  description TEXT,
  parent_id   VARCHAR(64),
  org_type    VARCHAR(64) DEFAULT 'department',
  level       INT DEFAULT 0,
  sort_order  INT DEFAULT 0,
  status      VARCHAR(32) DEFAULT 'active',
  settings    JSON,
  created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agents (
  id                 VARCHAR(64) PRIMARY KEY,
  name               VARCHAR(128) NOT NULL,
  description        TEXT,
  owner              VARCHAR(128) NOT NULL,
  gender             VARCHAR(32) DEFAULT 'male',
  title              JSON,
  rank               VARCHAR(64),
  birthday           VARCHAR(32),
  supervisor_id      VARCHAR(64),
  personalities      JSON,
  capabilities       JSON,
  status             VARCHAR(32) DEFAULT 'active',
  version            VARCHAR(64),
  url                VARCHAR(512),
  vehicle_id         VARCHAR(64),
  avatar_resource_id VARCHAR(64),
  extra_data         JSON,
  created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  deleted_at         DATETIME(6),
  upgraded_at        DATETIME(6)
);

CREATE TABLE IF NOT EXISTS agent_skills (
  id            VARCHAR(64) PRIMARY KEY,
  askid         BIGINT DEFAULT 0,
  name          VARCHAR(128) NOT NULL,
  owner         VARCHAR(128) NOT NULL,
  skill_owner   VARCHAR(128),
  description   TEXT,
  version       VARCHAR(128) NOT NULL,
  path          TEXT,
  source        VARCHAR(512) DEFAULT 'ui',
  level         VARCHAR(64),
  config        JSON,
  diagram       JSON,
  tags          JSON,
  examples      JSON,
  inputModes    JSON,
  outputModes   JSON,
  apps          JSON,
  limitations   JSON,
  price         INT DEFAULT 0,
  price_model   TEXT,
  public        BOOLEAN DEFAULT FALSE,
  rentable      BOOLEAN DEFAULT FALSE,
  created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  deleted_at    DATETIME(6)
);

CREATE TABLE IF NOT EXISTS agent_tasks (
  id            VARCHAR(64) PRIMARY KEY,
  name          VARCHAR(128) NOT NULL,
  description   TEXT,
  owner         VARCHAR(128) NOT NULL,
  source        VARCHAR(32) DEFAULT 'ui',
  org_id        VARCHAR(64),
  priority      VARCHAR(32) DEFAULT 'medium',
  status        VARCHAR(32) DEFAULT 'pending',
  task_type     VARCHAR(64),
  objectives    JSON,
  schedule      JSON,
  trigger       VARCHAR(64),
  progress      DOUBLE DEFAULT 0.0,
  result        JSON,
  error_message TEXT,
  metadata      JSON,
  created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_tools (
  id            VARCHAR(64) PRIMARY KEY,
  name          VARCHAR(128) NOT NULL,
  description   TEXT,
  owner         VARCHAR(128) NOT NULL,
  tool_type     VARCHAR(64),
  version       VARCHAR(64),
  path          TEXT,
  level         INT DEFAULT 1,
  config        JSON,
  capabilities  JSON,
  limitations   JSON,
  dependencies  JSON,
  public        BOOLEAN DEFAULT FALSE,
  rentable      BOOLEAN DEFAULT FALSE,
  price         DOUBLE DEFAULT 0.0,
  price_model   VARCHAR(32),
  status        VARCHAR(32) DEFAULT 'active',
  settings      JSON,
  created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_knowledges (
  id              VARCHAR(64) PRIMARY KEY,
  name            VARCHAR(128) NOT NULL,
  description     TEXT,
  owner           VARCHAR(128) NOT NULL,
  knowledge_type  VARCHAR(64),
  version         VARCHAR(64),
  path            TEXT,
  level           INT DEFAULT 1,
  content         TEXT,
  tags            JSON,
  categories      JSON,
  config          JSON,
  access_methods  JSON,
  limitations     JSON,
  public          BOOLEAN DEFAULT FALSE,
  rentable        BOOLEAN DEFAULT FALSE,
  price           DOUBLE DEFAULT 0.0,
  price_model     VARCHAR(32),
  status          VARCHAR(32) DEFAULT 'active',
  settings        JSON,
  created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_vehicles (
  id                VARCHAR(64) PRIMARY KEY,
  name              VARCHAR(128) NOT NULL,
  description       TEXT,
  owner             VARCHAR(128) NOT NULL,
  vehicle_type      VARCHAR(64) DEFAULT 'desktop',
  platform          VARCHAR(64),
  architecture      VARCHAR(32),
  ip_address        VARCHAR(45),
  hostname          VARCHAR(128),
  port              INT,
  url               VARCHAR(512),
  cpu_cores         INT,
  memory_gb         DOUBLE,
  storage_gb        DOUBLE,
  gpu_info          JSON,
  status            VARCHAR(32) DEFAULT 'offline',
  health_score      DOUBLE DEFAULT 1.0,
  last_heartbeat    DATETIME(6),
  uptime_seconds    INT DEFAULT 0,
  capabilities      JSON,
  limitations       JSON,
  max_concurrent_tasks INT DEFAULT 1,
  location          VARCHAR(128),
  timezone          VARCHAR(64),
  environment       VARCHAR(64) DEFAULT 'production',
  security_level    VARCHAR(32) DEFAULT 'standard',
  access_token      VARCHAR(512),
  ssl_enabled       BOOLEAN DEFAULT TRUE,
  settings          JSON,
  extra_metadata    JSON,
  created_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_org_rels (
  id           VARCHAR(64) PRIMARY KEY,
  agent_id     VARCHAR(64) NOT NULL,
  org_id       VARCHAR(64) NOT NULL,
  role         VARCHAR(64) DEFAULT 'member',
  status       VARCHAR(32) DEFAULT 'active',
  join_date    DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
  leave_date   DATETIME(6),
  permissions  JSON,
  access_level VARCHAR(32) DEFAULT 'read',
  created_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at   DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uc_agent_org (agent_id, org_id)
);

CREATE TABLE IF NOT EXISTS agent_skill_rels (
  id                 VARCHAR(64) PRIMARY KEY,
  agent_id           VARCHAR(64) NOT NULL,
  skill_id           VARCHAR(64) NOT NULL,
  proficiency_level  VARCHAR(32) DEFAULT 'beginner',
  experience_points  INT DEFAULT 0,
  certification_level VARCHAR(32),
  usage_count        INT DEFAULT 0,
  success_rate       DOUBLE DEFAULT 0.0,
  last_used          DATETIME(6),
  status             VARCHAR(32) DEFAULT 'active',
  is_favorite        BOOLEAN DEFAULT FALSE,
  priority           INT DEFAULT 0,
  created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uc_agent_skill (agent_id, skill_id)
);

CREATE TABLE IF NOT EXISTS agent_task_rels (
  id                 VARCHAR(64) PRIMARY KEY,
  agent_id           VARCHAR(64) NOT NULL,
  task_id            VARCHAR(64) NOT NULL,
  vehicle_id         VARCHAR(64),
  status             VARCHAR(32) DEFAULT 'pending',
  priority           VARCHAR(32) DEFAULT 'medium',
  progress           DOUBLE DEFAULT 0.0,
  scheduled_start    DATETIME(6),
  actual_start       DATETIME(6),
  estimated_end      DATETIME(6),
  actual_end         DATETIME(6),
  result             JSON,
  error_message      TEXT,
  logs               TEXT,
  cpu_usage          DOUBLE,
  memory_usage       DOUBLE,
  execution_time     DOUBLE,
  execution_context  JSON,
  retry_count        INT DEFAULT 0,
  max_retries        INT DEFAULT 3,
  created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS agent_skill_tool_rels (
  id               VARCHAR(64) PRIMARY KEY,
  skill_id         VARCHAR(64) NOT NULL,
  tool_id          VARCHAR(64) NOT NULL,
  dependency_type  VARCHAR(32) DEFAULT 'required',
  usage_frequency  VARCHAR(32) DEFAULT 'medium',
  importance       INT DEFAULT 1,
  tool_config      JSON,
  parameters       JSON,
  usage_count      INT DEFAULT 0,
  success_rate     DOUBLE DEFAULT 0.0,
  last_used        DATETIME(6),
  status           VARCHAR(32) DEFAULT 'active',
  created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uc_skill_tool (skill_id, tool_id)
);

CREATE TABLE IF NOT EXISTS agent_skill_knowledge_rels (
  id               VARCHAR(64) PRIMARY KEY,
  skill_id         VARCHAR(64) NOT NULL,
  knowledge_id     VARCHAR(64) NOT NULL,
  dependency_type  VARCHAR(32) DEFAULT 'required',
  usage_frequency  VARCHAR(32) DEFAULT 'medium',
  importance       INT DEFAULT 1,
  access_pattern   VARCHAR(32) DEFAULT 'read',
  knowledge_scope  JSON,
  access_count     INT DEFAULT 0,
  last_accessed    DATETIME(6),
  average_query_time DOUBLE DEFAULT 0.0,
  status           VARCHAR(32) DEFAULT 'active',
  created_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uc_skill_knowledge (skill_id, knowledge_id)
);

CREATE TABLE IF NOT EXISTS agent_task_skill_rels (
  id                 VARCHAR(64) PRIMARY KEY,
  task_id            VARCHAR(64) NOT NULL,
  skill_id           VARCHAR(64) NOT NULL,
  role               VARCHAR(32) DEFAULT 'primary',
  execution_order    INT DEFAULT 0,
  is_required        BOOLEAN DEFAULT TRUE,
  skill_config       JSON,
  parameters         JSON,
  constraints_json   JSON,
  estimated_duration DOUBLE,
  estimated_cost     DOUBLE,
  resource_requirements JSON,
  success_criteria   JSON,
  quality_threshold  DOUBLE DEFAULT 0.8,
  status             VARCHAR(32) DEFAULT 'pending',
  actual_duration    DOUBLE,
  actual_cost        DOUBLE,
  quality_score      DOUBLE,
  created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  UNIQUE KEY uc_task_skill (task_id, skill_id)
);

CREATE TABLE IF NOT EXISTS agent_skill_versions (
  id          VARCHAR(64) PRIMARY KEY,
  skill_id    VARCHAR(64) NOT NULL,
  version     VARCHAR(64) NOT NULL,
  snapshot    JSON NOT NULL,
  changelog   TEXT,
  created_by  VARCHAR(128),
  created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_skill_versions_skill (skill_id),
  INDEX idx_skill_versions_created (created_at DESC)
);

CREATE TABLE IF NOT EXISTS stories (
  id          VARCHAR(64) PRIMARY KEY,
  owner       VARCHAR(128) NOT NULL,
  name        VARCHAR(128),
  description TEXT,
  content     JSON,
  metadata    JSON,
  status      VARCHAR(32) DEFAULT 'draft',
  tags        JSON,
  created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS settings (
  key         VARCHAR(128) PRIMARY KEY,
  value       JSON,
  description VARCHAR(512),
  created_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at  DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)
);

CREATE TABLE IF NOT EXISTS cloud_task_runs (
  id              VARCHAR(64) PRIMARY KEY,
  owner_id        VARCHAR(128) NOT NULL,
  task_id         VARCHAR(64) NOT NULL,
  run_id          VARCHAR(256),
  status          VARCHAR(32) DEFAULT 'pending',
  started_at      DATETIME(6),
  completed_at    DATETIME(6),
  schedule        VARCHAR(128),
  meta_data       JSON,
  error_message   TEXT,
  created_at      DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_task_runs_owner (owner_id),
  INDEX idx_task_runs_task (task_id),
  INDEX idx_task_runs_status (status)
);

CREATE TABLE IF NOT EXISTS api_keys (
  id            VARCHAR(64) PRIMARY KEY,
  owner         VARCHAR(128) NOT NULL,
  key_hash      VARCHAR(128) NOT NULL UNIQUE,
  key_prefix    VARCHAR(16) NOT NULL,
  name          VARCHAR(128),
  description   VARCHAR(512),
  permissions   JSON,
  expires_at    DATETIME(6),
  last_used_at  DATETIME(6),
  usage_count   INT DEFAULT 0,
  created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_api_keys_owner (owner),
  INDEX idx_api_keys_hash (key_hash)
);

CREATE TABLE IF NOT EXISTS prompts (
  id            VARCHAR(64) PRIMARY KEY,
  owner         VARCHAR(128) NOT NULL,
  name          VARCHAR(128) NOT NULL,
  description   TEXT,
  content       TEXT,
  version       VARCHAR(64) DEFAULT '1.0.0',
  tags          JSON,
  metadata      JSON,
  created_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  updated_at    DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  INDEX idx_prompts_owner (owner),
  INDEX idx_prompts_name (name)
);

-- 索引
CREATE INDEX idx_agent_skills_owner_public ON agent_skills(owner, public, updated_at);
CREATE INDEX idx_agent_skills_public_updated ON agent_skills(public, updated_at DESC);
CREATE INDEX idx_agent_skills_source ON agent_skills(source);
CREATE INDEX idx_agent_skill_rels_agent_status ON agent_skill_rels(agent_id, status);
CREATE INDEX idx_agent_skill_rels_skill_status ON agent_skill_rels(skill_id, status);
CREATE INDEX idx_agent_org_rels_org ON agent_org_rels(org_id);
CREATE INDEX idx_agent_org_rels_agent ON agent_org_rels(agent_id);
CREATE INDEX idx_agent_tasks_owner_status ON agent_tasks(owner, status);
CREATE INDEX idx_agent_tasks_org ON agent_tasks(org_id);
CREATE INDEX idx_agent_vehicles_owner_status ON agent_vehicles(owner, status);
CREATE INDEX idx_agent_vehicles_ip ON agent_vehicles(ip_address);
CREATE INDEX idx_agents_owner ON agents(owner);
CREATE INDEX idx_agents_status ON agents(status);
CREATE INDEX idx_cloud_task_runs_owner_task ON cloud_task_runs(owner_id, task_id);
