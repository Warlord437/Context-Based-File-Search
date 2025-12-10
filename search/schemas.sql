-- SQLite schema for catalog database and FTS5 virtual table

-- Enable FTS5 extension
-- Note: FTS5 is included by default in SQLite 3.35.0+

-- Files table - tracks file metadata and changes
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    size INTEGER NOT NULL,
    mtime INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    indexed_at INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Indexes for files table
CREATE INDEX IF NOT EXISTS idx_files_path ON files (path);
CREATE INDEX IF NOT EXISTS idx_files_mtime ON files (mtime);
CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files (sha256);

-- Chunks table - tracks chunk metadata
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    token_start INTEGER NOT NULL,
    token_end INTEGER NOT NULL,
    created_at INTEGER DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (file_id) REFERENCES files(file_id) ON DELETE CASCADE,
    UNIQUE(file_id, idx)
);

-- Indexes for chunks table
CREATE INDEX IF NOT EXISTS idx_chunks_file_id ON chunks (file_id);
CREATE INDEX IF NOT EXISTS idx_chunks_idx ON chunks (idx);

-- FTS5 virtual table for full-text search
-- Uses Porter stemming for better word matching
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    chunk_id,
    text,
    path,
    tokenize = 'porter'
);

-- Triggers to maintain FTS5 index
-- Note: FTS insertion is handled manually in the application
-- No automatic triggers needed for chunks_fts

-- Update trigger for chunk metadata changes
CREATE TRIGGER IF NOT EXISTS chunks_fts_update_chunk AFTER UPDATE ON chunks
BEGIN
    UPDATE chunks_fts 
    SET chunk_id = NEW.chunk_id
    WHERE chunk_id = OLD.chunk_id;
END;

-- Update trigger for file path changes
CREATE TRIGGER IF NOT EXISTS chunks_fts_update_file AFTER UPDATE OF path ON files
BEGIN
    UPDATE chunks_fts 
    SET path = NEW.path
    WHERE path = OLD.path;
END;

-- Delete trigger
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON chunks
BEGIN
    DELETE FROM chunks_fts WHERE chunk_id = OLD.chunk_id;
END;

-- Delete trigger for files (cascades to chunks)
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete_file AFTER DELETE ON files
BEGIN
    DELETE FROM chunks_fts WHERE path = OLD.path;
END;

-- Indexing statistics table
CREATE TABLE IF NOT EXISTS index_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    files_processed INTEGER DEFAULT 0,
    chunks_created INTEGER DEFAULT 0,
    files_skipped INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0.0,
    timestamp INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Indexes for index_stats table
CREATE INDEX IF NOT EXISTS idx_stats_timestamp ON index_stats (timestamp);
CREATE INDEX IF NOT EXISTS idx_stats_operation ON index_stats (operation);

-- Search statistics table
CREATE TABLE IF NOT EXISTS search_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    total_candidates INTEGER DEFAULT 0,
    vector_candidates INTEGER DEFAULT 0,
    lexical_candidates INTEGER DEFAULT 0,
    final_results INTEGER DEFAULT 0,
    duration_seconds REAL DEFAULT 0.0,
    cache_hit BOOLEAN DEFAULT FALSE,
    timestamp INTEGER DEFAULT (strftime('%s', 'now'))
);

-- Indexes for search_stats table
CREATE INDEX IF NOT EXISTS idx_search_timestamp ON search_stats (timestamp);
CREATE INDEX IF NOT EXISTS idx_search_query ON search_stats (query);

-- Views for common queries
CREATE VIEW IF NOT EXISTS file_chunk_counts AS
SELECT 
    f.file_id,
    f.path,
    f.size,
    f.mtime,
    COUNT(c.chunk_id) as chunk_count,
    f.indexed_at
FROM files f
LEFT JOIN chunks c ON f.file_id = c.file_id
GROUP BY f.file_id, f.path, f.size, f.mtime, f.indexed_at;

CREATE VIEW IF NOT EXISTS recent_indexing AS
SELECT 
    operation,
    files_processed,
    chunks_created,
    duration_seconds,
    datetime(timestamp, 'unixepoch') as timestamp_str
FROM index_stats
ORDER BY timestamp DESC
LIMIT 10;

CREATE VIEW IF NOT EXISTS recent_searches AS
SELECT 
    query,
    final_results,
    duration_seconds,
    cache_hit,
    datetime(timestamp, 'unixepoch') as timestamp_str
FROM search_stats
ORDER BY timestamp DESC
LIMIT 10;

-- Utility functions (using SQLite's JSON extension if available)
-- These help with debugging and maintenance

-- Function to get database statistics
CREATE VIEW IF NOT EXISTS db_stats AS
SELECT 
    (SELECT COUNT(*) FROM files) as total_files,
    (SELECT COUNT(*) FROM chunks) as total_chunks,
    (SELECT COUNT(*) FROM chunks_fts) as total_fts_entries,
    (SELECT COUNT(DISTINCT path) FROM chunks_fts) as unique_paths,
    (SELECT SUM(size) FROM files) as total_size_bytes,
    (SELECT MAX(indexed_at) FROM files) as last_indexed;

-- Function to find orphaned FTS entries
CREATE VIEW IF NOT EXISTS orphaned_fts AS
SELECT cft.chunk_id, cft.path
FROM chunks_fts cft
LEFT JOIN chunks c ON cft.chunk_id = c.chunk_id
WHERE c.chunk_id IS NULL;

-- Function to find missing FTS entries
CREATE VIEW IF NOT EXISTS missing_fts AS
SELECT c.chunk_id, f.path
FROM chunks c
JOIN files f ON c.file_id = f.file_id
LEFT JOIN chunks_fts cft ON c.chunk_id = cft.chunk_id
WHERE cft.chunk_id IS NULL;
