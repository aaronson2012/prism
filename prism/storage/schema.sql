-- Prism initial schema (v1)

PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS settings (
  guild_id TEXT PRIMARY KEY,
  data_json TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT,
  channel_id TEXT,
  user_id TEXT,
  role TEXT NOT NULL, -- system|user|assistant
  content TEXT NOT NULL,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  token_estimate INTEGER
);

CREATE INDEX IF NOT EXISTS messages_scope_idx
  ON messages(guild_id, channel_id, ts);

CREATE TABLE IF NOT EXISTS emoji_index (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT,
  emoji_id TEXT,
  name TEXT,
  is_custom INTEGER NOT NULL,
  unicode TEXT,
  keywords_json TEXT,
  aliases_json TEXT,
  animated INTEGER DEFAULT 0,
  last_scanned_at TIMESTAMP,
  description TEXT
);

CREATE INDEX IF NOT EXISTS emoji_idx
  ON emoji_index(guild_id, name);

-- Removed user_facts and facts_backfill tables (learning disabled)
