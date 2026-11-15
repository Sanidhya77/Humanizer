"""Say plainly what the AI did to a text, in the form publishers ask for.

Most journals and many universities now separate two things:
  * assistive use: an AI tool corrected spelling, grammar and punctuation in text
    the author wrote. Several large publishers do not require a statement for this.
  * generative use: the tool reworded, restructured or wrote text. This is
    normally disclosed, with the tool named and its task described.

measure_change already measures where an edit falls between those two. This
module turns the measurement into a plain description and a draft statement with
the four parts most policies ask for: which tool, for what task, to what extent,
and who checked the result.

It describes; it does not decide. Policies differ between venues and change
often, and the measurement only compares the two texts it was given.
"""

from __future__ import annotations

from .change import BUDGETS, HEAVY_PCT, measure_change

LEVELS = {
    "none": "No change",
    "copy_editing": "Language correction (spelling, grammar, punctuation)",
    "language_revision": "Language revision (some wording changed for clarity)",
    "substantial_rewriting": "Substantial rewriting by the tool",
    "generated_text": "Contains text written by the tool",
}


def ai_use_statement(original: str, rewrite: str, tool_name: str = "Claude (Anthropic)",
                     author: str = "the author") -> dict:
    """Describe the AI's part in `rewrite`, measured against the writer's `original`."""
    m = measure_change(original, rewrite, mode="light")
    s = m["sentences"]
    changed, writer = m["changed_pct"], m["writer_words_pct"]
    added_paragraphs = sum(1 for p in m["paragraphs_over_budget"] if p["status"] == "added")
    written_by_tool = s["new"] + s["rebuilt"]

    if changed == 0 and m["corrections"] == 0:
        level = "none"
    elif s["new"] or added_paragraphs or writer < 50:
        level = "generated_text"
    elif s["rebuilt"] or changed >= HEAVY_PCT:
        level = "substantial_rewriting"
    elif changed > BUDGETS["light"]:
        level = "language_revision"
    else:
        level = "copy_editing"

    who = author[0].upper() + author[1:]
    check = (f"{who} reviewed and edited the result and takes full responsibility for the content of this work.")
    if level == "none":
        statement = "No AI tool changed the text of this work."
    elif level == "copy_editing":
        statement = (
            f"During the preparation of this work, {author} used {tool_name} to correct spelling, grammar and "
            f"punctuation in text {author} had written. The tool did not write or restructure any sentence. {check}")
    elif level == "language_revision":
        statement = (
            f"During the preparation of this work, {author} used {tool_name} to correct language errors and to "
            f"improve the clarity of text {author} had written. About {round(changed)}% of the wording was changed "
            f"and no sentence was written by the tool. {check}")
    elif level == "substantial_rewriting":
        statement = (
            f"During the preparation of this work, {author} used {tool_name} to revise text {author} had written. "
            f"The tool rewrote {written_by_tool} of {s['total']} sentences and changed about {round(changed)}% of "
            f"the wording. The ideas, data and conclusions are {author}'s own. {check}")
    else:
        statement = (
            f"During the preparation of this work, {author} used {tool_name} to draft and revise parts of the text. "
            f"About {round(100 - writer)}% of the final wording was produced by the tool, including "
            f"{written_by_tool} of {s['total']} sentences. The ideas, data and conclusions are {author}'s own. {check}")

    usually = {
        "none": "Nothing to disclose.",
        "copy_editing": "Several large publishers do not require a statement for grammar and spelling correction. "
                        "Some venues ask for one anyway. Giving it never hurts.",
        "language_revision": "Usually disclosed. Many venues accept AI-assisted language editing when it is declared.",
        "substantial_rewriting": "Disclose. Some venues limit AI use to language editing; check before submitting.",
        "generated_text": "Disclose. Some venues do not accept AI-generated text at all; check before submitting.",
    }[level]

    return {
        "level": level,
        "level_label": LEVELS[level],
        "statement": statement,
        "usually": usually,
        "measured": {
            "changed_pct": changed,
            "writer_words_pct": writer,
            "corrections": m["corrections"],
            "sentences": s,
            "paragraphs_added": added_paragraphs,
        },
        "limits": (
            "This describes the difference between the two texts you gave. If the original was itself drafted "
            "with AI, say so: the statement must describe the whole process, not only this edit. Rules differ "
            "between journals, universities and clients and change often, so read the venue's own policy. "
            "Replace the tool name and version with the ones actually used."),
    }
