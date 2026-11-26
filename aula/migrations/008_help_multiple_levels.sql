CREATE TABLE IF NOT EXISTS help_request_levels (
  request_id INTEGER NOT NULL,
  level TEXT NOT NULL CHECK (level IN ('L1', 'L2', 'L3', 'M1', 'M2', 'Doctorat', 'Autre')),
  PRIMARY KEY (request_id, level),
  FOREIGN KEY (request_id) REFERENCES help_requests(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_help_request_levels_level
  ON help_request_levels(level, request_id);

INSERT OR IGNORE INTO help_request_levels(request_id, level)
SELECT id, target_level FROM help_requests;
