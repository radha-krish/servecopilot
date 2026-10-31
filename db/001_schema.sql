CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS issues (
    number BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    labels TEXT[],
    created_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    state_reason TEXT
);

CREATE TABLE IF NOT EXISTS pull_requests (
    number BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    merged_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS issue_pr_links (
    issue_number BIGINT REFERENCES issues(number),
    pr_number BIGINT REFERENCES pull_requests(number),
    PRIMARY KEY (issue_number, pr_number)
);

-- The primary key already indexes lookups by issue_number;
-- this one serves the reverse lookup "which issues did this PR fix?".
CREATE INDEX IF NOT EXISTS issue_pr_links_pr_number_idx
    ON issue_pr_links (pr_number);

CREATE TABLE IF NOT EXISTS pr_files (
    pr_number BIGINT REFERENCES pull_requests(number),
    file_path TEXT NOT NULL,
    PRIMARY KEY (pr_number, file_path)
);

CREATE TABLE IF NOT EXISTS chunks (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id BIGINT NOT NULL,
    content TEXT NOT NULL
);
