"""Screen a corpus folder for AI-written texts before building a register from it.

Use this for sources whose dates you cannot verify (for example the IB Extended
Essay examples, published 2025 but written under a 2018-2026 guide). Every text is
scored with the local detector; texts that look AI-written are moved to
corpus/_excluded/ai_suspect/ so they never shape a register.

    uv run python scripts/screen_corpus.py "<HUMANIZER_HOME>\\corpus\\academic__high_school__humanities"

A text is moved if its AI likelihood is at or above --threshold (default 60), or if
it uses strong AI-favoured words (delve, showcase, tapestry ...) at more than
--max-ai-words per 1,000 words (default 0.6). Human texts in our corpora scored
about 10-15; a typical ChatGPT paragraph scored 83.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanizer_mcp.detector import get_detector  # noqa: E402
from humanizer_mcp.features import text_stats  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--threshold", type=float, default=60.0)
    ap.add_argument("--max-ai-words", type=float, default=0.6)
    ap.add_argument("--dry-run", action="store_true", help="report only, move nothing")
    args = ap.parse_args()

    folder = Path(args.folder)
    files = sorted(p for p in folder.glob("*.txt"))
    if not files:
        sys.exit(f"No .txt files in {folder}")
    out = folder.parent / "_excluded" / "ai_suspect"
    det = get_detector()
    moved = 0
    print(f"{'AI %':>6} {'AIwords':>8}  file")
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        # Long texts: score a few evenly spaced chunks to keep it fast on a CPU.
        words = text.split()
        if len(words) > 6000:
            step = len(words) // 3
            chunks = [" ".join(words[i:i + 2000]) for i in (0, step, 2 * step)]
            score = max(det.analyze(c)["ai_likelihood"] for c in chunks)
        else:
            score = det.analyze(text)["ai_likelihood"]
        ai_words = text_stats(text)["ai_words_strong_per_1k"]
        flag = score >= args.threshold or ai_words > args.max_ai_words
        print(f"{score:6.1f} {ai_words:8.2f}  {p.name}{'   <- AI suspect' if flag else ''}")
        if flag and not args.dry_run:
            out.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(out / p.name))
            moved += 1
    print(f"\n{moved} of {len(files)} moved to {out}" if not args.dry_run else "\n(dry run: nothing moved)")


if __name__ == "__main__":
    main()
