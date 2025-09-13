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

-- Revamped user_facts schema (destructive create acceptable for dev)
DROP TABLE IF EXISTS user_facts;
CREATE TABLE user_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT,
  user_id TEXT,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  normalized_value TEXT,
  confidence REAL NOT NULL DEFAULT 0.8,
  status TEXT NOT NULL DEFAULT 'candidate', -- candidate|confirmed
  support_count INTEGER NOT NULL DEFAULT 1,
  source TEXT, -- explicit|implicit
  evidence TEXT,
  last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS user_facts_idx
  ON user_facts(guild_id, user_id, key);
CREATE INDEX IF NOT EXISTS user_facts_norm_idx
  ON user_facts(guild_id, user_id, key, normalized_value);

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

CREATE TABLE IF NOT EXISTS reaction_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT,
  channel_id TEXT,
  message_id TEXT,
  emoji TEXT,
  score REAL,
  reason TEXT,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS reaction_log_idx
  ON reaction_log(guild_id, channel_id, ts);

-- Facts backfill progress
CREATE TABLE IF NOT EXISTS facts_backfill (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id TEXT,
  channel_id TEXT,
  last_message_id TEXT,
  processed_count INTEGER DEFAULT 0,
  status TEXT DEFAULT 'idle', -- idle|running|stopped|completed|error
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS facts_backfill_unique
  ON facts_backfill(guild_id, channel_id);
