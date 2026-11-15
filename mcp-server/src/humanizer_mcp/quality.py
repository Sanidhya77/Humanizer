"""Catch an edit that reads worse than the text it started from.

An edit can stay inside the budget and keep every fact, and still damage the
text: a doubled word, a bracket left open, a sentence cut to a fragment, the same
opener three times in a row. Rewriting tools are known to do this (the DAMAGE
study found that every humanizer it tested lowered fluency, and the worst ones
left stray characters and broken sentences).

This module only compares. It reports what is new in the rewrite, so an oddity
that was already in the writer's original is not blamed on the edit.

It also looks for hidden characters and look-alike letters (a Cyrillic "а" inside
a Latin word). Some tools insert those to confuse detectors. They break search,
screen readers and copy-paste, so they are always reported, in either text.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .text_utils import paragraphs, sentences, words

_INVISIBLE = {
    "​": "zero-width space", "‌": "zero-width non-joiner", "‍": "zero-width joiner",
    "⁠": "word joiner", "﻿": "byte-order mark", "­": "soft hyphen",
    "‎": "left-to-right mark", "‏": "right-to-left mark",
    "‪": "bidi control", "‫": "bidi control", "‬": "bidi control",
    "‭": "bidi control", "‮": "bidi control", "⁣": "invisible separator",
}
_PAIRS = [("(", ")"), ("[", "]"), ("{", "}"), ("“", "”")]
_END = tuple(".!?:;…\"'”’)]")


def _hidden_characters(text: str) -> list[str]:
    found = Counter(ch for ch in text if ch in _INVISIBLE)
    return [f"{_INVISIBLE[ch]} (x{n})" for ch, n in found.items()]


def _script(ch: str) -> str:
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    for s in ("LATIN", "CYRILLIC", "GREEK"):
        if name.startswith(s):
            return s
    return ""


def _lookalike_words(text: str) -> list[str]:
    """Words that mix Latin letters with Cyrillic or Greek ones."""
    out = []
    for tok in re.findall(r"[^\W\d_]{2,}", text):
        scripts = {_script(c) for c in tok} - {""}
        if "LATIN" in scripts and len(scripts) > 1:
            out.append(tok)
    return sorted(set(out))[:20]


def _doubled_words(text: str) -> Counter:
    return Counter(m.group(1).lower() for m in re.finditer(r"\b([A-Za-z]{2,})\s+\1\b", text, re.IGNORECASE)
                   if m.group(1).lower() not in {"that", "had", "very", "so", "no", "bye", "ha"})


def _unbalanced(text: str) -> list[str]:
    out = []
    for i, p in enumerate(paragraphs(text), 1):
        for a, b in _PAIRS:
            if p.text.count(a) != p.text.count(b):
                out.append(f"paragraph {i}: {a} {b} do not match")
        if p.text.count('"') % 2:
            out.append(f'paragraph {i}: odd number of " marks')
    return out


def _body(text: str) -> list[str]:
    return [p.text for p in paragraphs(text) if not p.text.lstrip().startswith("#") and len(words(p.text)) >= 25]


def _unfinished(text: str) -> int:
    return sum(1 for p in _body(text) if not p.rstrip().endswith(_END))


def _sent_texts(text: str) -> list[str]:
    return [s.text for p in _body(text) for s in sentences(p) if words(s.text)]


def _fragments(sents: list[str]) -> list[str]:
    return [s for s in sents if len(words(s)) < 3]


def _opener_runs(text: str) -> list[str]:
    """The same first word opening three or more sentences in a row, inside one paragraph.

    Runs are not counted across paragraphs: two sections that each start with "The" are
    not a repetition a reader notices.
    """
    runs = []
    for p in _body(text):
        prev, n = None, 0
        for s in [x.text for x in sentences(p) if words(x.text)] + [""]:
            w = words(s)[0].lower() if words(s) else None
            if w and w == prev:
                n += 1
            else:
                if prev and n >= 3:
                    runs.append(f'"{prev.capitalize()} ..." x{n} in a row')
                prev, n = w, 1
    return runs


def _repeated_phrases(text: str, n: int = 4) -> Counter:
    ws = [w.lower() for w in words(text)]
    grams = Counter(" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1))
    return Counter({g: c for g, c in grams.items() if c >= 3})


def _avg(xs: list[int]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def check_quality(original: str, rewrite: str) -> dict:
    """List what the rewrite made worse. ok=true means no hard issue."""
    hard: list[dict] = []
    soft: list[dict] = []

    hidden = _hidden_characters(rewrite)
    if hidden:
        hard.append({"issue": "hidden_characters", "found": hidden,
                     "fix": "Delete them. They are invisible and break search, screen readers and copy-paste."})
    look = _lookalike_words(rewrite)
    if look:
        hard.append({"issue": "lookalike_letters", "found": look,
                     "fix": "Retype these words with normal Latin letters."})
    in_original = _hidden_characters(original) or _lookalike_words(original)
    if in_original and not (hidden or look):
        soft.append({"issue": "original_had_hidden_or_lookalike_characters",
                     "note": "The original held hidden or look-alike characters, probably from another tool. "
                             "The rewrite is clean."})

    new_doubles = _doubled_words(rewrite) - _doubled_words(original)
    if new_doubles:
        hard.append({"issue": "doubled_words", "found": sorted(f"{w} {w}" for w in new_doubles),
                     "fix": "Remove the repeated word."})

    new_unbalanced = [u for u in _unbalanced(rewrite)] if len(_unbalanced(rewrite)) > len(_unbalanced(original)) else []
    if new_unbalanced:
        hard.append({"issue": "unbalanced_brackets_or_quotes", "found": new_unbalanced[:10],
                     "fix": "Close or remove the open bracket or quotation mark."})

    if _unfinished(rewrite) > _unfinished(original):
        hard.append({"issue": "paragraph_without_end_mark",
                     "found": [p[-60:] for p in _body(rewrite) if not p.rstrip().endswith(_END)][:5],
                     "fix": "A paragraph stops without a full stop. Check that no text was cut off."})

    o_sents, r_sents = _sent_texts(original), _sent_texts(rewrite)
    # Sentence checks only compare when both texts split into a similar number of sentences.
    # (A rough draft with no full stops is one long "sentence".)
    comparable = bool(o_sents and r_sents and 0.6 <= len(o_sents) / len(r_sents) <= 1.6)
    o_frag, r_frag = _fragments(o_sents), _fragments(r_sents)
    if comparable and len(r_frag) > len(o_frag):
        soft.append({"issue": "new_fragments", "found": r_frag[:8],
                     "note": "Sentences of one or two words that the original did not have."})

    new_runs = [r for r in _opener_runs(rewrite) if r not in _opener_runs(original)] if comparable else []
    if new_runs:
        soft.append({"issue": "repeated_openers", "found": new_runs,
                     "note": "Vary the opening, or go back to the writer's own sentence."})

    o_rep, r_rep = _repeated_phrases(original), _repeated_phrases(rewrite)
    new_rep = {g: c for g, c in r_rep.items() if c > o_rep.get(g, 0)}
    if new_rep:
        soft.append({"issue": "repeated_phrases",
                     "found": [f'"{g}" x{c}' for g, c in sorted(new_rep.items(), key=lambda x: -x[1])[:8]],
                     "note": "The same four words appear three or more times, more often than in the original."})

    ow, rw = len(words(original)), len(words(rewrite))
    ratio = round(rw / ow, 2) if ow else 0.0
    if ow and not 0.8 <= ratio <= 1.25:
        soft.append({"issue": "length_changed", "length_ratio": ratio,
                     "note": "The rewrite is much shorter or longer than the original. An edit should not be."})

    reading = None
    if comparable:
        o_len, r_len = _avg([len(words(s)) for s in o_sents]), _avg([len(words(s)) for s in r_sents])
        o_wl = _avg([len(w) for w in words(original)])
        r_wl = _avg([len(w) for w in words(rewrite)])
        reading = {"avg_sentence_words": [round(o_len, 1), round(r_len, 1)],
                   "avg_word_length": [round(o_wl, 2), round(r_wl, 2)]}
        if o_len and abs(r_len - o_len) / o_len > 0.25:
            soft.append({"issue": "sentence_length_changed", "before_after": reading["avg_sentence_words"],
                         "note": "Average sentence length moved by more than a quarter. The text now reads "
                                 "at a different level than the writer's own."})
        if o_wl and (r_wl - o_wl) / o_wl > 0.06:
            soft.append({"issue": "longer_words", "before_after": reading["avg_word_length"],
                         "note": "Words got longer on average. Plain words were probably swapped for formal ones."})

    return {
        "ok": not hard,
        "hard_issues": hard,
        "worth_a_look": soft,
        "reading_level_before_after": reading,
        "rule": "Fix every hard issue. For each item in worth_a_look, prefer the writer's original wording.",
    }
