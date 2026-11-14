"""Build a custom register from a folder of real texts.

Use this to add a field or platform the presets don't cover, or to replace a
preset with numbers from real writing you trust (open-access papers in your
field, theses from your department, top posts on a blog you admire).

    python scripts/build_register.py NAME FOLDER --label "Readable label" [--like academic:phd:humanities]

* Every .txt/.md/.docx file in FOLDER is measured with the same features the
  tool uses everywhere else.
* Each range is the 10th-90th percentile across the files (the full min-max when
  there are fewer than 20 files), widened by 10% so a normal text is not flagged
  for being slightly unusual.
* --like copies the guide text from an existing register.
* The result goes to HUMANIZER_HOME/registers/NAME.json and appears in
  list_registers; a custom register with a preset's name replaces the preset.

Use 8+ texts of 500+ words each. Only use texts written by people, ideally
from before late 2022 or from authors you know did not use AI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanizer_mcp import config, registers  # noqa: E402
from humanizer_mcp.features import text_stats  # noqa: E402
from humanizer_mcp.text_utils import read_document  # noqa: E402

FEATURES = sorted(set(registers._ACADEMIC_BASE) | registers.TRANSFERABLE | registers.REGISTER_ONLY)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("folder")
    ap.add_argument("--label", default=None)
    ap.add_argument("--like", default=None, help="copy the guide from this register")
    args = ap.parse_args()

    files = [p for p in sorted(Path(args.folder).glob("*")) if p.suffix.lower() in {".txt", ".md", ".docx"}]
    if len(files) < 3:
        sys.exit(f"Need at least 3 texts in {args.folder} (8+ recommended).")
    rows = []
    for p in files:
        st = text_stats(read_document(p))
        if st["words"] < 200:
            print(f"  skip {p.name}: only {st['words']} words", file=sys.stderr)
            continue
        rows.append(st)
        print(f"  {p.name}: {st['words']} words, {st['avg_sentence_words']} words/sentence", file=sys.stderr)

    # A text far shorter than the others is almost always a failed PDF extraction
    # (e.g. 1,600 words from a 180-page thesis): leave it out.
    if len(rows) >= 5:
        median = float(np.median([r["words"] for r in rows]))
        kept = [r for r in rows if r["words"] >= 0.15 * median]
        if len(kept) < len(rows):
            print(f"  skipped {len(rows) - len(kept)} text(s) under 15% of the median length "
                  f"({int(median)} words): probably a failed extraction", file=sys.stderr)
        rows = kept

    ranges = {}
    for f in FEATURES:
        vals = np.asarray([r[f] for r in rows if f in r], dtype=float)
        if len(vals) == 0:
            continue
        # With few texts the 10th-90th percentile cuts off normal writers, so use the full span.
        if len(vals) < 20:
            lo, hi = float(vals.min()), float(vals.max())
        else:
            lo, hi = np.percentile(vals, 10), np.percentile(vals, 90)
        pad = 0.10 * max(hi - lo, abs(hi) * 0.1, 0.05)
        lo, hi = max(0.0, lo - pad), hi + pad
        if f.endswith("_share"):
            hi = min(hi, 1.0)
        ranges[f] = [round(float(lo), 3), round(float(hi), 3)]
    # AI patterns keep the preset ceilings unless real texts are even lower.
    for f in ("ai_words_strong_per_1k", "ai_words_soft_per_1k"):
        ranges[f] = [0.0, min(ranges.get(f, [0, 99])[1], registers._ACADEMIC_BASE[f][1])]

    # Paragraph length is unreliable from PDFs (columns merge or split paragraphs), and the
    # AI-pattern ceilings must not flag human outliers, so these keep the wider of the
    # measured range and the research-based preset.
    base = registers.resolve(args.like, builtin=True)["ranges"] if args.like else registers._ACADEMIC_BASE
    for f in ("avg_paragraph_words", "nominalizations_per_1k", "participle_clauses_per_1k"):
        if f in ranges and f in base:
            ranges[f] = [round(min(ranges[f][0], base[f][0]), 3), round(max(ranges[f][1], base[f][1]), 3)]

    guide = []
    if args.like:
        guide = registers.resolve(args.like, builtin=True)["guide"]
    reg = {"name": args.name, "label": args.label or args.name, "kind": "custom",
           "ranges": ranges, "guide": guide, "built_from": [p.name for p in files], "texts": len(rows)}
    safe = args.name.replace(":", "__").replace("@", "_at_")  # Windows forbids ':' in file names
    out = config.home_dir() / "registers" / f"{safe}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reg, indent=2), encoding="utf-8")
    print(f"Saved {out} from {len(rows)} texts.")


if __name__ == "__main__":
    main()
