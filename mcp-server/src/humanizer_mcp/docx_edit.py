"""Edit the prose of a .docx in place, paragraph by paragraph.

save_output(format="docx") builds a new plain document, so headings styles, the
table of contents, tables and page layout are lost. For a real document it is
better to open the original, replace the text of the edited paragraphs only, and
save a copy. Everything that was not touched stays exactly as it was.

The original file is never overwritten.
"""

from __future__ import annotations

import re
from pathlib import Path

# Paragraphs that hold one of these cannot be edited safely by replacing text:
# the link, field (TOC, page number, cross-reference), note mark, picture or
# equation would be lost or orphaned.
_LOCKED = ("hyperlink", "fldChar", "fldSimple", "instrText", "drawing", "pict", "object",
           "footnoteReference", "endnoteReference", "commentReference", "oMath", "oMathPara", "sdt")
_LOCKED_XPATH = ".//*[" + " or ".join(f"local-name()='{n}'" for n in _LOCKED) + "]"
_NOT_PROSE_STYLES = ("heading", "title", "subtitle", "toc", "caption", "table", "bibliography", "reference")
# A heading with one of these names starts the reference list. Nothing after it is prose.
_REFERENCES_RE = re.compile(r"^\W*(?:\d+[.)]?\s*)?(?:bibliography|references?|reference list|works cited|"
                            r"literature cited|list of references|sources)\W*$", re.IGNORECASE)
# A short line with no end mark (a name on the title page, "TABLE OF CONTENTS") is a label, not prose.
_LABEL_MAX_WORDS = 8


def _open(path: str | Path):
    try:
        import docx  # python-docx
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Editing .docx needs python-docx: pip install python-docx") from e
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"No file at {p}")
    if p.suffix.lower() != ".docx":
        raise ValueError("This tool only edits .docx files.")
    return docx.Document(str(p)), p


def _is_heading(par) -> bool:
    style = (par.style.name if par.style is not None else "").lower()
    return any(style.startswith(s) or s in style for s in _NOT_PROSE_STYLES)


def _references_start(pars) -> int | None:
    """Index of the heading that opens the reference list, if there is one."""
    for i, par in enumerate(pars):
        if _is_heading(par) and "toc" not in (par.style.name or "").lower() and _REFERENCES_RE.match(par.text.strip()):
            return i
    return None


def _kind(par, in_references: bool = False) -> str:
    text = par.text.strip()
    if not text:
        return "empty"
    if _is_heading(par):
        return "heading"
    if in_references:
        return "reference"
    if len(text.split()) < _LABEL_MAX_WORDS and not text.endswith((".", "!", "?", ":", ";")):
        return "label"
    style = (par.style.name if par.style is not None else "").lower()
    if "list" in style or par._p.xpath(".//*[local-name()='numPr']"):
        return "list"
    return "body"


def _locked_by(par) -> list[str]:
    return sorted({el.tag.rsplit("}", 1)[-1] for el in par._p.xpath(_LOCKED_XPATH)})


def _run_format(run) -> tuple:
    f = run.font
    return (bool(run.bold), bool(run.italic), bool(run.underline), bool(f.superscript), bool(f.subscript),
            f.name, f.size, run.style.name if run.style is not None else None)


def _formatted_fragments(par) -> list[str]:
    """Text of runs whose character format differs from the paragraph's first run."""
    runs = [r for r in par.runs if r.text]
    if len(runs) < 2:
        return []
    base = _run_format(runs[0])
    return [r.text.strip() for r in runs[1:] if _run_format(r) != base and r.text.strip()]


def docx_paragraphs(path: str | Path) -> dict:
    """List the paragraphs of a .docx with the index that rewrite_docx expects."""
    doc, p = _open(path)
    rows = []
    pars = doc.paragraphs
    refs = _references_start(pars)
    for i, par in enumerate(pars):
        kind = _kind(par, in_references=refs is not None and i > refs)
        if kind == "empty":
            continue
        locked = _locked_by(par)
        rows.append({
            "index": i,
            "kind": kind,
            "style": par.style.name if par.style is not None else "",
            "words": len(par.text.split()),
            "editable": kind in ("body", "list") and not locked,
            **({"locked_by": locked} if locked else {}),
            "text": par.text,
        })
    return {
        "file": str(p),
        "paragraphs": rows,
        "editable": sum(r["editable"] for r in rows),
        "note": ("Rewrite only paragraphs with editable=true. Headings, captions, short labels (title page "
                 "lines) and the reference list are locked. Text inside tables, text boxes, headers and footers "
                 "is not listed and is left untouched."),
    }


def rewrite_docx(path: str | Path, replacements: dict, output_path: str | Path | None = None) -> dict:
    """Write a copy of the .docx in which the given paragraphs have new text.

    replacements: {paragraph index: new text}, indexes from docx_paragraphs.
    """
    doc, src = _open(path)
    if not replacements:
        raise ValueError("Give at least one replacement: {paragraph index: new text}.")
    pars = doc.paragraphs
    refs = _references_start(pars)
    written, skipped, check_formatting = [], [], []
    for key, new_text in replacements.items():
        try:
            i = int(key)
        except (TypeError, ValueError):
            skipped.append({"index": key, "why": "Index is not a number."})
            continue
        if not 0 <= i < len(pars):
            skipped.append({"index": i, "why": f"No paragraph {i}; the document has {len(pars)}."})
            continue
        par = pars[i]
        new_text = (new_text or "").strip()
        if not new_text:
            skipped.append({"index": i, "why": "Empty replacement. This tool does not delete paragraphs."})
            continue
        if "\n" in new_text:
            skipped.append({"index": i, "why": "Replacement holds a line break. One paragraph in, one paragraph out."})
            continue
        kind = _kind(par, in_references=refs is not None and i > refs)
        if kind not in ("body", "list"):
            skipped.append({"index": i, "why": f"Not prose ({kind}, style '{par.style.name}')."})
            continue
        locked = _locked_by(par)
        if locked:
            skipped.append({"index": i, "why": "Holds " + ", ".join(locked) + ". Edit this paragraph by hand."})
            continue
        if new_text == par.text.strip():
            continue
        lost = _formatted_fragments(par)
        runs = par.runs
        if runs:
            runs[0].text = new_text
            for r in runs[1:]:
                r._r.getparent().remove(r._r)
        else:
            par.add_run(new_text)
        written.append(i)
        if lost:
            check_formatting.append({"index": i, "was_formatted": lost[:12]})

    if output_path:
        out = Path(output_path).expanduser()
        if out.suffix.lower() != ".docx":
            out = out.with_suffix(".docx")
    else:
        out = src.with_name(f"{src.stem}_humanized.docx")
        n = 2
        while out.exists():
            out = src.with_name(f"{src.stem}_humanized-{n}.docx")
            n += 1
    if out.resolve() == src.resolve():
        raise ValueError("output_path is the original file. The original is never overwritten.")
    if written:
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
    return {
        "saved_to": str(out) if written else None,
        "paragraphs_rewritten": written,
        "skipped": skipped,
        "check_formatting": check_formatting,
        "note": ("Paragraphs in check_formatting had words in italics, bold or another font. The new text uses "
                 "the paragraph's main format, so re-apply those by hand." if check_formatting else
                 "Styles, headings, tables and layout are unchanged."),
    }
