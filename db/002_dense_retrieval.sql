ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS source_ref TEXT,
    ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS heading_path TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS component TEXT,
    ADD COLUMN IF NOT EXISTS version TEXT,
    ADD COLUMN IF NOT EXISTS embedding vector(384);

-- Docs have no number; they are identified by source_ref (file path).
ALTER TABLE chunks ALTER COLUMN source_id DROP NOT NULL;

-- One row per (type, source, chunk): makes re-indexing an upsert, not a duplicate.
CREATE UNIQUE INDEX IF NOT EXISTS chunks_source_key
    ON chunks (source_type, source_ref, chunk_index);

CREATE INDEX IF NOT EXISTS chunks_metadata_idx
    ON chunks (source_type, component, created_at);
