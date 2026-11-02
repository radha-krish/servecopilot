import re

from servecopilot.leakage import strip_issue_refs

_DETAILS = re.compile(r"<details>.*?</details>", re.DOTALL | re.IGNORECASE)
_ENV_SECTION = re.compile(
    r"###\s*Your current environment.*?(?=\n###\s|\Z)", re.DOTALL | re.IGNORECASE
)
_CHECKLIST = re.compile(
    r"###\s*Before submitting a new issue.*", re.DOTALL | re.IGNORECASE
)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_body(body):
    # The model only reads ~512 tokens. Without this, many issue vectors
    # would encode collect_env.py output (PyTorch versions, CPU flags), not the bug.
    if not body:
        return ""
    for pattern in (_DETAILS, _ENV_SECTION, _CHECKLIST, _HTML_COMMENT):
        body = pattern.sub("", body)
    body = strip_issue_refs(body)
    return _BLANK_LINES.sub("\n\n", body).strip()


def issue_text(title, body):
    return f"{strip_issue_refs(title)}\n\n{clean_body(body)}".strip()


def pr_text(title, body, files):
    text = f"{strip_issue_refs(title)}\n\n{clean_body(body)}".strip()
    if files:
        text += "\n\nChanged files:\n" + "\n".join(files[:50])
    return text
