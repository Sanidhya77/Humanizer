"""Save finished rewrites to the output folder."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from . import config


def _slug(title: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", title.lower()).strip("-")
    return (s or "untitled")[:60]


def save_output(text: str, title: str, original: str | None = None, report: dict | None = None,
                fmt: str = "md") -> dict:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    folder = config.output_dir() / f"{stamp}_{_slug(title)}"
    n = 2
    while folder.exists():
        folder = config.output_dir() / f"{stamp}_{_slug(title)}-{n}"
        n += 1
    folder.mkdir(parents=True)

    written: list[Path] = []
    if fmt == "docx":
        try:
            import docx

            d = docx.Document()
            for para in re.split(r"\n\s*\n", text.strip()):
                if para.startswith("#"):
                    level = min(len(para) - len(para.lstrip("#")), 4)
                    d.add_heading(para.lstrip("#").strip(), level=level)
                else:
                    d.add_paragraph(para.strip())
            p = folder / "final.docx"
            d.save(str(p))
            written.append(p)
        except ImportError:
            fmt = "md"
    if fmt != "docx":
        p = folder / "final.md"
        p.write_text(text.strip() + "\n", encoding="utf-8")
        written.append(p)
    if original:
        p = folder / "original.md"
        p.write_text(original.strip() + "\n", encoding="utf-8")
        written.append(p)
    if report:
        p = folder / "report.json"
        p.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        written.append(p)
    return {"folder": str(folder), "files": [str(p) for p in written]}
