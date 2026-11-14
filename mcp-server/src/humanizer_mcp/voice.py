"""Voice profiles and the register-aware voice check.

Two layers, applied in this order:

1. REGISTER (registers.py): what is normal for this kind of writing, as ranges.
   A text outside a register range is a real problem in that register.
2. PERSONAL VOICE (a profile learned from the writer's own texts): how this
   writer tends to write. It only steers features inside the register's range
   and only for features that carry over between genres. A habit from blogs
   (contractions, "you") never gets pushed into a research article.

The strength setting decides how hard the personal voice pulls:
    off    - register checks for AI patterns only, no voice
    light  - register ranges only (default for academic text)
    medium - also nudge toward the writer's habits, within the register (default for blogs)
    strong - tighter nudging, plus the writer's recurring phrases
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import config, registers
from .features import text_stats
from .text_utils import paragraphs, words

_STOPWORDS = set(
    """a about above after again against all am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is it
    its itself just me more most my myself no nor not now of off on once only or other our ours
    ourselves out over own same she should so some such than that the their theirs them themselves
    then there these they this those through to too under until up very was we were what when where
    which while who whom why will with would you your yours yourself yourselves also one two new
    like get got make made many much may might must us use used using way well even still really
    s t don didn isn wasn aren doesn can't it's i'm that's there's""".split()
)

# Tolerance for "personal drift" at medium strength (absolute units of each feature).
_TOLERANCE = {
    "avg_sentence_words": 3.0, "sentence_length_cv": 0.12, "short_sentence_share": 0.08,
    "avg_paragraph_words": 30.0, "hedges_per_1k": 2.0, "boosters_per_1k": 2.0, "passive_share": 0.10,
    "i_me_my_per_1k": 5.0, "we_our_per_1k": 5.0, "semicolons_per_1k": 2.0, "parentheses_per_1k": 6.0,
    "colons_per_1k": 2.5, "em_dashes_per_1k": 1.0,
}
# Punctuation habits come from content (citations, units, lists), so the voice may only
# reduce them toward the writer's rate, never ask for more.
_REDUCE_ONLY = {"parentheses_per_1k", "colons_per_1k", "semicolons_per_1k", "em_dashes_per_1k"}
_DEFAULT_STRENGTH = {"academic": "light", "platform": "medium", "custom": "medium"}


def _safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-]+", "-", name.strip()).strip("-").lower()
    if not s:
        raise ValueError("Profile name must contain letters or numbers.")
    return s


def _vocabulary(text: str, top: int = 30) -> tuple[list[str], list[str]]:
    ws = [w.lower().strip("'’") for w in words(text)]
    content = [w for w in ws if w not in _STOPWORDS and len(w) > 2]
    vocab = [w for w, c in Counter(content).most_common(top * 2) if c >= 2][:top]
    def ok(t: str) -> bool:
        return len(t) >= 3 and t not in {"et", "al"}
    bigrams = Counter(f"{a} {b}" for a, b in zip(ws, ws[1:])
                      if ok(a) and ok(b) and (a not in _STOPWORDS or b not in _STOPWORDS))
    phrases = [p for p, c in bigrams.most_common(40) if c >= 2 and not all(x in _STOPWORDS for x in p.split())][:15]
    return vocab, phrases


def _style_guide(s: dict) -> list[str]:
    g = [
        f"Sentences average about {s['avg_sentence_words']:.0f} words; "
        f"{int(s['short_sentence_share'] * 100)}% are 8 words or fewer and "
        f"{int(s['long_sentence_share'] * 100)}% are 30 or more.",
        f"Paragraphs run about {s['avg_paragraph_words']:.0f} words.",
    ]
    if s["sentence_length_cv"] >= 0.45:
        g.append("Sentence length varies a lot; keep that unevenness.")
    c = s["contractions_per_1k"]
    g.append("Uses contractions freely." if c >= 15 else "Uses some contractions." if c >= 4 else "Writes words out in full; no contractions.")
    if s["i_me_my_per_1k"] >= 10:
        g.append("Writes in the first person singular (I, my).")
    elif s["we_our_per_1k"] >= 5:
        g.append("Uses 'we' for the authors' actions.")
    else:
        g.append("Keeps the writer out of the text (impersonal subjects, 'this thesis', passive).")
    if s["you_your_per_1k"] >= 8:
        g.append("Talks to the reader as 'you'.")
    if s["boosters_per_1k"] < 2:
        g.append("Rarely uses intensifiers (clearly, very, significantly).")
    if s["passive_share"] >= 0.30:
        g.append("Uses the passive voice often.")
    if s["em_dashes_per_1k"] < 0.5:
        g.append("Never uses dashes as connectors.")
    if s["semicolons_per_1k"] >= 2:
        g.append("Uses semicolons to join related clauses.")
    if s["parentheses_per_1k"] >= 8:
        g.append("Uses parentheses a lot: definitions, abbreviations, units, citations.")
    if s["spelling"] != "unknown":
        g.append(f"{s['spelling'].title()} spelling.")
    if s.get("top_openers"):
        g.append("Common sentence openers: " + ", ".join(s["top_openers"][:6]) + ".")
    return g


def _excerpts(texts: list[str], budget_words: int = 900) -> list[str]:
    picks: list[str] = []
    per_text = max(1, 4 // max(len(texts), 1))
    used = 0
    for t in texts:
        paras = [p.text for p in paragraphs(t) if 40 <= len(words(p.text)) <= 220 and not p.text.startswith("#")]
        if not paras:
            continue
        step = max(1, len(paras) // per_text)
        for p in paras[::step][:per_text]:
            n = len(words(p))
            if used + n > budget_words:
                break
            picks.append(p)
            used += n
    return picks


def build_profile(name: str, texts: list[str], description: str = "", genre: str = "blog",
                  register: str | None = None, private: bool = False) -> dict:
    """genre: free text label. register: the register the samples were written in
    (e.g. "academic:undergraduate:cs_engineering" or "blog_personal"), so the voice
    is applied first to that register and only partially elsewhere.
    private: keep only numeric stats and the style guide; store no excerpts, words or
    phrases from the samples (for text you may not share, such as client work)."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        raise ValueError("Give at least one writing sample.")
    joined = "\n\n".join(texts)
    if len(words(joined)) < 300:
        raise ValueError("Need at least ~300 words of the writer's own text (1,500+ is better).")
    if register:
        registers.resolve(register)  # validate
    stats = text_stats(joined)
    vocab, phrases = ([], []) if private else _vocabulary(joined)
    if private:
        stats = {k: v for k, v in stats.items() if k not in ("top_openers", "ai_words_found")}
    return {
        "name": _safe_name(name),
        "description": description,
        "genre": genre,
        "register": register,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample_count": len(texts),
        "stats": stats,
        "style_guide": _style_guide(stats),
        "favourite_words": vocab,
        "recurring_phrases": phrases,
        "excerpts": [] if private else _excerpts(texts),
        "private": private,
    }


def save_profile(profile: dict) -> Path:
    path = config.profiles_dir() / f"{profile['name']}.json"
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_profile(name: str) -> dict:
    path = config.profiles_dir() / f"{_safe_name(name)}.json"
    if not path.exists():
        available = list_profiles()
        raise FileNotFoundError(
            f"No voice profile '{name}'. Available: {', '.join(p['name'] for p in available) or 'none yet'}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def list_profiles() -> list[dict]:
    out = []
    for p in sorted(config.profiles_dir().glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({"name": d["name"], "genre": d.get("genre", ""), "register": d.get("register"),
                        "description": d.get("description", ""), "words_sampled": d["stats"]["words"]})
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return out


def _fmt(v: float) -> float:
    return round(v, 2)


def _default_strength(reg: dict | None) -> str:
    """light for academic text, medium for everything else.

    Registers measured from real texts have kind "measured", so the kind alone does
    not say whether they are academic. The name does ("academic:masters:business").
    """
    if not reg:
        return _DEFAULT_STRENGTH["custom"]
    if str(reg.get("name", "")).startswith("academic"):
        return "light"
    return _DEFAULT_STRENGTH.get(reg.get("kind", "custom"), "medium")


# A one-line lead-in under a heading ("This chapter covers ...") is a normal paragraph
# in a report, but it drags the average paragraph length down.
_INTRO_MAX_WORDS = 25


def _body_paragraph_words(text: str) -> float | None:
    """Average paragraph length without headings and one-line lead-ins."""
    sizes = [len(words(p.text)) for p in paragraphs(text) if not p.text.lstrip().startswith("#")]
    body = [n for n in sizes if n >= _INTRO_MAX_WORDS]
    return sum(body) / len(body) if body else None


def check_voice(text: str, register: str | None = None, profile: dict | None = None,
                strength: str | None = None, section: str | None = None,
                level: str | None = None, domain: str | None = None) -> dict:
    """Check a draft against a register and (optionally) a personal voice.

    Returns:
      must_fix         - features outside the register range (real problems in this genre)
      voice_nudges     - optional moves toward the writer's habits, already clamped to the register
      not_applied      - writer habits deliberately NOT applied because the register rules them out
      ai_patterns      - AI-typical patterns found (participle clauses, nominalizations, AI words)
    """
    if not register and not (level or domain) and profile and profile.get("register"):
        register = profile["register"]
    reg = registers.resolve(register, level=level, domain=domain, section=section) if (register or level or domain) else None
    strength = (strength or _default_strength(reg)).lower()
    if strength not in {"off", "light", "medium", "strong"}:
        raise ValueError("strength must be off, light, medium or strong")

    draft = text_stats(text)
    must_fix, nudges, not_applied, ai_patterns, optional = [], [], [], [], []

    # The writer's own past text in THIS register is evidence of what is normal for them:
    # widen the register's range to include their habits (transferable features only).
    widened = []
    if reg and profile and profile.get("register") and \
            profile["register"].split("@")[0] == reg["name"].split("@")[0]:
        reg = dict(reg, ranges=dict(reg["ranges"]))
        for feat in registers.TRANSFERABLE:
            w = profile["stats"].get(feat)
            if w is None or feat not in reg["ranges"]:
                continue
            lo, hi = reg["ranges"][feat]
            new_lo, new_hi = min(lo, w * 0.95), max(hi, w * 1.05)
            if (new_lo, new_hi) != (lo, hi):
                reg["ranges"][feat] = (round(new_lo, 3), round(new_hi, 3))
                widened.append(feat)

    if reg:
        for feat, (lo, hi) in reg["ranges"].items():
            v = draft.get(feat)
            if v is None:
                continue
            is_ai = feat in {"participle_clauses_per_1k", "nominalizations_per_1k",
                             "ai_words_strong_per_1k", "ai_words_soft_per_1k"}
            if strength == "off" and not is_ai:
                continue
            if feat == "avg_paragraph_words" and v < lo:
                body = _body_paragraph_words(text)
                if body is not None and body >= lo:
                    continue  # only short because of one-line lead-ins under headings
            if v > hi or v < lo:
                over = v > hi
                tip = registers.ADVICE.get(feat, ("", ""))[0 if over else 1]
                if not tip:
                    continue
                item = {"feature": feat, "draft": _fmt(v), "range": [lo, hi], "advice": tip}
                if feat.startswith("ai_words"):
                    item["words"] = draft["ai_words_found"]
                if not over and feat in registers.LOWER_BOUND_OPTIONAL:
                    item["advice"] = "Optional: " + tip + " Only if the text reads stiff; being below typical is fine."
                    optional.append(item)
                    continue
                (ai_patterns if is_ai else must_fix).append(item)

    if profile and strength in {"medium", "strong"}:
        target_stats = profile["stats"]
        same_register = bool(reg and profile.get("register") and profile["register"].split("@")[0] == reg["name"].split("@")[0])
        scale = 0.5 if strength == "strong" else 1.0
        if not same_register:
            scale *= 1.5  # different genre: only pull on big gaps
        for feat in sorted(registers.TRANSFERABLE):
            if feat not in target_stats or feat not in draft:
                continue
            want = target_stats[feat]
            if reg and feat in reg["ranges"]:
                lo, hi = reg["ranges"][feat]
                clamped = min(max(want, lo), hi)
                if abs(clamped - want) > 1e-9:
                    not_applied.append({"feature": feat, "writer": _fmt(want), "register_range": [lo, hi],
                                        "why": "Writer's habit is outside what this register allows; using the register's limit instead."})
                want = clamped
            d = draft[feat]
            tol = _TOLERANCE.get(feat, 1.0) * scale
            if feat in _REDUCE_ONLY and d <= want:
                continue
            if abs(d - want) > tol:
                nudges.append({"feature": feat, "draft": _fmt(d), "writer_target": _fmt(want),
                               "advice": f"{'Lower' if d > want else 'Raise'} {feat.replace('_', ' ')} toward {_fmt(want)}."})
        if reg:
            for feat in sorted(registers.REGISTER_ONLY):
                if feat.startswith("ai_words") or feat in ("nominalizations_per_1k", "participle_clauses_per_1k"):
                    continue  # AI-pattern ceilings, never a writer habit to carry over
                if feat in target_stats and feat in reg["ranges"]:
                    lo, hi = reg["ranges"][feat]
                    w = target_stats[feat]
                    if w > hi or w < lo:
                        not_applied.append({"feature": feat, "writer": _fmt(w), "register_range": [lo, hi],
                                            "why": "Genre-specific habit; never carried into this register."})
        sp = target_stats.get("spelling")
        if sp and sp != "unknown" and draft["spelling"] not in ("unknown", sp):
            nudges.append({"feature": "spelling", "draft": draft["spelling"], "writer_target": sp,
                           "advice": f"Switch to {sp} spelling."})
        if strength == "strong":
            nudges.append({"feature": "phrases", "advice": "Where it fits naturally, prefer the writer's own recurring phrases.",
                           "phrases": profile.get("recurring_phrases", [])[:10]})

    checked = len(reg["ranges"]) if reg else 0
    score = 100 if not checked else max(0, round(100 * (1 - (len(must_fix) + len(ai_patterns)) / checked)))
    return {
        "register": reg["name"] if reg else None,
        "register_label": reg["label"] if reg else None,
        "strength": strength,
        "register_fit": score,
        "must_fix": must_fix,
        "ai_patterns": ai_patterns,
        "voice_nudges": nudges,
        "optional": optional,
        "not_applied": not_applied,
        "widened_by_your_writing": widened,
        "register_guide": reg["guide"] if reg else [],
        "draft_stats": {k: v for k, v in draft.items() if k not in ("top_openers",)},
        "rule": ("Fix must_fix and ai_patterns. Apply voice_nudges and optional items only where they read "
                 "naturally; never force them into a sentence that already works. Never apply anything in not_applied."),
    }


def compare_to_voice(text: str, profile: dict) -> dict:
    """Backward-compatible: personal-voice comparison in the profile's own register."""
    return check_voice(text, register=profile.get("register"), profile=profile, strength="medium")
