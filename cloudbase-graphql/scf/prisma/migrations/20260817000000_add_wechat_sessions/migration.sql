CREATE TABLE IF NOT EXISTS wechat_sessions (
  id TEXT PRIMARY KEY,
  openid TEXT NOT NULL UNIQUE,
  session_token TEXT NOT NULL,
  wx_access_token TEXT,
  owner TEXT NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  last_refreshed TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS wechat_sessions_owner_idx ON wechat_sessions (owner);
CREATE INDEX IF NOT EXISTS wechat_sessions_expires_at_idx ON wechat_sessions (expires_at);