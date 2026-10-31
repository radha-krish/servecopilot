"""Remove issue/PR references so retrieval can't match on the answer's number.

99% of vLLM PR bodies say "Fixes #1234" or link the issue URL, and some issue
bodies link their fixing PR. If that text is indexed or used as a query,
search "finds" the right answer by its number, and the eval measures nothing.
Applied to both sides: PR text before indexing, issue text before querying.
"""

import re

_REF = (
    r"(?:"
    # https://github.com/o/r/issues/123, also API paths: repos/o/r/issues/123
    r"(?:https?://github\.com/|\brepos/)[\w.-]+/[\w.-]+/(?:issues|pull)/\d+(?:#[\w-]+)?"
    r"|\b(?:[\w.-]+/)?[\w.-]+#\d+"  # owner/repo#123, vllm#123, issue#123
    r"|(?<![\w&])#\d+\b"  # #123 (not HTML entities like &#123;)
    r")"
)

# "Fixes #12", "FIX: https://github.com/.../issues/12", "closes owner/repo#12".
# The keyword is only removed together with a reference, so a title like
# "Fix crash in scheduler" keeps its words.
_KEYWORD_AND_REF = re.compile(
    rf"\b(?:fix(?:e[sd])?|close[sd]?|resolve[sd]?)\b[\s:]*{_REF}",
    re.IGNORECASE,
)
_REF_ONLY = re.compile(_REF)
_SPACES = re.compile(r"[ \t]{2,}")


def strip_issue_refs(text):
    if not text:
        return text
    text = _KEYWORD_AND_REF.sub("", text)
    text = _REF_ONLY.sub("", text)
    return _SPACES.sub(" ", text)
