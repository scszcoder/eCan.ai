CREATE TABLE IF NOT EXISTS worker_launch_requests (
  request_id VARCHAR(64) PRIMARY KEY,
  owner_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  run_id TEXT,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS cloud_task_runs (
  owner_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  schedule TEXT NOT NULL DEFAULT '',
  meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(owner_id, task_id)
);
CREATE TABLE IF NOT EXISTS cloud_task_run_history (
  id BIGSERIAL PRIMARY KEY,
  owner_id TEXT NOT NULL,
  task_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  schedule TEXT NOT NULL DEFAULT '',
  meta_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS cloud_task_run_history_owner_task_idx ON cloud_task_run_history(owner_id, task_id, created_at DESC);
