CREATE TABLE IF NOT EXISTS help_requests (
  id INTEGER PRIMARY KEY,
  group_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  target_level TEXT NOT NULL CHECK (target_level IN ('L1', 'L2', 'L3', 'M1', 'M2', 'Doctorat', 'Autre')),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  created_at TEXT NOT NULL,
  closed_at TEXT,
  FOREIGN KEY (group_id) REFERENCES groupes(id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_help_requests_level_status
  ON help_requests(target_level, status, created_at DESC);

CREATE TABLE IF NOT EXISTS help_responses (
  id INTEGER PRIMARY KEY,
  request_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (request_id) REFERENCES help_requests(id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE
);