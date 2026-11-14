"""Measurable style features, shared by voice profiles and register presets.

Every rate is "per 1,000 words" or "share of sentences" so that texts of any
length compare directly. Word lists follow the categories in Hyland's stance
model (hedges, boosters, self-mention) and the AI-style findings in
Reinhart et al. (PNAS 2025), Kobak et al. (2025) and Liang et al. (2024).
See REGISTERS.md for sources.

Note: these are automatic counts with fixed word lists. Published studies
code by hand, so absolute numbers differ from theirs; the register presets
are expressed in *this* tool's units.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np

from .text_utils import paragraphs, sentences, words

# --- word lists -------------------------------------------------------------

HEDGES = {
    "may", "might", "could", "perhaps", "possibly", "possible", "probably", "probable",
    "likely", "unlikely", "seem", "seems", "seemed", "appear", "appears", "appeared",
    "apparently", "suggest", "suggests", "suggested", "indicate", "indicates", "indicated",
    "tend", "tends", "tended", "generally", "typically", "usually", "often", "largely",
    "mainly", "mostly", "approximately", "roughly", "about", "around", "somewhat",
    "relatively", "arguably", "presumably", "plausible", "plausibly", "partly", "partially",
    "sometimes", "assume", "assumed", "estimate", "estimated", "unclear", "uncertain",
}
BOOSTERS = {
    "clearly", "clear", "obviously", "obvious", "certainly", "certain", "definitely",
    "undoubtedly", "indeed", "always", "never", "must", "demonstrate", "demonstrates",
    "demonstrated", "prove", "proves", "proved", "proven", "show", "shows", "showed",
    "evident", "evidently", "establish", "establishes", "established", "really", "truly",
    "surely", "undeniably", "fundamentally", "highly", "extremely", "completely", "absolutely",
    "significantly", "strongly", "very",
}
FIRST_SINGULAR = {"i", "me", "my", "mine", "myself"}
FIRST_PLURAL = {"we", "us", "our", "ours", "ourselves"}
SECOND = {"you", "your", "yours", "yourself", "yourselves"}

# Words whose frequency jumped after ChatGPT (Kobak et al.; Liang et al.; Reinhart et al.).
# "Strong" items are rare in human academic text; one or two per text is already a tell.
AI_WORDS_STRONG = {
    "delve", "delves", "delved", "delving", "showcase", "showcases", "showcased", "showcasing",
    "underscore", "underscores", "underscored", "underscoring", "tapestry", "camaraderie",
    "realm", "realms", "intricate", "intricacies", "meticulous", "meticulously", "commendable",
    "pivotal", "palpable", "testament", "multifaceted", "seamlessly",
    "elevate", "elevates", "embark", "embarks", "unwavering", "bustling",
    "unlock", "unlocks", "unlocking", "transformative", "game-changer", "ever-evolving",
}
# Words that rose too but are ordinary in academic prose; only a high *rate* is a tell.
AI_WORDS_SOFT = {
    "crucial", "notably", "comprehensive", "robust", "leverage", "leverages", "leveraging",
    "foster", "fosters", "fostering", "enhance", "enhances", "enhancing", "streamline",
    "additionally", "furthermore", "moreover", "ultimately", "insights", "invaluable",
    "vital", "paramount", "noteworthy", "boasts",
    # also technical terms in some fields ("benchmark harness", "robust estimator"), so soft only
    "harness", "harnessing", "landscape", "nuanced", "seamless", "robust",
}

_CONTRACTION_RE = re.compile(
    r"\b\w+n['’]t\b|\b\w+['’](?:re|ve|ll|d|m)\b|\b(?:it|that|there|what|here|he|she|who|let|where|how)['’]s\b",
    re.IGNORECASE,
)
_IRREGULAR_PARTICIPLES = (
    "shown|made|done|given|taken|found|known|seen|built|written|held|kept|run|set|put|led|sent|"
    "chosen|drawn|grown|thrown|brought|bought|caught|taught|thought|left|lost|meant|paid|said|"
    "sold|told|understood|won|begun|broken|driven|eaten|fallen|forgotten|hidden|ridden|risen|"
    "spoken|stolen|worn|withdrawn|undertaken|overlooked"
)
_PASSIVE_RE = re.compile(
    rf"\b(?:am|is|are|was|were|be|been|being|get|gets|got)\s+(?:\w+ly\s+|not\s+)?(?:\w+ed|{_IRREGULAR_PARTICIPLES})\b",
    re.IGNORECASE,
)
# "..., leveraging X" / "Leaning on X, he ..." : a present participle opening a clause.
_PARTICIPLE_CLAUSE_RE = re.compile(r"(?:^|[,;:—–(]\s*)(?:thereby\s+|while\s+|by\s+)?[a-z]+ing\b(?!\s+(?:of|to)\b)")
_NOMINALIZATION_RE = re.compile(r"\b[a-z]{3,}(?:tion|tions|sion|sions|ment|ments|ness|nesses|ity|ities|ance|ances|ence|ences)\b")
_NOT_ING = {"thing", "things", "something", "anything", "nothing", "everything", "during", "bring",
            "king", "ring", "sing", "string", "spring", "morning", "evening", "ceiling", "building",
            "meaning", "according", "including", "regarding", "concerning", "following", "using"}
_UK_US = [("colour", "color"), ("behaviour", "behavior"), ("favour", "favor"), ("analyse", "analyze"),
          ("organis", "organiz"), ("realis", "realiz"), ("optimis", "optimiz"), ("centre", "center"),
          ("modelling", "modeling"), ("labelled", "labeled"), ("licence", "license"), ("programme", "program"),
          ("utilis", "utiliz"), ("summaris", "summariz"), ("prioritis", "prioritiz"), ("minimis", "minimiz"),
          ("maximis", "maximiz"), ("characteris", "characteriz"), ("standardis", "standardiz")]


def _participle_clauses(sents: list[str]) -> int:
    n = 0
    for s in sents:
        for m in _PARTICIPLE_CLAUSE_RE.finditer(s):
            word = re.search(r"[a-z]+ing\b", m.group(0)).group(0)
            if word not in _NOT_ING:
                n += 1
    return n


def text_stats(text: str) -> dict:
    sents = [s.text for s in sentences(text) if len(words(s.text)) >= 2]
    lens = [len(words(s)) for s in sents] or [0]
    ws = [w.lower() for w in words(text)]
    nw = max(len(ws), 1)
    ns = max(len(sents), 1)
    paras = [p.text for p in paragraphs(text) if not p.text.lstrip().startswith("#")]
    para_sents = [len(sentences(p)) for p in paras] or [0]
    para_words = [len(words(p)) for p in paras] or [0]

    def per_1k(count: int) -> float:
        return round(1000 * count / nw, 2)

    low = text.lower()
    uk = sum(len(re.findall(rf"\b{u}\w*", low)) for u, _ in _UK_US)
    us = sum(len(re.findall(rf"\b{a}\w*", low)) for _, a in _UK_US)
    openers = Counter(words(s)[0].lower() for s in sents if words(s))
    strong_ai = Counter(w for w in ws if w in AI_WORDS_STRONG)
    soft_ai = Counter(w for w in ws if w in AI_WORDS_SOFT)
    mean_len = float(np.mean(lens))

    return {
        "words": len(ws),
        "sentences": len(sents),
        "avg_sentence_words": round(mean_len, 1),
        "sentence_words_std": round(float(np.std(lens)), 1),
        "sentence_length_cv": round(float(np.std(lens) / mean_len), 2) if mean_len else 0.0,
        "short_sentence_share": round(sum(l <= 8 for l in lens) / len(lens), 2),
        "long_sentence_share": round(sum(l >= 30 for l in lens) / len(lens), 2),
        "avg_paragraph_sentences": round(float(np.mean(para_sents)), 1),
        "avg_paragraph_words": round(float(np.mean(para_words)), 1),
        "avg_word_length": round(float(np.mean([len(w) for w in ws])) if ws else 0.0, 2),
        "contractions_per_1k": per_1k(len(_CONTRACTION_RE.findall(text))),
        "i_me_my_per_1k": per_1k(sum(w in FIRST_SINGULAR for w in ws)),
        "we_our_per_1k": per_1k(sum(w in FIRST_PLURAL for w in ws)),
        "you_your_per_1k": per_1k(sum(w in SECOND for w in ws)),
        "hedges_per_1k": per_1k(sum(w in HEDGES for w in ws)),
        "boosters_per_1k": per_1k(sum(w in BOOSTERS for w in ws)),
        "passive_share": round(min(1.0, len(_PASSIVE_RE.findall(text)) / ns), 2),
        "nominalizations_per_1k": per_1k(len(_NOMINALIZATION_RE.findall(low))),
        "participle_clauses_per_1k": per_1k(_participle_clauses([s.lower() for s in sents])),
        "question_share": round(sum(s.rstrip().endswith("?") for s in sents) / ns, 2),
        "exclamation_share": round(sum(s.rstrip().endswith("!") for s in sents) / ns, 2),
        "em_dashes_per_1k": per_1k(text.count("—") + len(re.findall(r"\s--\s|\s–\s", text))),
        "semicolons_per_1k": per_1k(text.count(";")),
        "colons_per_1k": per_1k(len(re.findall(r":(?!//)", text))),
        "parentheses_per_1k": per_1k(text.count("(")),
        "ai_words_strong_per_1k": per_1k(sum(strong_ai.values())),
        "ai_words_soft_per_1k": per_1k(sum(soft_ai.values())),
        "ai_words_found": sorted((strong_ai + soft_ai).keys()),
        "spelling": "british" if uk > us else ("american" if us > uk else "unknown"),
        "top_openers": [w for w, _ in openers.most_common(8)],
    }
