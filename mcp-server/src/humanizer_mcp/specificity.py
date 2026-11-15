"""Find the paragraphs that say the least.

A paragraph with no number, name, example, first-hand detail or stated opinion
could have been written by anyone, about anything. In an AI-written draft those
are the places to ask the writer a question, because only the writer can fill
them (see references/local-tools.md, "AI-written drafts").

This is a count, not a judgement of who wrote the paragraph. People write
generic paragraphs too. It only decides where a question is worth asking.
"""

from __future__ import annotations

import re

from .meaning import _citations, _names, _numbers
from .text_utils import paragraphs, words

_FIRST_HAND = re.compile(
    r"\b(?:i|we)\s+(?:\w+ly\s+)?(?:saw|measured|found|tried|tested|built|ran|noticed|learned|learnt|used|wrote|"
    r"worked|asked|compared|counted|observed|interviewed|visited|collected|recorded|spent|made|did|had|got|"
    r"started|switched|chose|decided|failed|fixed|broke|shipped|deployed)\b"
    r"|\bin (?:my|our) (?:experience|project|test|tests|case|class|team|work|study|thesis|company|data|own)\b"
    r"|\b(?:my|our) (?:professor|team|client|manager|supervisor|results|data|code|students|customers|users)\b"
    r"|\b(?:last|this) (?:week|month|year|semester|summer|winter)\b|\b(?:yesterday|years? ago|months? ago)\b",
    re.IGNORECASE)
_STANCE = re.compile(
    r"\bi (?:think|believe|doubt|suspect|disagree|agree|prefer|would argue|am not sure|don't think|do not think)\b"
    r"|\bin my (?:opinion|view)\b|\b(?:honestly|frankly|surprisingly|to be fair|to my surprise|i was wrong)\b",
    re.IGNORECASE)
_EXAMPLE = re.compile(r"\b(?:for example|for instance|e\.g\.|such as|one example|take the case)\b", re.IGNORECASE)
_QUOTE = re.compile(r"[\"“][^\"”]{12,}[\"”]")

_FILLER = re.compile(
    r"\bplays? an? (?:crucial|key|vital|important|pivotal|significant) role\b"
    r"|\bit is (?:important|worth|essential|crucial) to (?:note|mention|remember|understand|recognize)\b"
    r"|\bin today's (?:\w+ )?(?:world|landscape|age|era|society)\b|\bin the (?:modern|digital) (?:world|age|era)\b"
    r"|\b(?:rapidly|ever|constantly|fast)[- ](?:evolving|changing|growing)\b"
    r"|\ba (?:wide|broad|vast) (?:range|variety|array) of\b|\bwhen it comes to\b|\bat the end of the day\b"
    r"|\bin conclusion\b|\boverall,|\bultimately,|\bhas become (?:increasingly|more and more)\b"
    r"|\b(?:unlock|harness|leverage)s? the (?:power|potential|full potential)\b|\bthe (?:power|importance) of\b"
    r"|\bcannot be overstated\b|\bgame[- ]changer\b|\bboth .{3,40} and .{3,40} alike\b",
    re.IGNORECASE)
_VAGUE = re.compile(
    r"\b(?:many|various|numerous|several|countless|some|most) (?:people|experts|studies|researchers|companies|"
    r"organizations|organisations|businesses|users|factors|ways|benefits|challenges|aspects|areas|industries)\b",
    re.IGNORECASE)

MIN_WORDS = 30
WORDS_PER_QUESTION = 300
MIN_QUESTIONS, MAX_QUESTIONS = 3, 8


def _score(text: str) -> dict:
    n = len(words(text))
    specifics = {
        "numbers": sum(_numbers(text).values()),
        "names": len(_names(text)),
        "citations": sum(_citations(text).values()),
        "first_hand": len(_FIRST_HAND.findall(text)),
        "opinions": len(_STANCE.findall(text)),
        "examples": len(_EXAMPLE.findall(text)),
        "quotes": len(_QUOTE.findall(text)),
    }
    filler = [m.group(0) for m in _FILLER.finditer(text)] + [m.group(0) for m in _VAGUE.finditer(text)]
    # a paragraph can only "earn" 3 points from one kind of detail, so ten numbers
    # in a results paragraph do not hide the fact that nothing else is there
    earned = sum(min(v, 3) for v in specifics.values())
    score = round(100 * (earned - len(filler)) / max(n, 1), 1)
    return {"words": n, "score": score, "has": {k: v for k, v in specifics.items() if v}, "filler": filler[:6]}


def find_generic(text: str, max_questions: int | None = None) -> dict:
    """Rank the paragraphs of a text from least to most specific."""
    rows = []
    total_words = 0
    for i, p in enumerate(paragraphs(text), 1):
        if p.text.lstrip().startswith("#"):
            continue
        n = len(words(p.text))
        total_words += n
        if n < MIN_WORDS:
            continue
        s = _score(p.text)
        ws = p.text.split()
        rows.append({"paragraph": i, **s, "starts": " ".join(ws[:12]) + (" ..." if len(ws) > 12 else "")})
    rows.sort(key=lambda r: (r["score"], -r["words"]))
    allowed = max(MIN_QUESTIONS, min(MAX_QUESTIONS, round(total_words / WORDS_PER_QUESTION)))
    if max_questions is not None:
        allowed = max(0, min(allowed, int(max_questions)))
    # only paragraphs with next to nothing in them are worth a question
    ask = [r for r in rows if r["score"] <= 1.0][:allowed]
    return {
        "words": total_words,
        "questions_allowed": allowed,
        "ask_about": ask,
        "all_paragraphs": rows,
        "how_to_read": (
            "score = details per 100 words (numbers, names, citations, first-hand phrases, opinions, examples, "
            "quotes; at most 3 points per kind) minus filler phrases. ask_about lists the paragraphs with the least "
            "in them. Ask the writer ONE specific question about each, all in one message. A low score does not "
            "mean a model wrote the paragraph."),
    }
