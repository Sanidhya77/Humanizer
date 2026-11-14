"""Check that a rewrite kept every fact the original had.

Rewriting to lower a detector score tends to drift: a number gets rounded,
a citation disappears, "in 2019" becomes "recently". This module pulls the
checkable items out of both versions and lists what went missing or appeared
from nowhere.

Hard items (must survive): numbers, percentages, years, citations, DOIs,
URLs, direct quotes.
Soft items (worth a look): names, acronyms, technical terms.
"""

from __future__ import annotations

import re
from collections import Counter

from .text_utils import sentences, words

_NUM_WORDS = {"percent": "%", "per cent": "%"}
_SCALE = {"k": "thousand", "m": "million", "bn": "billion", "b": "billion"}

_NUMBER_RE = re.compile(
    r"(?<![\w.])[-+−]?\$?€?£?\d[\d,]*(?:\.\d+)?"
    r"(?:\s?(?:%|percent|per cent|x|×))?"
    r"(?:\s?(?:k|bn|thousand|million|billion|trillion)\b)?",
    re.IGNORECASE,
)
_AUTHOR_YEAR_RE = re.compile(
    r"\(([^()]*?\b(?:1[89]|20)\d{2}[a-z]?(?:,\s*(?:p|pp)\.\s*[\d\-–]+)?)\)"
)
_NARRATIVE_CITE_RE = re.compile(
    r"\b([A-Z][A-Za-z'\-]+(?:\s+(?:et al\.|and|&)\s*[A-Z]?[A-Za-z'\-]*)?)\s+\(((?:1[89]|20)\d{2}[a-z]?)\)"
)
_NUMERIC_CITE_RE = re.compile(r"\[\s*\d+(?:\s*[\-–,]\s*\d+)*\s*\]")
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s\"<>)\]]+")
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
_QUOTE_RE = re.compile(r"[\"“]([^\"”]{12,}?)[\"”]")
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,}(?:-[A-Z0-9]+)?s?\b")

_STOP_CAPS = {
    "The", "A", "An", "This", "That", "These", "Those", "It", "In", "On", "At", "For",
    "But", "And", "Or", "If", "When", "While", "As", "We", "I", "You", "They", "He",
    "She", "Our", "My", "Its", "There", "Here", "So", "However", "Also", "Then",
    "First", "Second", "Third", "Finally", "Today", "Yet", "Still", "What", "Why",
    "How", "Which", "Who", "With", "Without", "From", "To", "By", "Of", "Not", "No",
}


def _norm_number(raw: str) -> str:
    s = raw.lower().strip().replace("−", "-").replace(",", "")
    for k, v in _NUM_WORDS.items():
        s = s.replace(k, v)
    s = re.sub(r"\s+", "", s)
    m = re.match(r"^(.*?\d)(k|bn|b|m)$", s)
    if m:
        s = m.group(1) + _SCALE[m.group(2)]
    s = s.replace("×", "x")
    return s


def _numbers(text: str) -> Counter:
    # Skip citation brackets and DOIs/URLs so their digits are not double counted.
    cleaned = _DOI_RE.sub(" ", _URL_RE.sub(" ", text))
    cleaned = _NUMERIC_CITE_RE.sub(" ", cleaned)
    return Counter(_norm_number(m.group(0)) for m in _NUMBER_RE.finditer(cleaned))


def _citations(text: str) -> Counter:
    items = []
    for m in _AUTHOR_YEAR_RE.finditer(text):
        # split "(Smith, 2020; Lee & Park, 2021)" into separate citations
        for part in re.split(r";", m.group(1)):
            part = re.sub(r"\s+", " ", part.strip())
            if re.search(r"(?:1[89]|20)\d{2}", part):
                items.append(part)
    for m in _NARRATIVE_CITE_RE.finditer(text):
        items.append(f"{m.group(1).strip()}, {m.group(2)}")
    items += [re.sub(r"\s+", "", m.group(0)) for m in _NUMERIC_CITE_RE.finditer(text)]
    return Counter(items)


def _cite_key(c: str) -> str:
    """Loose key so 'Smith et al., 2020' matches 'Smith et al. (2020)'."""
    c = c.lower()
    year = re.findall(r"(?:1[89]|20)\d{2}[a-z]?", c)
    name = re.findall(r"[a-z][a-z'\-]+", c)
    name = [n for n in name if n not in {"et", "al", "and", "p", "pp"}]
    return f"{name[0] if name else ''}:{year[0] if year else ''}" if year else c


def _names(text: str) -> Counter:
    found = Counter()
    for span in sentences(text):
        toks = re.findall(r"[A-Za-z][A-Za-z0-9'\-]*", span.text)
        for i, t in enumerate(toks):
            if i == 0 or t in _STOP_CAPS:
                continue
            if t[0].isupper():
                found[t] += 1
    for m in _ACRONYM_RE.finditer(text):
        found[m.group(0).rstrip("s") if m.group(0).endswith("s") and m.group(0)[:-1].isupper() else m.group(0)] += 1
    return found


def _fmt_counts(c: Counter) -> list[str]:
    """['23.5%', '1200 (x2 fewer)'] - one entry per item, with how many copies differ."""
    return sorted(k if n == 1 else f"{k} (x{n})" for k, n in c.items() if n > 0)


def _links(text: str) -> set[str]:
    found = _DOI_RE.findall(text) + _URL_RE.findall(text)
    return {l.rstrip(".,;:!?") for l in found}


def check_meaning(original: str, rewrite: str, also_allowed: str | None = None) -> dict:
    """also_allowed: extra text the writer supplied (for example their answers to
    questions). Numbers and citations found there are not reported as invented.
    Nothing in it is required to appear in the rewrite."""
    extra = also_allowed or ""
    o_nums, r_nums = _numbers(original), _numbers(rewrite)
    missing_numbers = _fmt_counts(o_nums - r_nums)
    added_numbers = _fmt_counts(r_nums - o_nums - _numbers(extra))

    o_cites, r_cites = _citations(original), _citations(rewrite)
    r_keys = Counter(_cite_key(c) for c in r_cites.elements())
    missing_cites = []
    for c in o_cites.elements():
        k = _cite_key(c)
        if r_keys[k] > 0:
            r_keys[k] -= 1
        else:
            missing_cites.append(c)
    o_keys = {_cite_key(c) for c in o_cites} | {_cite_key(c) for c in _citations(extra)}
    added_cites = sorted({c for c in r_cites if _cite_key(c) not in o_keys})

    o_links, r_links = _links(original), _links(rewrite)
    missing_links = sorted(o_links - r_links)

    r_flat = re.sub(r"\s+", " ", rewrite)
    missing_quotes = [
        q for q in _QUOTE_RE.findall(original) if re.sub(r"\s+", " ", q) not in r_flat
    ]

    o_names, r_names = _names(original), _names(rewrite)
    r_lower = rewrite.lower()
    missing_names = sorted(n for n in o_names if n not in r_names and n.lower() not in r_lower)

    o_words, r_words = len(words(original)), len(words(rewrite))
    ratio = round(r_words / o_words, 2) if o_words else 0.0

    hard = {
        "missing_numbers": missing_numbers,
        "added_numbers": added_numbers,
        "missing_citations": _fmt_counts(Counter(missing_cites)),
        "added_citations": added_cites,
        "missing_links": missing_links,
        "changed_quotes": missing_quotes,
    }
    problems = sum(len(v) for v in hard.values())
    notes = []
    if added_numbers or added_cites:
        notes.append(
            "The rewrite has numbers or citations the original did not. Remove them unless the user supplied them."
        )
    if ratio < 0.6:
        notes.append("The rewrite is much shorter. Check that no claim was cut.")
    elif ratio > 1.5:
        notes.append("The rewrite is much longer. Check for padding.")

    return {
        "ok": problems == 0,
        "hard_issues": problems,
        **hard,
        "names_to_check": missing_names[:25],
        "length_ratio": ratio,
        "words": {"original": o_words, "rewrite": r_words},
        "notes": notes,
    }
