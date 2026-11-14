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


def _is_correction(old: str, new: str) -> bool:
    """True when `new` looks like `old` with its spelling or ending fixed."""
    if old == new:
        return False
    longest = max(len(old), len(new))
    if longest < 3 or old.isdigit() or new.isdigit():
        return False  # "is" -> "it", "3" -> "5": a different word or a changed fact
    allowed = 1 if longest < 5 else 2 if longest < 9 else 3
    return _edit_distance(old, new, allowed) <= allowed


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
