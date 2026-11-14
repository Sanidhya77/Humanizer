"""Register presets: what "normal" looks like for a kind of writing.

A register is a set of acceptable RANGES (low, high) for the features in
features.py, plus a short plain-English guide. Ranges, not targets: real
writers vary, and forcing every text onto one number is exactly what makes
"humanized" text read strangely.

Academic registers are built from a LEVEL (high school ... published article)
and a DOMAIN (CS/engineering ... humanities). Non-academic registers are
named platforms (personal blog, LinkedIn, ...).

Where the numbers come from (details and links in REGISTERS.md):
  * Anchors measured with this tool on real texts (a CS bachelor thesis and a
    CS journal article), so the ranges are in this tool's units.
  * Ratios from corpus research: soft fields hedge about twice as much as hard
    fields (Hyland); first-year writers over-use boosters and under-use hedges
    (Aull & Lancaster 2014); PhD writing carries more metadiscourse than
    master's (Hyland & Tse 2004); research-article sentences average about
    25 words (Gray 2011; education RAs 24.7); median paragraph 109 words, most
    65-167 (PubMed Central sample of 9,830 papers); about 30% of clauses passive
    in science articles, much more in methods (Alvin 2014; Martinez 2001).
  * AI tells: instruction-tuned LLMs use present participial clauses at 2-5x
    and nominalizations at 1.5-2x the human rate (Reinhart et al., PNAS 2025).
  * Social platforms: practitioner data (LinkedIn readability studies), so treat
    those ranges as softer guidance.

Users can add or override registers with scripts/build_register.py, which
measures a folder of real texts and writes a JSON file to HUMANIZER_HOME/registers.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from . import config

Range = tuple[float, float]

# ---------------------------------------------------------------- academic

# Baseline: a published research article in a general field.
_ACADEMIC_BASE: dict[str, Range] = {
    "avg_sentence_words": (19, 28),
    "sentence_length_cv": (0.35, 0.80),
    "short_sentence_share": (0.03, 0.20),
    "avg_paragraph_words": (60, 180),
    "contractions_per_1k": (0, 0.5),
    "i_me_my_per_1k": (0, 4),
    "we_our_per_1k": (0, 12),
    "you_your_per_1k": (0, 0.5),
    "hedges_per_1k": (1.5, 9),
    "boosters_per_1k": (0.3, 5),
    "passive_share": (0.10, 0.45),
    "nominalizations_per_1k": (30, 95),
    "participle_clauses_per_1k": (0, 7),
    "question_share": (0, 0.03),
    "exclamation_share": (0, 0.0),
    "em_dashes_per_1k": (0, 2),
    "ai_words_strong_per_1k": (0, 0.5),
    "ai_words_soft_per_1k": (0, 2.5),
}

LEVELS: dict[str, dict] = {
    "high_school": {
        "label": "High school / secondary school (essays, extended essays, school theses)",
        "shift": {"avg_sentence_words": (-6, -8), "nominalizations_per_1k": (-15, -40),
                  "hedges_per_1k": (-1.5, -4), "boosters_per_1k": (1, 4),
                  "i_me_my_per_1k": (0, 6), "contractions_per_1k": (0, 2.5),
                  "question_share": (0, 0.03), "passive_share": (-0.05, -0.15),
                  "avg_paragraph_words": (-15, -40)},
        "guide": [
            "Plain, direct sentences; mostly 12-20 words.",
            "A clear thesis statement and topic sentences; some first person ('I argue') is normal in essays.",
            "Real students state opinions firmly; a few boosters are fine, heavy hedging is not typical.",
            "Simple vocabulary over technical nouns; avoid stacked abstractions.",
        ],
    },
    "undergraduate": {
        "label": "Undergraduate / bachelor (essays, reports, bachelor thesis)",
        "shift": {"avg_sentence_words": (-2, -1), "nominalizations_per_1k": (-5, -5),
                  "hedges_per_1k": (-0.5, -1), "boosters_per_1k": (0.5, 1)},
        "guide": [
            "Formal but not dense; sentences mostly 17-26 words.",
            "Thesis-style signposting ('This chapter...', 'The third chapter...') is normal and expected.",
            "Claims tied to sources; hedge interpretations, not measured facts.",
        ],
    },
    "masters": {
        "label": "Master's (dissertation, research report)",
        "shift": {"hedges_per_1k": (0, 0.5)},
        "guide": [
            "Hedges are the most common stance marker at this level; use them on interpretations.",
            "Explicit research questions and methodology justification.",
        ],
    },
    "phd": {
        "label": "PhD (thesis, confirmation report)",
        "shift": {"avg_sentence_words": (1, 1), "hedges_per_1k": (0.5, 2), "boosters_per_1k": (0, 0.5),
                  "i_me_my_per_1k": (0, 1), "avg_paragraph_words": (0, 20)},
        "guide": [
            "More metadiscourse than a master's: map the argument, position against the literature.",
            "Careful, calibrated claims: hedge interpretations, state results plainly.",
        ],
    },
    "published": {
        "label": "Published research article / journal or conference paper",
        "shift": {},
        "guide": [
            "Concise and evidence-led; every claim scoped to what was tested.",
            "Section conventions: passive common in methods, active in introduction and discussion.",
        ],
    },
}

DOMAINS: dict[str, dict] = {
    "cs_engineering": {
        "label": "Computer science, engineering, physics, maths",
        "shift": {"avg_sentence_words": (-1, -1), "hedges_per_1k": (-0.5, -2.5),
                  "passive_share": (0.03, 0.08), "we_our_per_1k": (0, 4), "i_me_my_per_1k": (0, -2.5)},
        "guide": [
            "'We' is normal in papers; single-author theses often use 'this thesis' or the passive instead.",
            "Hedge less than in soft fields: report numbers plainly, hedge only explanations.",
            "Units, versions and exact figures carry the argument; parentheses for definitions and units are normal.",
        ],
    },
    "natural_sciences": {
        "label": "Chemistry, biology, earth and environmental sciences",
        "shift": {"avg_sentence_words": (-1, -1), "hedges_per_1k": (0, -1), "passive_share": (0.05, 0.10),
                  "i_me_my_per_1k": (0, -3)},
        "guide": [
            "Passive voice is standard in methods; active 'we' is accepted elsewhere.",
            "Hedge interpretations of mechanisms; state observations directly.",
        ],
    },
    "life_health": {
        "label": "Medicine, health, nursing, psychology (experimental)",
        "shift": {"passive_share": (0.05, 0.10), "i_me_my_per_1k": (0, -3), "hedges_per_1k": (0, 1)},
        "guide": [
            "Structured reporting (IMRaD); passive common in methods.",
            "Cautious causal language: 'was associated with', not 'caused', unless the design supports it.",
        ],
    },
    "social_sciences": {
        "label": "Sociology, education, applied linguistics, political science",
        "shift": {"hedges_per_1k": (1, 3), "passive_share": (-0.03, -0.12), "i_me_my_per_1k": (0, 4),
                  "avg_sentence_words": (1, 1)},
        "guide": [
            "Active voice dominates; 'I' is accepted in many venues (especially qualitative work).",
            "Hedge more than in hard sciences: claims are interpretive and contestable.",
        ],
    },
    "business": {
        "label": "Business, management, marketing, economics",
        "shift": {"hedges_per_1k": (1, 3), "passive_share": (-0.02, -0.08), "we_our_per_1k": (0, 2)},
        "guide": [
            "Marketing and management papers hedge heavily; practical implications sections are expected.",
            "Avoid sales language even when discussing products or firms.",
        ],
    },
    "humanities": {
        "label": "History, philosophy, literature, arts",
        "shift": {"avg_sentence_words": (2, 4), "hedges_per_1k": (1.5, 3), "boosters_per_1k": (0.5, 2),
                  "passive_share": (-0.05, -0.20), "i_me_my_per_1k": (0, 6), "nominalizations_per_1k": (-5, -10),
                  "question_share": (0, 0.04), "avg_paragraph_words": (20, 60)},
        "guide": [
            "Longer, more varied sentences and paragraphs; argument carried in prose, not lists.",
            "First person 'I' is normal; rhetorical questions are acceptable in moderation.",
            "Quotations are analysed closely; hedging and boosting both mark the writer's position.",
        ],
    },
}

# Section adjustments for academic registers.
SECTIONS: dict[str, dict] = {
    "abstract": {"shift": {"passive_share": (0, 0.05), "hedges_per_1k": (-1, -2)},
                 "guide": ["Abstract: compact, one claim per sentence, numbers stated plainly."]},
    "introduction": {"shift": {"passive_share": (-0.05, -0.10), "hedges_per_1k": (0, 1)},
                     "guide": ["Introduction: mostly active voice; build the gap from cited work."]},
    "literature": {"shift": {"hedges_per_1k": (0, 1), "avg_sentence_words": (1, 2)},
                   "guide": ["Literature review: report sources accurately; vary reporting verbs naturally."]},
    "methods": {"shift": {"passive_share": (0.10, 0.30), "hedges_per_1k": (-1, -3), "boosters_per_1k": (-0.5, -2)},
                "guide": ["Methods: passive voice is normal and expected here; no hedging of what was done."]},
    "results": {"shift": {"hedges_per_1k": (-1, -2), "passive_share": (0, 0.05)},
                "guide": ["Results: report findings directly; save interpretation for the discussion."]},
    "discussion": {"shift": {"hedges_per_1k": (1, 3), "passive_share": (-0.05, -0.10)},
                   "guide": ["Discussion: hedge interpretations and generalisations; active voice dominates."]},
    "conclusion": {"shift": {"hedges_per_1k": (0, 1)},
                   "guide": ["Conclusion: restate contributions and limits without new claims."]},
}

# ------------------------------------------------------------ non-academic

PLATFORMS: dict[str, dict] = {
    "blog_personal": {
        "label": "Personal or travel blog",
        "ranges": {"avg_sentence_words": (10, 18), "sentence_length_cv": (0.45, 1.0), "short_sentence_share": (0.15, 0.45),
                   "avg_paragraph_words": (20, 90), "contractions_per_1k": (6, 40), "i_me_my_per_1k": (10, 60),
                   "you_your_per_1k": (0, 25), "hedges_per_1k": (1, 10), "boosters_per_1k": (1, 10),
                   "passive_share": (0, 0.15), "nominalizations_per_1k": (5, 35), "participle_clauses_per_1k": (0, 8),
                   "question_share": (0, 0.12), "exclamation_share": (0, 0.06), "em_dashes_per_1k": (0, 4),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["First person, concrete sensory and logistical detail (times, prices, names of places).",
                  "Short paragraphs; occasional one-line paragraph for a beat, not as a slogan.",
                  "Contractions and asides are natural here."],
    },
    "blog_technical": {
        "label": "Technical / developer blog, tutorial",
        "ranges": {"avg_sentence_words": (11, 20), "sentence_length_cv": (0.40, 0.95), "short_sentence_share": (0.10, 0.40),
                   "avg_paragraph_words": (20, 100), "contractions_per_1k": (3, 30), "i_me_my_per_1k": (2, 30),
                   "we_our_per_1k": (0, 20), "you_your_per_1k": (3, 35), "hedges_per_1k": (1, 8), "boosters_per_1k": (0.5, 6),
                   "passive_share": (0, 0.20), "nominalizations_per_1k": (10, 50), "participle_clauses_per_1k": (0, 8),
                   "question_share": (0, 0.08), "exclamation_share": (0, 0.02), "em_dashes_per_1k": (0, 3),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["Address the reader as 'you' in steps; say what you tried and what broke.",
                  "Exact versions, commands and numbers; no hype adjectives.",
                  "Code and commands go in code blocks, not prose."],
    },
    "blog_company": {
        "label": "Company / brand blog (written for a business)",
        "ranges": {"avg_sentence_words": (12, 21), "sentence_length_cv": (0.40, 0.90), "short_sentence_share": (0.08, 0.35),
                   "avg_paragraph_words": (25, 100), "contractions_per_1k": (2, 25), "i_me_my_per_1k": (0, 10),
                   "we_our_per_1k": (3, 30), "you_your_per_1k": (3, 30), "hedges_per_1k": (1, 8), "boosters_per_1k": (0.5, 6),
                   "passive_share": (0, 0.20), "nominalizations_per_1k": (15, 55), "participle_clauses_per_1k": (0, 7),
                   "question_share": (0, 0.08), "exclamation_share": (0, 0.02), "em_dashes_per_1k": (0, 3),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["'We' for the company, 'you' for the customer; concrete product facts over adjectives.",
                  "Brand style guides win over these ranges when they conflict."],
    },
    "academic_blog": {
        "label": "Academic / research blog (e.g. LSE Impact style) or popular-science post",
        "ranges": {"avg_sentence_words": (15, 24), "sentence_length_cv": (0.40, 0.85), "short_sentence_share": (0.05, 0.30),
                   "avg_paragraph_words": (35, 130), "contractions_per_1k": (0, 15), "i_me_my_per_1k": (1, 20),
                   "we_our_per_1k": (1, 20), "you_your_per_1k": (0, 12), "hedges_per_1k": (2, 10), "boosters_per_1k": (1, 6),
                   "passive_share": (0.03, 0.25), "nominalizations_per_1k": (20, 70), "participle_clauses_per_1k": (0, 7),
                   "question_share": (0, 0.08), "exclamation_share": (0, 0.01), "em_dashes_per_1k": (0, 3),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["A hybrid of article and journalism: the writer's own research, told more personally.",
                  "Fewer citations and hedges than the paper, more reader address and first person.",
                  "Keep every number and finding exactly as in the paper."],
    },
    "linkedin": {
        "label": "LinkedIn post",
        "ranges": {"avg_sentence_words": (8, 17), "sentence_length_cv": (0.40, 1.1), "short_sentence_share": (0.20, 0.60),
                   "avg_paragraph_words": (5, 45), "contractions_per_1k": (5, 45), "i_me_my_per_1k": (10, 70),
                   "you_your_per_1k": (0, 30), "hedges_per_1k": (0, 8), "boosters_per_1k": (0.5, 10),
                   "passive_share": (0, 0.12), "nominalizations_per_1k": (5, 40), "participle_clauses_per_1k": (0, 8),
                   "question_share": (0, 0.15), "exclamation_share": (0, 0.06), "em_dashes_per_1k": (0, 4),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["Open with the specific thing that happened, not a slogan.",
                  "Short paragraphs are normal; avoid the one-sentence-per-line staircase for a whole post.",
                  "No 'Let that sink in', no lists of three adjectives, at most one hashtag line at the end."],
    },
    "x_thread": {
        "label": "X / Twitter post or thread",
        "ranges": {"avg_sentence_words": (6, 15), "sentence_length_cv": (0.35, 1.2), "short_sentence_share": (0.30, 0.80),
                   "avg_paragraph_words": (5, 45), "contractions_per_1k": (5, 60), "i_me_my_per_1k": (5, 70),
                   "you_your_per_1k": (0, 40), "hedges_per_1k": (0, 8), "boosters_per_1k": (0, 12),
                   "passive_share": (0, 0.10), "nominalizations_per_1k": (0, 40), "participle_clauses_per_1k": (0, 8),
                   "question_share": (0, 0.20), "exclamation_share": (0, 0.10), "em_dashes_per_1k": (0, 5),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["One idea per post; drop articles and filler before dropping facts.",
                  "Lowercase, fragments and abbreviations are fine if the writer uses them."],
    },
    "newsletter": {
        "label": "Email newsletter",
        "ranges": {"avg_sentence_words": (10, 19), "sentence_length_cv": (0.40, 1.0), "short_sentence_share": (0.12, 0.45),
                   "avg_paragraph_words": (15, 80), "contractions_per_1k": (5, 40), "i_me_my_per_1k": (5, 50),
                   "you_your_per_1k": (3, 35), "hedges_per_1k": (1, 9), "boosters_per_1k": (0.5, 8),
                   "passive_share": (0, 0.15), "nominalizations_per_1k": (5, 40), "participle_clauses_per_1k": (0, 8),
                   "question_share": (0, 0.12), "exclamation_share": (0, 0.04), "em_dashes_per_1k": (0, 4),
                   "ai_words_strong_per_1k": (0, 0.3), "ai_words_soft_per_1k": (0, 2)},
        "guide": ["Written to one reader: 'you', direct, a clear single ask or takeaway."],
    },
    "forum_post": {
        "label": "Forum / Reddit / Q&A answer",
        "ranges": {"avg_sentence_words": (8, 18), "sentence_length_cv": (0.40, 1.1), "short_sentence_share": (0.15, 0.55),
                   "avg_paragraph_words": (10, 80), "contractions_per_1k": (8, 60), "i_me_my_per_1k": (8, 60),
                   "you_your_per_1k": (3, 45), "hedges_per_1k": (2, 14), "boosters_per_1k": (0.5, 10),
                   "passive_share": (0, 0.12), "nominalizations_per_1k": (0, 35), "participle_clauses_per_1k": (0, 7),
                   "question_share": (0, 0.20), "exclamation_share": (0, 0.05), "em_dashes_per_1k": (0, 3),
                   "ai_words_strong_per_1k": (0, 0.2), "ai_words_soft_per_1k": (0, 1.5)},
        "guide": ["Answer first, then how you know; casual tone, personal experience welcome.",
                  "No headings or bold labels in a short answer."],
    },
}

# Features a personal voice may pull toward (within the register's range).
TRANSFERABLE = {
    "avg_sentence_words", "sentence_length_cv", "short_sentence_share", "avg_paragraph_words",
    "hedges_per_1k", "boosters_per_1k", "passive_share", "i_me_my_per_1k", "we_our_per_1k",
    "semicolons_per_1k", "parentheses_per_1k", "colons_per_1k", "em_dashes_per_1k",
}
# Features where only the register decides (habits from other genres never transfer).
REGISTER_ONLY = {
    "contractions_per_1k", "you_your_per_1k", "question_share", "exclamation_share",
    "nominalizations_per_1k", "participle_clauses_per_1k", "ai_words_strong_per_1k", "ai_words_soft_per_1k",
}

# Being BELOW the range on these is a style choice, not an error: a writer who rarely
# hedges or boosts, or never says "we", should not be pushed to add them.
LOWER_BOUND_OPTIONAL = {
    "hedges_per_1k", "boosters_per_1k", "i_me_my_per_1k", "we_our_per_1k", "you_your_per_1k",
    "contractions_per_1k", "colons_per_1k", "parentheses_per_1k", "semicolons_per_1k",
    "question_share", "exclamation_share", "passive_share", "nominalizations_per_1k",
    "participle_clauses_per_1k",
}

ADVICE = {
    "avg_sentence_words": ("Shorten some sentences: split at 'and', 'which' or 'while'.",
                           "Combine some short sentences where the ideas belong together."),
    "sentence_length_cv": ("", "Sentence lengths are too even: mix a few short sentences with longer ones."),
    "short_sentence_share": ("Too many very short sentences; merge some.", "Add an occasional short sentence (8 words or fewer)."),
    "avg_paragraph_words": ("Split long paragraphs.", "Paragraphs are thin; merge related ones."),
    "contractions_per_1k": ("Write contractions out in full for this register.", "Use contractions where a person would ('it's', 'don't')."),
    "i_me_my_per_1k": ("Use less first person singular here.", "First person is normal in this register; use it where you made a choice."),
    "we_our_per_1k": ("Too much 'we'; switch some to the subject of the sentence.", "Use 'we' for the authors' actions where natural."),
    "you_your_per_1k": ("Remove reader address ('you') for this register.", "Address the reader as 'you' in places."),
    "hedges_per_1k": ("Too much hedging: state measured results plainly.", "Hedge interpretations ('suggests', 'may') where the evidence is indirect."),
    "boosters_per_1k": ("Cut intensifiers (clearly, significantly, very, truly).", "Commit where the evidence is strong ('shows', 'clearly')."),
    "passive_share": ("Turn some passives into active sentences with a real subject.", "Passive is normal here (e.g. methods); don't force active voice."),
    "nominalizations_per_1k": ("Too noun-heavy, an AI pattern: turn some -tion/-ment nouns back into verbs.", ""),
    "participle_clauses_per_1k": ("Too many ', doing X' clauses, an AI pattern: make them separate clauses or sentences.", ""),
    "question_share": ("Remove rhetorical questions for this register.", ""),
    "exclamation_share": ("Remove exclamation marks.", ""),
    "em_dashes_per_1k": ("Replace most dashes with commas, colons or full stops.", ""),
    "ai_words_strong_per_1k": ("Replace AI-favoured words (see ai_words_found) with plain ones.", ""),
    "ai_words_soft_per_1k": ("Too many stock transition/AI words (moreover, crucial, leverage...); use plainer words.", ""),
}


def _apply_shift(ranges: dict[str, Range], shift: dict[str, Range]) -> dict[str, Range]:
    out = dict(ranges)
    for k, (dlo, dhi) in shift.items():
        lo, hi = out.get(k, (0.0, 0.0))
        lo, hi = max(0.0, lo + dlo), max(0.0, hi + dhi)
        if k.endswith("_share"):
            lo, hi = min(lo, 1.0), min(hi, 1.0)
        out[k] = (round(min(lo, hi), 3), round(max(lo, hi), 3))
    return out


_MEASURED_DIR = Path(__file__).parent / "measured"


def _load_dir(d: Path) -> dict[str, dict]:
    out = {}
    if d.exists():
        for p in d.glob("*.json"):
            try:
                reg = json.loads(p.read_text(encoding="utf-8"))
                reg["ranges"] = {k: tuple(v) for k, v in reg["ranges"].items()}
                out[reg["name"]] = reg
            except (OSError, KeyError, json.JSONDecodeError):
                continue
    return out


def _measured_registers() -> dict[str, dict]:
    """Registers measured from real pre-AI texts and shipped with the package
    (statistics only, no text). They replace the estimated presets of the same name."""
    return _load_dir(_MEASURED_DIR)


def _user_registers() -> dict[str, dict]:
    out = {}
    d = config.home_dir() / "registers"
    if d.exists():
        for p in d.glob("*.json"):
            try:
                reg = json.loads(p.read_text(encoding="utf-8"))
                reg["ranges"] = {k: tuple(v) for k, v in reg["ranges"].items()}
                out[reg["name"]] = reg
            except (OSError, KeyError, json.JSONDecodeError):
                continue
    return out


def resolve(register: str | None = None, level: str | None = None, domain: str | None = None,
            section: str | None = None, builtin: bool = False) -> dict:
    """Return a register dict: name, label, kind, ranges, guide.

    register: a platform name ("blog_personal"), a user register name, or
              "academic:<level>:<domain>" (e.g. "academic:undergraduate:cs_engineering").
    level/domain: alternative way to ask for an academic register.
    section: optional academic section ("methods", "discussion", ...).
    builtin: ignore custom registers (used when building one from a preset).
    """
    user = {} if builtin else _user_registers()
    measured = {} if builtin else _measured_registers()
    if register and register.startswith("academic") and not register.count(":") == 2 and (level or domain):
        register = None  # rebuilt below from level/domain
    if not register and (level or domain) and not builtin:
        register = f"academic:{level or 'published'}:{domain or 'cs_engineering'}"
    base = register.split("@")[0] if register else None
    if base and base in user:
        reg = copy.deepcopy(user[base])
        reg.setdefault("kind", "custom")
    elif base and base in measured:
        reg = copy.deepcopy(measured[base])
        n = reg.get("n_texts") or reg.get("texts")
        try:
            preset = resolve(base, builtin=True)
            reg["label"] = preset["label"]
            reg.setdefault("guide", preset["guide"])
        except ValueError:
            pass
        reg["label"] = f"{reg.get('label', base)} (measured from {n} real texts)"
    elif register and register in PLATFORMS:
        p = PLATFORMS[register]
        reg = {"name": register, "label": p["label"], "kind": "platform",
               "ranges": dict(p["ranges"]), "guide": list(p["guide"])}
    else:
        if register and register.startswith("academic"):
            parts = register.split(":")
            level = level or (parts[1] if len(parts) > 1 else None)
            domain = domain or (parts[2] if len(parts) > 2 else None)
        elif register and not (level or domain):
            raise ValueError(f"Unknown register '{register}'. Call list_registers to see options.")
        level = level or "published"
        domain = domain or "cs_engineering"
        if level not in LEVELS:
            raise ValueError(f"Unknown level '{level}'. Options: {', '.join(LEVELS)}")
        if domain not in DOMAINS:
            raise ValueError(f"Unknown domain '{domain}'. Options: {', '.join(DOMAINS)}")
        ranges = _apply_shift(_ACADEMIC_BASE, LEVELS[level]["shift"])
        ranges = _apply_shift(ranges, DOMAINS[domain]["shift"])
        reg = {"name": f"academic:{level}:{domain}", "kind": "academic",
               "label": f"{LEVELS[level]['label']} - {DOMAINS[domain]['label']}",
               "ranges": ranges, "guide": LEVELS[level]["guide"] + DOMAINS[domain]["guide"]}
    if section:
        if section not in SECTIONS:
            raise ValueError(f"Unknown section '{section}'. Options: {', '.join(SECTIONS)}")
        if reg["name"].startswith("academic:"):
            reg["ranges"] = _apply_shift(reg["ranges"], SECTIONS[section]["shift"])
            reg["guide"] = reg["guide"] + SECTIONS[section]["guide"]
            reg["name"] += f"@{section}"
    return reg


def list_all() -> dict:
    return {
        "academic": {
            "how": "Use register='academic:<level>:<domain>', optionally with section.",
            "levels": {k: v["label"] for k, v in LEVELS.items()},
            "domains": {k: v["label"] for k, v in DOMAINS.items()},
            "sections": list(SECTIONS),
        },
        "platforms": {k: v["label"] for k, v in PLATFORMS.items()},
        "measured": {k: f"{v.get('n_texts') or v.get('texts')} real texts"
                     for k, v in sorted(_measured_registers().items())},
        "custom": {k: v.get("label", k) for k, v in _user_registers().items()},
    }
