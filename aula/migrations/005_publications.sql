CREATE TABLE IF NOT EXISTS publications (
  id INTEGER PRIMARY KEY,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  link_url TEXT,
  file_id INTEGER,
  status TEXT NOT NULL DEFAULT 'published'
    CHECK (status IN ('published', 'reported', 'rejected')),
  created_at TEXT NOT NULL,
  edited_at TEXT,
  deleted_at TEXT,
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS publication_comments (
  id INTEGER PRIMARY KEY,
  publication_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  body TEXT NOT NULL,
  parent_id INTEGER,
  created_at TEXT NOT NULL,
  edited_at TEXT,
  deleted_at TEXT,
  FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (parent_id) REFERENCES publication_comments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publication_reactions (
  publication_id INTEGER NOT NULL,
  user_id INTEGER NOT NULL,
  emoji TEXT NOT NULL,
  PRIMARY KEY (publication_id, user_id, emoji),
  FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publication_reports (
  id INTEGER PRIMARY KEY,
  reporter_id INTEGER NOT NULL,
  publication_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'resolved', 'dismissed')),
  admin_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolver_id INTEGER,
  FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE,
  FOREIGN KEY (resolver_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_publications_status
  ON publications(status, created_at);
CREATE INDEX IF NOT EXISTS idx_publication_comments_publication
  ON publication_comments(publication_id, id);
