ALTER TABLE groupes ADD COLUMN preferred_level TEXT NOT NULL DEFAULT '';
ALTER TABLE groupes ADD COLUMN recruitment_open INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN discoverable INTEGER NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_groups_discovery
  ON groupes(visibility, recruitment_open, created_at);
