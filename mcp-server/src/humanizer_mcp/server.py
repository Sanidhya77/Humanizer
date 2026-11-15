"""Humanizer MCP server.

Runs locally over stdio. Claude (desktop app, Claude Code, or any MCP client)
does the rewriting; these tools measure, check and save.

Typical loop the skill asks Claude to follow (see references/local-tools.md):
  1. read_document (or read_docx_paragraphs) / get_voice_profile
  2. edit: fix errors and AI patterns inside the writer's own sentences
  3. measure_change -> go back to the original wording wherever the edit is over budget
  4. check_voice    -> fix only what is outside the register
  5. check_meaning  -> restore anything dropped, remove anything invented
  6. check_quality  -> fix anything the edit made worse
  7. save_output (or rewrite_docx to keep a .docx's formatting)
For AI-written drafts, find_generic picks the paragraphs to ask the writer about.
"""

from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from . import config
from .change import measure_change as _measure_change
from .detector import get_detector
from .disclosure import ai_use_statement as _ai_use_statement
from .docx_edit import docx_paragraphs as _docx_paragraphs, rewrite_docx as _rewrite_docx
from .meaning import check_meaning as _check_meaning
from .output import save_output as _save_output
from .quality import check_quality as _check_quality
from .specificity import find_generic as _find_generic
from .text_utils import read_document as _read_document
from . import registers as _registers
from .voice import build_profile, check_voice as _check_voice, compare_to_voice as _compare, list_profiles, load_profile, save_profile

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[humanizer] %(message)s")
log = logging.getLogger("humanizer")
for noisy in ("httpx", "httpcore", "huggingface_hub", "urllib3", "filelock"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

mcp = FastMCP(
    "humanizer",
    instructions=(
        "Tools for the Humanizer skill. Claude edits the text; these tools measure how much was changed "
        "(measure_change), check it against the register and the writer's voice (check_voice), check that "
        "facts and citations survived (check_meaning), and save the result. Edit lightly: fix errors and AI "
        "patterns inside the writer's own sentences, and stay inside the edit budget. Follow the Humanizer "
        "SKILL.md loop."
    ),
)


def _text_or_path(text: str | None, path: str | None) -> str:
    if text and text.strip():
        return text
    if path:
        return _read_document(path)
    raise ValueError("Give either text or a path to a .txt, .md or .docx file.")


@mcp.tool()
def score_text(text: str | None = None, path: str | None = None, model: str | None = None) -> dict:
    """Optional local estimate of how model-like a text reads (runs on this computer's CPU).

    Returns ai_likelihood (0-100), burstiness numbers and flagged_sentences. Use it to find passages
    worth a second look, on 100+ words at a time. It does NOT predict GPTZero, Turnitin or any other
    commercial detector, and a lower score is never a reason to reword a sentence that has no other
    problem: heavy rewording is what makes a writer's own text read as AI (see measure_change).
    First call downloads the detector model (~500 MB) once.
    model: optional "fast" (default, GPT-2) or "accurate" (Qwen2.5-0.5B, slower).
    """
    body = _text_or_path(text, path)
    det = get_detector(model)
    log.info("scoring %d chars with %s", len(body), det.model_name)
    return det.analyze(body)


@mcp.tool()
def measure_change(
    original: str | None = None,
    rewrite: str | None = None,
    original_path: str | None = None,
    rewrite_path: str | None = None,
    mode: str = "normal",
    budget_pct: float | None = None,
    detail: bool = False,
) -> dict:
    """Measure how much of the writer's own wording a rewrite changed, paragraph by paragraph.
    Run it after every editing round, before check_voice and check_meaning.

    Spelling and typing fixes are counted as corrections and do not use up the budget. Everything
    else is rewording. Returns changed_pct (share of characters reworded), writer_words_pct (share
    of the final words that are still the writer's own), sentence counts (kept / edited / rebuilt /
    new), and paragraphs_over_budget with the sentences that were rebuilt.
    Also returns word_swaps (one word replaced by another: undo each one that fixes nothing) and
    style_drift (notes where the edit moved the text toward model habits: overused words, added
    dashes, written-out contractions, removed "I", more abstract nouns, longer words).

    mode: "light" (budget 12% per paragraph: fix errors only) or "normal" (20%: also remove AI
      patterns and fix clarity). budget_pct overrides the number; only raise it if the user asks.
    detail=True also lists every paragraph.

    ok=false means: go back to the original wording in the listed paragraphs and keep only the
    fixes that are needed. Do not rebuild sentences; show the writer a suggestion instead.
    Give the texts directly, or as paths to .txt, .md or .docx files (better for long documents)."""
    return _measure_change(_text_or_path(original, original_path), _text_or_path(rewrite, rewrite_path),
                           mode=mode, budget_pct=budget_pct, detail=detail)


@mcp.tool()
def check_meaning(
    original: str | None = None,
    rewrite: str | None = None,
    original_path: str | None = None,
    rewrite_path: str | None = None,
    also_allowed: str | None = None,
) -> dict:
    """Compare a rewrite with its original and list any number, citation, link, quote or name
    that was dropped, changed, or newly invented. ok=true means no hard issues.
    Always run this before saving a rewrite.

    Give the texts directly, or as paths to .txt, .md or .docx files (better for long documents).
    also_allowed: text the writer added themselves in this session (for example their answers to
    your questions). Numbers and citations from it are not reported as invented."""
    return _check_meaning(_text_or_path(original, original_path), _text_or_path(rewrite, rewrite_path),
                          also_allowed=also_allowed)


@mcp.tool()
def check_quality(
    original: str | None = None,
    rewrite: str | None = None,
    original_path: str | None = None,
    rewrite_path: str | None = None,
) -> dict:
    """List what an edit made worse than the original. Run it before saving.

    hard_issues (ok=false): hidden characters, look-alike letters from another alphabet, doubled
    words, unbalanced brackets or quotes, a paragraph that stops without an end mark.
    worth_a_look: new one-word fragments, the same opener three times in a row, a phrase repeated
    more than in the original, a large change in length, sentence length or word length.
    Only what is new in the rewrite is reported. Give the texts directly or as file paths."""
    return _check_quality(_text_or_path(original, original_path), _text_or_path(rewrite, rewrite_path))


@mcp.tool()
def ai_use_statement(
    original: str | None = None,
    rewrite: str | None = None,
    original_path: str | None = None,
    rewrite_path: str | None = None,
    tool_name: str = "Claude (Anthropic)",
    author: str = "the author",
) -> dict:
    """Describe honestly what the AI did to a text, and draft the disclosure statement that journals,
    universities and clients ask for.

    Measures the edit against the writer's original and returns a level: copy_editing (spelling,
    grammar, punctuation only), language_revision (some wording changed), substantial_rewriting
    (sentences rebuilt) or generated_text (sentences the tool wrote). Returns a draft statement naming
    the tool, the task, the extent and who checked the result, and a note on what venues usually expect.

    Offer it when the text is for a university, a journal or a client, or when the user asks what
    they need to declare. It describes only the edit between the two texts given: if the original was
    itself drafted with AI, tell the user the statement must say so. Never use it to claim a text is
    human-written."""
    return _ai_use_statement(_text_or_path(original, original_path), _text_or_path(rewrite, rewrite_path),
                             tool_name=tool_name, author=author)


@mcp.tool()
def find_generic(text: str | None = None, path: str | None = None, max_questions: int | None = None) -> dict:
    """For an AI-written draft: rank its paragraphs from least to most specific, so you know where
    to ask the writer a question.

    A paragraph scores by its details per 100 words (numbers, names, citations, first-hand phrases,
    stated opinions, examples, quotes) minus filler phrases. ask_about lists the emptiest ones, at
    most questions_allowed (one per 300 words, between 3 and 8). Ask ONE specific question about each,
    all in one message, and put the writer's answer into the paragraph almost word for word.
    A low score does not mean a model wrote the paragraph; do not report it that way."""
    return _find_generic(_text_or_path(text, path), max_questions=max_questions)


@mcp.tool()
def create_voice_profile(
    name: str,
    sample_texts: list[str] | None = None,
    sample_paths: list[str] | None = None,
    description: str = "",
    genre: str = "blog",
    register: str | None = None,
    private: bool = False,
) -> dict:
    """Learn a writer's voice from samples of their OWN writing (not AI drafts) and save it.

    Give sample_texts (pasted posts) and/or sample_paths (.txt/.md/.docx files). 1,500+ words
    across several pieces works best. Use one profile per genre (e.g. "shivam-academic",
    "shivam-blog"): a blog voice should not be learned from a thesis.
    register: the register the samples are written in, e.g. "academic:undergraduate:cs_engineering"
    or "blog_personal" (see list_registers). Returns stats, a style guide and excerpts to imitate.
    private=True: store only numbers and the style guide, no text from the samples (use for client or
    company writing the user may not share). Prefer sample_paths then, so the files are read locally."""
    texts = list(sample_texts or [])
    for p in sample_paths or []:
        texts.append(_read_document(p))
    profile = build_profile(name, texts, description=description, genre=genre, register=register, private=private)
    path = save_profile(profile)
    return {"saved_to": str(path), **profile}


@mcp.tool()
def get_voice_profile(name: str) -> dict:
    """Load a saved voice profile: style guide, favourite words, and real excerpts to imitate."""
    return load_profile(name)


@mcp.tool()
def list_voice_profiles() -> list[dict]:
    """List saved voice profiles."""
    return list_profiles()


@mcp.tool()
def list_registers() -> dict:
    """List the writing registers: academic levels x domains (+ sections), blog and social platforms,
    and any custom registers built from the user's own corpora."""
    return _registers.list_all()


@mcp.tool()
def get_register(register: str, section: str | None = None) -> dict:
    """Show a register's acceptable ranges and its plain-English guide.
    register: e.g. "academic:phd:social_sciences", "linkedin", "blog_technical"."""
    return _registers.resolve(register, section=section)


@mcp.tool()
def check_voice(
    text: str | None = None,
    register: str | None = None,
    profile_name: str | None = None,
    strength: str | None = None,
    section: str | None = None,
    path: str | None = None,
) -> dict:
    """Check a draft against a register (what is normal for this kind of writing) and, optionally,
    the writer's voice profile.

    register: e.g. "academic:undergraduate:cs_engineering", "blog_personal". Defaults to the
      profile's own register.
    strength: off | light | medium | strong. Default: light for academic, medium for blogs.
      light = only fix what is outside the register; medium/strong = also nudge toward the writer.
    section: for academic text: abstract, introduction, literature, methods, results, discussion, conclusion.

    Returns must_fix (over the register's limits), ai_patterns, optional (below typical; a style
    choice, change only if the text reads stiff), voice_nudges (already limited to the register) and
    not_applied (writer habits deliberately NOT used in this register).
    The ranges are limits, not targets: leave a text alone when it is inside them.
    Give the text directly or as a path to a .txt, .md or .docx file."""
    profile = load_profile(profile_name) if profile_name else None
    return _check_voice(_text_or_path(text, path), register=register, profile=profile, strength=strength,
                        section=section)


@mcp.tool()
def compare_to_voice(text: str | None = None, profile_name: str = "", path: str | None = None) -> dict:
    """Shortcut for check_voice with the profile's own register at medium strength.
    Run it on the original and on the edit: the edit should not move away from the writer's voice."""
    if not profile_name:
        raise ValueError("Give profile_name (see list_voice_profiles).")
    return _compare(_text_or_path(text, path), load_profile(profile_name))


@mcp.tool()
def read_document(path: str) -> str:
    """Read a .txt, .md or .docx file from this computer and return its text."""
    return _read_document(path)


@mcp.tool()
def read_docx_paragraphs(path: str) -> dict:
    """List the paragraphs of a .docx with their index, style and whether they can be edited.
    Use the indexes with rewrite_docx. Headings, captions and paragraphs that hold a link, field,
    footnote mark, picture or equation are marked editable=false: leave those alone."""
    return _docx_paragraphs(path)


@mcp.tool()
def rewrite_docx(path: str, replacements: dict[str, str], output_path: str | None = None) -> dict:
    """Save a copy of a .docx in which only the given paragraphs have new text. Styles, headings,
    the table of contents, tables and page layout stay as they were. The original is never changed.

    replacements: {"paragraph index": "new text"}, indexes from read_docx_paragraphs. Send only the
      paragraphs you actually edited.
    output_path: optional; default is "<name>_humanized.docx" next to the original.
    Returns the paragraphs written, the ones skipped (with the reason) and check_formatting: paragraphs
    that had words in italics or bold, which the user must re-apply by hand."""
    return _rewrite_docx(path, replacements, output_path=output_path)


@mcp.tool()
def save_output(
    text: str,
    title: str,
    original: str | None = None,
    report: dict | None = None,
    format: str = "md",
) -> dict:
    """Save the final rewrite into the Humanizer output folder (one subfolder per job).
    Include the original and a report (measure_change, register fit before/after, meaning check).
    When the original is given, the folder also gets changes.html: a change record with every edit
    marked (removed words struck through, added words underlined). Tell the user it is there.
    format: "md" (default) or "docx". "docx" builds a new plain document; to keep the formatting of
    an existing .docx, use rewrite_docx instead."""
    return _save_output(text, title, original=original, report=report, fmt=format)


@mcp.tool()
def humanizer_status() -> dict:
    """Show where files are saved, which detector model is configured, and whether it is calibrated."""
    return {
        "home": str(config.home_dir()),
        "output_dir": str(config.output_dir()),
        "profiles_dir": str(config.profiles_dir()),
        "detector_model": config.detector_model(),
        "calibration_file": str(config.calibration_path()),
        "calibrated": config.calibration_path().exists(),
        "cpu_threads": config.cpu_threads(),
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--download":
        model = sys.argv[2] if len(sys.argv) > 2 else None
        det = get_detector(model)
        print(f"Downloading and loading {det.model_name} ...", file=sys.stderr)
        det.load()
        print("Ready.", file=sys.stderr)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "--score":
        import json

        det = get_detector()
        print(json.dumps(det.analyze(_read_document(sys.argv[2])), indent=2))
        return
    mcp.run()


if __name__ == "__main__":
    main()
