# ServeCopilot — Day 1: GitHub Issue Ingestion

Day 1 builds the first data-ingestion component of ServeCopilot.

The goal is to fetch closed GitHub issues from the vLLM repository through the GitHub GraphQL API, extract useful issue and fixing-PR information, and store the result as JSONL.

This day focuses on learning the foundations of **production-oriented data ingestion**.

## What I Built

The ingester:

1. Connects to GitHub's GraphQL API.
2. Fetches closed issues using cursor-based pagination.
3. Extracts:
   - Issue number
   - Title
   - Body
   - Labels
   - Creation time
   - Closing time
   - State reason
   - Merged fixing PRs
4. Writes issues incrementally to JSONL.
5. Tracks GitHub API rate limits.
6. Detects when nested API results are truncated.
7. Uses an HTTP client that can reuse connections.
8. Uses atomic file writing so an interrupted run does not replace the existing valid dataset with a partial file.
9. Provides CLI configuration for repository, issue limit, and output path.

## Architecture

```text
GitHub GraphQL API
        │
        ▼
   fetch_page()
        │
        ▼
   GraphQL response
        │
        ├── rate limit information
        ├── pagination information
        └── issue data
                │
                ▼
          parse_issue()
                │
                ▼
         write JSONL
                │
                ▼
       issues.jsonl.tmp
                │
          flush + fsync
                │
                ▼
       atomic replacement
                │
                ▼
         issues.jsonl
```

## GraphQL Pagination

GitHub returns issues in pages.

Each request asks for:

```text
100 issues
```

The response contains:

```text
hasNextPage
endCursor
```

The next request uses `endCursor` as the next cursor.

The process continues until:

```text
fetched issues >= requested limit
```

or GitHub reports:

```text
hasNextPage = false
```

For example:

```text
Request 1 → issues 1–100
Request 2 → issues 101–200
Request 3 → issues 201–300
Request 4 → issues 301–400
Request 5 → issues 401–500
```

## Rate Limit Handling

Each GraphQL response includes:

```text
cost
remaining
resetAt
```

The ingester monitors the remaining API budget.

If the remaining budget becomes too low, the program waits until GitHub's rate-limit reset time rather than continuing until the request fails.

The current safety threshold is:

```python
RATE_LIMIT_FLOOR = 100
```

## Detecting Truncated Data

Some GraphQL fields are collections.

For example:

```graphql
labels(first: 20)
```

and:

```graphql
closedByPullRequestsReferences(first: