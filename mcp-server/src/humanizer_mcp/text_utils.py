"""Plain-text helpers: sentence and paragraph splitting, word lists, file reading."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Abbreviations that end with a period but do not end a sentence.
_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "et al", "vs", "fig", "figs", "eq", "eqs", "no", "nos",
    "dr", "mr", "mrs", "ms", "prof", "st", "jr", "sr", "inc", "ltd", "co",
    "approx", "cf", "ch", "sec", "vol", "pp", "p", "ed", "eds", "al", "u.s",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")


@dataclass
class Span:
    text: str
    start: int  # character offset in the original text
    end: int


def paragraphs(text: str) -> list[Span]:
    """Split on blank lines. Markdown headings count as their own paragraph."""
    spans: list[Span] = []
    for m in re.finditer(r"(?:[^\n]|\n(?!\s*\n))+", text):
        chunk = m.group(0)
        if chunk.strip():
            lead = len(chunk) - len(chunk.lstrip())
            spans.append(Span(chunk.strip(), m.start() + lead, m.start() + lead + len(chunk.strip())))
    return spans


def _is_abbreviation(text: str, dot_index: int) -> bool:
    before = text[max(0, dot_index - 12):dot_index]
    m = re.search(r"([A-Za-z.]+)$", before)
    if not m:
        return False
    token = m.group(1).lower().rstrip(".")
    if token in _ABBREVIATIONS:
        return True
    # Single capital letter initials like "J. Smith"
    return len(token) == 1 and token.isalpha()


def sentences(text: str) -> list[Span]:
    """Split text into sentences, keeping character offsets.

    Handles common abbreviations, decimals (3.5), initials and line-broken
    headings. Not perfect, but good enough for scoring and stats.
    """
    out: list[Span] = []
    for para in paragraphs(text):
        ptext = para.text
        start = 0
        i = 0
        n = len(ptext)
        while i < n:
            ch = ptext[i]
            boundary = False
            if ch in "!?":
                boundary = True
            elif ch == ".":
                nxt = ptext[i + 1] if i + 1 < n else ""
                prev = ptext[i - 1] if i > 0 else ""
                if prev.isdigit() and nxt.isdigit():
                    boundary = False  # decimal
                elif _is_abbreviation(ptext, i):
                    boundary = False
                else:
                    boundary = True
            elif ch == "\n":
                # A single newline inside a paragraph (lists, headings) ends a sentence.
                boundary = True
            if boundary and ch == "\n":
                seg = ptext[start:i]
                if seg.strip():
                    lead = len(seg) - len(seg.lstrip())
                    s = para.start + start + lead
                    out.append(Span(seg.strip(), s, s + len(seg.strip())))
                start = i + 1
                i += 1
                continue
            if boundary:
                j = i + 1
                # absorb closing quotes / brackets / repeated punctuation
                while j < n and ptext[j] in "\"'”’)]!?.":
                    j += 1
                if j >= n or ptext[j].isspace():
                    seg = ptext[start:j]
                    if seg.strip():
                        lead = len(seg) - len(seg.lstrip())
                        s = para.start + start + lead
                        out.append(Span(seg.strip(), s, s + len(seg.strip())))
                    start = j
                    i = j
                    continue
            i += 1
        seg = ptext[start:]
        if seg.strip():
            lead = len(seg) - len(seg.lstrip())
            s = para.start + start + lead
            out.append(Span(seg.strip(), s, s + len(seg.strip())))
    return out


def words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def read_document(path: str | Path) -> str:
    """Read .txt, .md or .docx into plain text."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"No file at {p}")
    suffix = p.suffix.lower()
    if suffix == ".docx":
        try:
            import docx  # python-docx
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Reading .docx needs python-docx: pip install python-docx") from e
        d = docx.Document(str(p))
        return "\n\n".join(par.text for par in d.paragraphs if par.text.strip())
    return p.read_text(encoding="utf-8", errors="replace")
