"""Markdown chunking: one chunk per paragraph, prefixed with its section heading.

Used by the offline provider (and, in the Azure build, by ingestion). Paragraph
chunks keep a policy statement and its heading together, which is what both
lexical and vector retrieval need to rank it well.
"""

import re
from dataclasses import dataclass
from pathlib import Path

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    text: str
    source: str  # file name
    index: int  # position within the file


def _split_long(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        if current and len(current) + 1 + len(sentence) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        parts.append(current)
    return parts


def chunk_markdown(path: Path, max_chars: int = 1500) -> list[Chunk]:
    heading = ""
    pieces: list[str] = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8")):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            heading = block.lstrip("# ").splitlines()[0]
            continue
        text = f"{heading}: {block}" if heading else block
        pieces.extend(_split_long(text, max_chars))
    return [Chunk(text=t, source=path.name, index=i) for i, t in enumerate(pieces)]


def chunk_corpus(corpus_dir: Path, max_chars: int = 1500) -> list[Chunk]:
    return [
        chunk
        for path in sorted(Path(corpus_dir).glob("*.md"))
        for chunk in chunk_markdown(path, max_chars)
    ]
