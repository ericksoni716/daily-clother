-- Stop B: what the tagger said about each item, and where its tagging stands.
-- Numbered 0005 on purpose: a migration numbered below a closet's current version would never run.

ALTER TABLE items ADD COLUMN tag_state TEXT NOT NULL DEFAULT 'none'
  CHECK (tag_state IN ('none', 'waiting', 'working', 'done', 'failed'));
ALTER TABLE items ADD COLUMN tag_error TEXT;            -- why tagging failed, in a sentence the owner can read
ALTER TABLE items ADD COLUMN tag_answer TEXT;           -- JSON: the tagger's whole answer as it came back (kept whatever the owner changes)
ALTER TABLE items ADD COLUMN tag_schema_version INTEGER; -- closet/tagger/schema.py SCHEMA_VERSION the answer was given in
ALTER TABLE items ADD COLUMN tag_route TEXT;            -- 'plan', 'api', or 'demo' for the demo closet's answers made in advance
ALTER TABLE items ADD COLUMN tag_model TEXT;            -- the model that answered (null for the demo closet)
ALTER TABLE items ADD COLUMN tagged_at TEXT;            -- when the answer arrived (UTC)
