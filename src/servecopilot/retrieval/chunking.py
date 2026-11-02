import re

_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*#*\s*$")


def split_by_headings(markdown):
    """Return (heading_path, text) per section, e.g. ("Serving > Tool calling", ...)."""
    sections = []
    path = []
    lines = []
    in_code = False

    def flush():
        text = "\n".join(lines).strip()
        if text:
            sections.append((" > ".join(path), text))
        lines.clear()

    for line in markdown.splitlines():
        # "# install deps" inside a ```bash block is a comment, not a heading.
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            path[:] = path[: level - 1] + [match.group(2)]
        else:
            lines.append(line)
    flush()
    return sections


def pack_paragraphs(text, max_words=350):
    chunks = []
    current = []
    count = 0

    for paragraph in text.split("\n\n"):
        words = len(paragraph.split())

        if words > max_words:
            if current:
                chunks.append("\n\n".join(current))
                current, count = [], 0

            paragraph_words = paragraph.split()

            for start in range(0, len(paragraph_words), max_words):
                piece = paragraph_words[start : start + max_words]
                chunks.append(" ".join(piece))

            continue

        if current and count + words > max_words:
            chunks.append("\n\n".join(current))
            current, count = [], 0

        current.append(paragraph)
        count += words

    if current:
        chunks.append("\n\n".join(current))

    return chunks
