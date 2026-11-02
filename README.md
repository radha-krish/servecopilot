# ServeCopilot

AI triage copilot for vLLM issues: paste a bug report, get related issues, likely fixing PRs, the component, and a cited answer.

## Chunking

What gets embedded (`src/servecopilot/retrieval/`):

| Source | One chunk = | Text embedded |
|---|---|---|
| Issue | the whole issue | title + cleaned body |
| PR | the whole PR | title + cleaned body + changed file paths (first 50) |
| Doc | one heading section, split further if long | heading path + section text |

**Cleaning before embedding.** The embedding model reads only ~512 tokens. Most issue bodies start with a `collect_env.py` dump (`<details>` blocks, "Your current environment"), so without cleaning many issue vectors would describe PyTorch versions instead of the bug. Removing env sections, the submission checklist and HTML comments halves the average issue body (8,337 → 4,146 chars). Issue/PR references (`#123`, issue URLs) are stripped too, so search can't match on the answer's number (see `leakage.py`).

**Docs: heading-aware chunks.** vLLM docs are structured Markdown, so sections are split on `#`/`##`/`###` headings rather than at fixed sizes. Each chunk keeps its heading path (e.g. `Serving > OpenAI server > Tool calling`), which adds context the section text alone lacks. Headings inside code blocks are ignored. Sections over ~350 words (~450 tokens) are split on paragraph breaks to stay under the model limit; pieces under 20 words (heading-only stubs) are skipped. Result: 1,993 chunks, median 99 words.

**Issues and PRs: one chunk each.** Simple and enough to start; long issues are truncated by the model. Multi-chunk issues/PRs are a later experiment (Day 9), kept only if the Day 6 eval shows a gain.
