"""A change record the writer can keep or show: every edit, marked.

Detectors guess from the finished text. A record of what the editor actually did
to the writer's draft is better evidence of how a text was made, and it lets the
writer check the edit word by word. This module renders that record as one
self-contained HTML file: deleted words struck through, added words underlined,
with the measure_change numbers on top.

It records what was given to it. It cannot know whether the "original" was typed
by the writer, so the page says so.
"""

from __future__ import annotations

import difflib
import html
import re
from datetime import datetime

from .change import _align_paragraphs, measure_change
from .text_utils import paragraphs

_CSS = """
body{font:16px/1.6 Georgia,serif;max-width:46rem;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{font:600 1.4rem system-ui,sans-serif;margin-bottom:.2rem}
.meta{font:.85rem system-ui,sans-serif;color:#555}
table{border-collapse:collapse;font:.9rem system-ui,sans-serif;margin:1rem 0}
td,th{border:1px solid #ccc;padding:.3rem .7rem;text-align:left}
del{background:#fde2e1;color:#8a1f1a;text-decoration:line-through}
ins{background:#dff3e3;color:#145c26;text-decoration:underline}
p.new{border-left:3px solid #145c26;padding-left:.7rem}
p.gone{border-left:3px solid #8a1f1a;padding-left:.7rem}
.note{font:.85rem system-ui,sans-serif;color:#555;border-top:1px solid #ccc;margin-top:2rem;padding-top:.7rem}
"""


def _key(word: str) -> str:
    return re.sub(r"[^\w']+", "", word.lower().replace("’", "'"))


def _diff_paragraph(old: str, new: str) -> str:
    a, b = old.split(), new.split()
    sm = difflib.SequenceMatcher(None, [_key(w) for w in a], [_key(w) for w in b], autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            # show the edited spelling of the kept words (capitals and punctuation may differ)
            out.append(html.escape(" ".join(b[j1:j2])))
            continue
        if i2 > i1:
            out.append("<del>" + html.escape(" ".join(a[i1:i2])) + "</del>")
        if j2 > j1:
            out.append("<ins>" + html.escape(" ".join(b[j1:j2])) + "</ins>")
    return " ".join(out)


def render_changes_html(original: str, rewrite: str, title: str = "Change record", mode: str = "normal") -> str:
    """One HTML page showing every change between the writer's draft and the edit."""
    m = measure_change(original, rewrite, mode=mode)
    olds = [p.text for p in paragraphs(original)]
    news = [p.text for p in paragraphs(rewrite)]
    body: list[str] = []
    for oi, ni in _align_paragraphs(olds, news):
        if ni is None:
            body.append(f'<p class="gone"><del>{html.escape(olds[oi])}</del></p>')
        elif oi is None:
            body.append(f'<p class="new"><ins>{html.escape(news[ni])}</ins></p>')
        else:
            body.append(f"<p>{_diff_paragraph(olds[oi], news[ni])}</p>")
    s = m["sentences"]
    rows = [
        ("Reworded (share of characters, spelling fixes set aside)", f'{m["changed_pct"]}%'),
        ("Still the writer's own words, in their order", f'{m["writer_words_pct"]}%'),
        ("Spelling and typing fixes", str(m["corrections"])),
        ("Sentences kept / edited / rebuilt / new", f'{s["kept"]} / {s["edited"]} / {s["rebuilt"]} / {s["new"]}'),
        ("Words swapped for another word", str(m["word_swaps"]["count"])),
    ]
    table = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title><style>{_CSS}</style></head><body>"
        f"<h1>{html.escape(title)}</h1>"
        f'<div class="meta">Change record, generated {stamp}. '
        "<del>Struck through</del> = removed from the draft. <ins>Underlined</ins> = added by the edit.</div>"
        f"<table>{table}</table>"
        + "\n".join(body)
        + '<div class="note">This page compares two texts: the draft that was supplied as the original, and the '
          "edited version. It shows what the edit changed. It does not show how the draft itself was written."
          "</div></body></html>\n"
    )
