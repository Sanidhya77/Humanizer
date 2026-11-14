"""Calibrate the local detector so its score lines up with GPTZero (or with plain human/AI labels).

Folder layout (inside HUMANIZER_HOME, default ~/Humanizer):

    calibration/
        human/   *.txt or *.md   - text you wrote yourself
        ai/      *.txt or *.md   - raw AI output (ChatGPT, Claude, Gemini ...)
        rewrites/ *.txt or *.md  - optional: Humanizer outputs you checked on GPTZero
        gptzero.csv              - optional: file,ai_percent   (GPTZero's "AI" % for any file above)

Labels:
  * If gptzero.csv lists a file, the label is GPTZero's verdict (ai_percent >= 50 means AI).
    This is what makes the local score imitate GPTZero.
  * Otherwise the folder decides: human/ = 0, ai/ = 1. rewrites/ files without a GPTZero
    number are skipped.

Run:
    python scripts/calibrate.py                   # uses HUMANIZER_MODEL (default "fast")
    python scripts/calibrate.py --compare         # tries both presets, reports which separates better
    python scripts/calibrate.py --model accurate  # calibrate a specific preset

Writes calibration.json next to your profiles. Aim for 10+ files per side, 200+ words each.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from humanizer_mcp import config  # noqa: E402
from humanizer_mcp.detector import Detector  # noqa: E402
from humanizer_mcp.text_utils import read_document  # noqa: E402

FEATURES = ["discrepancy", "sentence_length_cv", "perplexity_cv"]


def load_dataset(root: Path) -> list[tuple[Path, int]]:
    gz: dict[str, float] = {}
    csv_path = root / "gptzero.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                gz[Path(row["file"]).name] = float(row["ai_percent"])
    items = []
    for sub, default in (("human", 0), ("ai", 1), ("rewrites", None)):
        for p in sorted((root / sub).glob("*")):
            if p.suffix.lower() not in {".txt", ".md", ".docx"}:
                continue
            if p.name in gz:
                items.append((p, int(gz[p.name] >= 50)))
            elif default is not None:
                items.append((p, default))
    return items


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return float(wins / (len(pos) * len(neg)))


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float = 0.1, steps: int = 4000, lr: float = 0.1):
    mean, std = X.mean(0), X.std(0)
    std[std == 0] = 1.0
    Z = (X - mean) / std
    w, b = np.zeros(Z.shape[1]), 0.0
    for _ in range(steps):
        p = 1 / (1 + np.exp(-(Z @ w + b)))
        gw = Z.T @ (p - y) / len(y) + l2 * w
        gb = float((p - y).mean())
        w -= lr * gw
        b -= lr * gb
    return w, b, mean, std


def featurize(det: Detector, items):
    rows = []
    for p, label in items:
        text = read_document(p)
        feats, _ = det.features(text)
        rows.append([feats[f] for f in FEATURES])
        print(f"  {label}  d={feats['discrepancy']:+.3f}  len_cv={feats['sentence_length_cv']:.2f}  "
              f"ppl_cv={feats['perplexity_cv']:.2f}  {p.name}", file=sys.stderr)
    return np.asarray(rows, dtype=float)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None, help='preset ("fast", "accurate") or Hugging Face id')
    ap.add_argument("--compare", action="store_true", help="score with both presets and compare")
    ap.add_argument("--dir", default=None, help="calibration folder (default HUMANIZER_HOME/calibration)")
    args = ap.parse_args()

    root = Path(args.dir) if args.dir else config.home_dir() / "calibration"
    items = load_dataset(root)
    y = np.asarray([lab for _, lab in items], dtype=float)
    if len(items) < 6 or y.sum() < 2 or (1 - y).sum() < 2:
        sys.exit(f"Need at least a few human and AI files in {root}/human and {root}/ai (found {len(items)}).")

    models = list(config.MODEL_PRESETS.values()) if args.compare else [
        config.MODEL_PRESETS.get(args.model, args.model) if args.model else config.detector_model()
    ]
    best = None
    for name in models:
        print(f"\nScoring {len(items)} files with {name} ...", file=sys.stderr)
        det = Detector(name)
        X = featurize(det, items)
        a = auc(X[:, 0], y)
        w, b, mean, std = fit_logistic(X, y)
        z = ((X - mean) / std) @ w + b
        acc = float(((z > 0) == (y == 1)).mean())
        print(f"{name}: AUC of raw discrepancy = {a:.3f}, combined accuracy on these files = {acc:.0%}")
        if best is None or acc > best[1]:
            best = (name, acc, w, b, mean, std, a)

    name, acc, w, b, mean, std, a = best
    # Sentence threshold: discrepancy where the text-level model flips, other features at their mean.
    d_i = FEATURES.index("discrepancy")
    if w[d_i] > 0:
        d_star = float(mean[d_i] - std[d_i] * b / w[d_i])
    else:
        d_star = float(np.median(np.asarray([0.0])))
    cal = {
        "model": name,
        "features": FEATURES,
        "weights": [float(x) for x in w],
        "bias": float(b),
        "mean": [float(x) for x in mean],
        "std": [float(x) for x in std],
        "sentence_threshold": round(d_star + 0.10, 3),
        "training_files": len(items),
        "training_accuracy": round(acc, 3),
        "discrepancy_auc": round(a, 3),
    }
    out = config.calibration_path()
    out.write_text(json.dumps(cal, indent=2), encoding="utf-8")
    print(f"\nSaved {out}  (model {name}, accuracy {acc:.0%}).")
    if name != config.detector_model():
        print(f'Set HUMANIZER_MODEL="{name}" in your Claude Desktop config so the server uses this model.')


if __name__ == "__main__":
    main()
