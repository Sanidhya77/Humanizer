"""Measure how much a rewrite changed the writer's own text.

Why this exists: in a small test on GPTZero (docs/edit-budget.md), human-written
drafts stayed "Human" after a light or a middle edit and flipped to "AI" after a
heavy rewrite. The same paragraphs, the same facts; only the amount of rewording
differed. So the amount of rewording is measured and kept inside a budget.

What is counted:
  * Spelling and typing fixes ("teh" -> "the", "aswell" -> "as well") are
    CORRECTIONS. They are counted separately and do not use up the budget.
  * Case and punctuation changes are ignored.
  * Everything else (a different word, a moved phrase, a rebuilt sentence) is
    REWORDING. changed_pct is the share of characters that were reworded.

The budgets are starting values from that test, not guarantees. Detectors also
react to the kind of change, not only its size (Saha & Feizi 2025).
"""

from __future__ import annotations

import difflib
import re
from collections import Counter

from .features import AI_WORDS_SOFT, AI_WORDS_STRONG, HEDGES, text_stats
from .text_utils import paragraphs, sentences

# Share of characters reworded, per paragraph, after corrections are set aside.
# From docs/edit-budget.md: edits up to about 20% stayed "Human" (6 of 6 texts);
# edits of 36% and more were classed "AI" (3 of 3). Nothing was tested between.
BUDGETS = {"light": 12.0, "normal": 20.0}
HEAVY_PCT = 30.0
# Paragraphs shorter than this (headings, one-line intros) are measured but not
# held to the budget: one changed word is already a large share of them.
MIN_PARAGRAPH_WORDS = 25
# A sentence counts as kept / edited / rebuilt by the share of its words that
# still sit in the writer's original order.
_KEPT, _EDITED = 0.85, 0.5

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)*|%")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower().replace("’", "'"))


def _edit_distance(a: str, b: str, limit: int = 3) -> int:
    """Damerau-Levenshtein distance (a swap of two neighbours counts as 1)."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        prev2, prev = prev, cur
    return prev[-1]


_ENDINGS = {"", "s", "es", "ed", "d", "ing", "e", "y", "ies", "ied", "er", "ers", "ly"}


def _is_correction(old: str, new: str) -> bool:
    """True when `new` looks like `old` with its spelling or ending fixed."""
    if old == new:
        return False
    longest = max(len(old), len(new))
    if longest < 3 or old.isdigit() or new.isdigit():
        return False  # "is" -> "it", "3" -> "5": a different word or a changed fact
    allowed = 1 if longest < 5 else 2 if longest < 9 else 3
    if _edit_distance(old, new, allowed) <= allowed:
        return True
    if not (old.isalpha() and new.isalpha()):
        return False
    # Same word with another ending: "working" -> "worked". A grammar fix, not a new word.
    k = 0
    while k < min(len(old), len(new)) and old[k] == new[k]:
        k += 1
    if k >= 4 and old[k:] in _ENDINGS and new[k:] in _ENDINGS:
        return True
    # Badly mistyped but the same letters: "cusae" -> "because", "imapleting" -> "implementing".
    if min(len(old), len(new)) >= 5:
        a, b = Counter(old), Counter(new)
        shared = sum((a & b).values())
        return shared / (len(old) + len(new) - shared) >= 0.68
    return False


def _apply_corrections(a: list[str], b: list[str]) -> tuple[list[str], int]:
    """Return the original tokens with spelling fixes applied, and how many were applied.

    The rewrite `b` shows what each misspelled word was corrected to. Applying those
    fixes to the original first means the comparison that follows measures rewording only.
    """
    out: list[str] = []
    fixed = 0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or tag == "delete":
            out.extend(a[i1:i2])
            continue
        if tag == "insert":
            continue
        old, new = a[i1:i2], b[j1:j2]
        j = 0
        for k, w in enumerate(old):
            hit = None
            for look in range(j, min(j + 3, len(new))):
                v = new[look]
                if _is_correction(w, v):
                    hit = (look, [v])
                    break
                # "aswell" -> "as well"
                if look + 1 < len(new) and _edit_distance(w, v + new[look + 1], 1) <= 1 and len(w) >= 4:
                    hit = (look + 1, [v, new[look + 1]])
                    break
                # "any thing" -> "anything"
                if k + 1 < len(old) and _edit_distance(w + old[k + 1], v, 1) <= 1 and len(v) >= 4:
                    hit = (look, [v])
                    break
            if hit:
                j = hit[0] + 1
                if out[-1:] != hit[1]:  # second half of a joined pair is already in
                    out.extend(hit[1])
                fixed += 1
            else:
                out.append(w)
    return out, fixed


def _pct(x: float) -> float:
    return round(100 * x, 1)


_FUNCTION_WORDS = set(
    "a an the this that these those it its i me my we us our you your he she they them their and or but so if as "
    "of in on at to for from by with about into over under than then also is are was were be been being am do does "
    "did has have had not no can could will would shall should may might must there here what which who when "
    "where why how all any each some both more most very just only even still too".split())


def _word_swaps(a_fixed: list[str], b: list[str]) -> list[tuple[str, str]]:
    """One word replaced by one different word: 'hunt' -> 'search'.

    These are the "better word" swaps. Each one replaces a choice the writer made
    with a choice the editor made, and changes nothing else.
    """
    swaps = []
    sm = difflib.SequenceMatcher(None, a_fixed, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and i2 - i1 == j2 - j1 <= 2:
            for old, new in zip(a_fixed[i1:i2], b[j1:j2]):
                if old != new and old not in _FUNCTION_WORDS and new not in _FUNCTION_WORDS \
                        and old.isalpha() and new.isalpha() and len(old) > 2 and len(new) > 2 \
                        and not _is_correction(old, new):
                    swaps.append((old, new))
    return swaps


# Style drift is a set of notes for the editor, not a pass/fail test. Every check needs a
# minimum number of occurrences, because one word more or less in a 100-word text is noise.
_DRIFT_MIN_WORDS = 80
_FIRST_PERSON = {"i", "me", "my", "mine", "myself", "i'm", "i've", "i'll", "i'd"}
_PRONOUNS = _FIRST_PERSON | {"we", "us", "our", "ours", "you", "your", "yours", "he", "him", "his", "she", "her",
                             "hers", "they", "them", "their", "theirs", "we're", "we've", "you're", "they're"}
_OPINION_RE = re.compile(
    r"\bi (?:think|believe|doubt|suspect|disagree|agree|prefer|would argue|am not sure|don't think|do not think)\b"
    r"|\bin my (?:opinion|view)\b|\bmy (?:opinion|view|answer|argument) is\b", re.IGNORECASE)
_NOMINAL_RE = re.compile(r"^[a-z]{3,}(?:tion|tions|sion|sions|ment|ments|ness|nesses|ity|ities|ance|ances|ence|ences)$")
_CONTRACTION_TOKEN_RE = re.compile(r"^[a-z]+(?:n't|'re|'ve|'ll|'d|'m)$|^(?:it|that|there|what|here|he|she|who|let)'s$")


def _style_drift(o_tokens: list[str], r_tokens: list[str], original: str, rewrite: str,
                 clean_original: bool) -> dict:
    """Did the edit pull the text toward the way models write?

    The writer's own draft is the reference (o_tokens: its words with spelling fixed).
    Research on LLM style (Reinhart et al. 2025; Kobak et al. 2025) finds more
    nominalizations and "-ing" clauses, a set of favoured words, and a more even, more
    formal surface than people produce. An edit that adds those to a text that did not
    have them is moving it the wrong way.

    clean_original: the original needed few spelling fixes, so its punctuation-based
    statistics (sentence rhythm, "-ing" clauses) can be trusted.
    """
    ai_words = AI_WORDS_STRONG | AI_WORDS_SOFT
    introduced = sorted({w for w in r_tokens if w in ai_words} - set(o_tokens))
    flags: list[str] = []
    if introduced:
        flags.append("The edit added words that models overuse: " + ", ".join(introduced)
                     + ". Use the writer's own word.")
    o_dash = original.count("—") + len(re.findall(r"\s--\s|\s–\s", original))
    r_dash = rewrite.count("—") + len(re.findall(r"\s--\s|\s–\s", rewrite))
    if r_dash > o_dash:
        flags.append(f"The edit added {r_dash - o_dash} dash(es) used as a connector. The writer used {o_dash}.")
    out: dict = {"introduced_ai_words": introduced, "flags": flags}
    if min(len(o_tokens), len(r_tokens)) < _DRIFT_MIN_WORDS:
        return out
    table: dict = {}

    def count(tokens: list[str], test) -> int:
        return sum(1 for t in tokens if test(t))

    a, b = count(o_tokens, _CONTRACTION_TOKEN_RE.match), count(r_tokens, _CONTRACTION_TOKEN_RE.match)
    table["contractions"] = [a, b]
    if a >= 3 and b <= a / 2:
        flags.append("The writer's contractions were written out in full. Keep them unless the register forbids them.")
    a, b = count(o_tokens, _FIRST_PERSON.__contains__), count(r_tokens, _FIRST_PERSON.__contains__)
    table["first_person_words"] = [a, b]
    if a >= 4 and b <= a / 2:
        flags.append("First-person wording (I, my) was removed. Keep the writer in the text unless the register forbids it.")
    a, b = count(o_tokens, _PRONOUNS.__contains__), count(r_tokens, _PRONOUNS.__contains__)
    table["personal_pronouns"] = [a, b]
    if a >= 8 and b <= a * 0.6 and not any("First-person" in f for f in flags):
        flags.append("Personal pronouns (we, you, they) were replaced by nouns. The text reads less personal than the writer's.")
    a, b = count(o_tokens, HEDGES.__contains__), count(r_tokens, HEDGES.__contains__)
    table["hedging_words"] = [a, b]
    if b - a >= 3 and b >= a * 1.5:
        flags.append("The edit added hedging (may, might, perhaps, generally). It softens claims the writer made plainly.")
    a, b = len(_OPINION_RE.findall(original)), len(_OPINION_RE.findall(rewrite))
    table["stated_opinions"] = [a, b]
    if a >= 2 and b <= a / 2:
        flags.append("Stated opinions (I think, in my view) were removed. Do not make the writer's position neutral.")
    a, b = count(o_tokens, _NOMINAL_RE.match), count(r_tokens, _NOMINAL_RE.match)
    table["abstract_nouns"] = [a, b]
    if b - a >= 4 and b >= a * 1.5:
        flags.append("More abstract nouns (-tion, -ment, -ity) than the original. Go back to the writer's verbs.")

    def word_len(tokens: list[str]) -> float:
        ws = [t for t in tokens if t.isalpha()]
        return sum(map(len, ws)) / len(ws) if ws else 0.0

    a, b = word_len(o_tokens), word_len(r_tokens)
    table["avg_word_length"] = [round(a, 2), round(b, 2)]
    if a and (b - a) / a > 0.06 and min(len(o_tokens), len(r_tokens)) >= 150:
        flags.append("Words got longer on average. Plain words were probably swapped for formal ones.")

    if clean_original:
        o, r = text_stats(original), text_stats(rewrite)
        a = round(o["participle_clauses_per_1k"] * o["words"] / 1000)
        b = round(r["participle_clauses_per_1k"] * r["words"] / 1000)
        table["ing_clauses"] = [a, b]
        if b - a >= 3 and b >= a * 1.5:
            flags.append("More '-ing' clauses than the original (', making it ...'). Models overuse them.")
        if min(o["sentences"], r["sentences"]) >= 8 and 0.6 <= o["sentences"] / r["sentences"] <= 1.6:
            table["sentence_length_variation"] = [o["sentence_length_cv"], r["sentence_length_cv"]]
            table["avg_sentence_words"] = [o["avg_sentence_words"], r["avg_sentence_words"]]
            if o["sentence_length_cv"] - r["sentence_length_cv"] >= 0.12:
                flags.append("Sentence lengths became more even. Keep the writer's mix of short and long sentences.")
    out["before_after"] = table
    return out


def _ratio_changed(a, b) -> float:
    if not a and not b:
        return 0.0
    return 1 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _compare_paragraph(orig: str, new: str) -> dict:
    a, b = _tokens(orig), _tokens(new)
    a_fixed, corrections = (a, 0) if a == b else _apply_corrections(a, b)
    sa, sb = " ".join(a_fixed), " ".join(b)
    sm = difflib.SequenceMatcher(None, a_fixed, b, autojunk=False)
    kept_flags = [False] * len(b)
    for m in sm.get_matching_blocks():
        for j in range(m.b, m.b + m.size):
            kept_flags[j] = True

    # per-sentence: how much of each rewritten sentence is the writer's own wording
    sent_rows = []
    pos = 0
    for s in sentences(new):
        n = len(_tokens(s.text))
        if n == 0:
            continue
        share = sum(kept_flags[pos:pos + n]) / n
        pos += n
        kind = "kept" if share >= _KEPT else "edited" if share >= _EDITED else "rebuilt"
        sent_rows.append({"text": s.text, "writer_words_pct": _pct(share), "kind": kind})

    match_chars = sum(m.size for m in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_matching_blocks())
    return {
        "swaps": _word_swaps(a_fixed, b),
        "a_fixed": a_fixed, "b": b, "orig_words": len(a),
        "words": len(b),
        "orig_chars": len(sa), "new_chars": len(sb), "match_chars": match_chars,
        "changed_pct": _pct(1 - 2 * match_chars / (len(sa) + len(sb))) if (sa or sb) else 0.0,
        "words_changed_pct": _pct(_ratio_changed(a_fixed, b)),
        "raw_changed_pct": _pct(_ratio_changed(" ".join(a), sb)),
        "corrections": corrections,
        "kept_words": sum(kept_flags),
        "sentences": sent_rows,
    }


def _align_paragraphs(olds: list[str], news: list[str]) -> list[tuple[int | None, int | None]]:
    """Pair each rewritten paragraph with the original paragraph it came from, in order."""
    so = [set(_tokens(p)) for p in olds]
    sn = [set(_tokens(p)) for p in news]

    def sim(i: int, j: int) -> float:
        u = so[i] | sn[j]
        return len(so[i] & sn[j]) / len(u) if u else 1.0

    n, m = len(olds), len(news)
    gap = 0.25  # a pair must share more than this to beat "removed + added"
    if n == m:
        # The usual case: paragraphs kept one to one. A paragraph that shares almost
        # nothing with its original is then reported as a heavy rewrite, which it is.
        return list(zip(range(n), range(m)))
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            score[i][j] = max(score[i + 1][j + 1] + sim(i, j) - gap, score[i + 1][j], score[i][j + 1])
    pairs: list[tuple[int | None, int | None]] = []
    i = j = 0
    while i < n and j < m:
        if score[i][j] == score[i + 1][j + 1] + sim(i, j) - gap and sim(i, j) > gap:
            pairs.append((i, j)); i += 1; j += 1
        elif score[i][j] == score[i + 1][j]:
            pairs.append((i, None)); i += 1
        else:
            pairs.append((None, j)); j += 1
    pairs += [(k, None) for k in range(i, n)] + [(None, k) for k in range(j, m)]
    return pairs


def _preview(text: str, n: int = 12) -> str:
    ws = text.split()
    return " ".join(ws[:n]) + (" ..." if len(ws) > n else "")


def measure_change(original: str, rewrite: str, mode: str = "normal",
                   budget_pct: float | None = None, detail: bool = False) -> dict:
    """Compare a rewrite with the writer's original, paragraph by paragraph."""
    if mode not in BUDGETS:
        raise ValueError(f"mode must be one of: {', '.join(BUDGETS)}")
    budget = float(budget_pct) if budget_pct is not None else BUDGETS[mode]
    if not 0 < budget <= 100:
        raise ValueError("budget_pct must be between 0 and 100")

    def body(text: str) -> list[str]:
        return [p.text for p in paragraphs(text)]

    olds, news = body(original), body(rewrite)
    rows: list[dict] = []
    tot_o = tot_n = tot_match = tot_words = tot_kept = tot_corr = 0
    tot_raw_o = tot_raw_match = 0.0
    counts = {"kept": 0, "edited": 0, "rebuilt": 0, "new": 0}
    removed: list[str] = []
    swaps: list[tuple[str, str]] = []
    o_tokens: list[str] = []
    r_tokens: list[str] = []
    tot_orig_words = 0

    for oi, ni in _align_paragraphs(olds, news):
        if ni is None:
            a = " ".join(_tokens(olds[oi]))
            tot_o += len(a)
            removed.append(_preview(olds[oi]))
            continue
        if oi is None:
            b = _tokens(news[ni])
            sb = " ".join(b)
            tot_n += len(sb); tot_words += len(b)
            sents = [s.text for s in sentences(news[ni]) if _tokens(s.text)]
            counts["new"] += len(sents)
            rows.append({"paragraph": ni + 1, "words": len(b), "changed_pct": 100.0, "words_changed_pct": 100.0,
                         "corrections": 0, "status": "added", "starts": _preview(news[ni]),
                         "rebuilt_sentences": [_preview(s) for s in sents]})
            continue
        r = _compare_paragraph(olds[oi], news[ni])
        tot_o += r["orig_chars"]; tot_n += r["new_chars"]; tot_match += r["match_chars"]
        tot_words += r["words"]; tot_kept += r["kept_words"]; tot_corr += r["corrections"]
        swaps += r["swaps"]
        o_tokens += r["a_fixed"]; r_tokens += r["b"]; tot_orig_words += r["orig_words"]
        for s in r["sentences"]:
            counts[s["kind"]] += 1
        short = r["words"] < MIN_PARAGRAPH_WORDS
        if r["changed_pct"] == 0 and r["corrections"] == 0:
            status = "unchanged"
        elif short:
            status = "short"
        elif r["changed_pct"] >= HEAVY_PCT:
            status = "heavy"
        elif r["changed_pct"] > budget:
            status = "over_budget"
        else:
            status = "within_budget"
        rows.append({"paragraph": ni + 1, "words": r["words"], "changed_pct": r["changed_pct"],
                     "words_changed_pct": r["words_changed_pct"], "corrections": r["corrections"],
                     "status": status, "starts": _preview(news[ni]),
                     "rebuilt_sentences": [_preview(s["text"]) for s in r["sentences"] if s["kind"] == "rebuilt"]})

    doc_changed = _pct(1 - 2 * tot_match / (tot_o + tot_n)) if (tot_o + tot_n) else 0.0
    writer_words = _pct(tot_kept / tot_words) if tot_words else 100.0
    over = [r for r in rows if r["status"] in ("over_budget", "heavy", "added")]
    zone = "heavy" if doc_changed >= HEAVY_PCT else "over_budget" if doc_changed > budget else "within_budget"
    rebuilt = counts["rebuilt"] + counts["new"]

    advice: list[str] = []
    if over:
        advice.append(
            f"{len(over)} paragraph(s) are over the {budget:g}% budget. Go back to the writer's original wording "
            "there and keep only the fixes that are needed (errors, AI patterns). Do not rebuild sentences.")
    if rebuilt:
        advice.append(
            f"{rebuilt} sentence(s) were rebuilt or are new. If a sentence really needs a "
            "rewrite, show it to the writer as a suggestion or ask them to rewrite it, instead of replacing it.")
    if removed:
        advice.append(f"{len(removed)} original paragraph(s) have no match in the rewrite. Check that nothing was cut.")
    clean = tot_orig_words > 0 and tot_corr / tot_orig_words < 0.03
    drift = _style_drift(o_tokens, r_tokens, original, rewrite, clean_original=clean)
    if swaps:
        advice.append(
            f"{len(swaps)} word(s) were swapped for another word. Undo every swap that does not fix an error "
            "or remove an AI pattern: the writer's word was a choice.")
    advice += drift["flags"]
    if not advice:
        advice.append("Within budget. The text is still mostly the writer's own wording.")

    out = {
        "ok": zone == "within_budget" and not over and not rebuilt and not removed,
        "mode": mode,
        "budget_pct": budget,
        "changed_pct": doc_changed,
        "zone": zone,
        "writer_words_pct": writer_words,
        "corrections": tot_corr,
        "sentences": {"total": sum(counts.values()), **counts},
        "word_swaps": {"count": len(swaps), "examples": [f"{a} -> {b}" for a, b in swaps[:20]]},
        "style_drift": drift,
        "paragraphs_total": len(news),
        "paragraphs_over_budget": over,
        "removed_paragraphs": removed,
        "advice": advice,
        "how_to_read": (
            "changed_pct = share of characters reworded, after spelling fixes are set aside. "
            "writer_words_pct = share of the final words that are the writer's own, in their own order. "
            "In the test behind these budgets (docs/edit-budget.md), edits up to about 20% with no rebuilt "
            "sentences stayed Human on GPTZero, and edits of 36% or more were classed AI. Nothing between was "
            "tested. This is a guide, not a prediction."),
    }
    if detail:
        out["paragraphs"] = rows
    return out
