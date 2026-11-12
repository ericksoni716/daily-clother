-- Bulk import: a photo already in the closet is not added again.
-- source_sha256 is the SHA-256 of the file the owner picked, before the browser
-- shrank it (the browser sends it). Photos added before this have only the hash
-- of what reached the server, which is the best that is known for them.

ALTER TABLE photos ADD COLUMN source_sha256 TEXT;
UPDATE photos SET source_sha256 = sha256;
CREATE INDEX photos_source_sha256 ON photos (source_sha256);
