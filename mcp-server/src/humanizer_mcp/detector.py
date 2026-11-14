"""Free, local AI-text detector that runs on a laptop CPU.

How it works, in plain words
----------------------------
A small language model reads the text one token at a time. At each token we
ask two things:

1. How likely was the token that was actually written?        -> ll
2. How likely is a "typical" token the model itself would pick? -> mu (and its spread, var)

AI text keeps choosing tokens that are about as likely as, or more likely
than, the model's own typical pick. People choose more surprising words.
So we measure the gap:

    discrepancy = (average ll - average mu) / sqrt(average var)

Near 0 or negative  -> reads like a person.
Clearly positive    -> reads like a model.

This is the "analytic sampling discrepancy" from Fast-DetectGPT (Bao et al.,
ICLR 2024), normalised per token so sentences of any length can be compared.

We also measure "burstiness": how much sentence length and per-sentence
predictability vary. People vary a lot; AI is even.

The raw numbers are turned into a 0-100 "AI likelihood" with either rough
defaults or your own calibration (see scripts/calibrate.py), which is how we
line this score up with GPTZero.
"""

from __future__ import annotations

import bisect
import re
import json
import math
import threading
import time
from dataclasses import dataclass

import numpy as np

from . import config
from .text_utils import sentences, words

# Rough uncalibrated defaults per model: (threshold, scale) for the logistic
# that turns discrepancy into a probability. Replace them by running
# scripts/calibrate.py on your own human and AI samples.
_DEFAULTS = {
    "openai-community/gpt2": (0.15, 0.08),
    "gpt2": (0.15, 0.08),
    "Qwen/Qwen2.5-0.5B": (0.20, 0.09),
}
_FALLBACK_DEFAULT = (0.18, 0.09)

_MIN_WORDS_TO_FLAG = 6


@dataclass
class TokenStats:
    starts: np.ndarray  # char start of each scored token
    ll: np.ndarray
    mu: np.ndarray
    var: np.ndarray


_REFERENCES_HEADING = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?\s+)?"
    r"(?:references|reference list|bibliography|works cited|literature cited|sources|cited works)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_CITATION_LIKE = re.compile(
    r"(?:\bvol\.\s*\d|\bpp?\.\s*\d|\bdoi\b|10\.\d{4,}/|https?://|\bet al\.,?\s*\(?\d{4}|^\s*\[\d+\]|\(\d{4}[a-z]?\)\.)",
    re.IGNORECASE,
)


def strip_references(text: str) -> str:
    """Drop the reference list: everything after the last 'References' style heading,
    if that heading sits in the second half of the document."""
    matches = list(_REFERENCES_HEADING.finditer(text))
    if matches and matches[-1].start() > len(text) * 0.5:
        return text[: matches[-1].start()]
    return text


def _flaggable(sentence: str, n_words: int) -> bool:
    """Only full prose sentences: long enough, ends like a sentence, not a citation or heading."""
    s = sentence.strip().rstrip("\"'”’)]")
    if n_words < _MIN_WORDS_TO_FLAG or not s or s[-1] not in ".!?":
        return False
    if sentence.lstrip().startswith(("#", "|", "- ", "* ")):
        return False
    return not _CITATION_LIKE.search(sentence)


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _discrepancy(ll: np.ndarray, mu: np.ndarray, var: np.ndarray) -> float:
    if len(ll) == 0:
        return 0.0
    return float((ll.mean() - mu.mean()) / math.sqrt(max(var.mean(), 1e-6)))


def _cv(values: list[float]) -> float:
    """Coefficient of variation: spread relative to the average."""
    if len(values) < 2:
        return 0.0
    arr = np.asarray(values, dtype=float)
    m = arr.mean()
    return float(arr.std() / m) if m > 0 else 0.0


class Detector:
    def __init__(self, model_name: str | None = None, model=None, tokenizer=None):
        self.model_name = model_name or config.detector_model()
        self._model = model
        self._tok = tokenizer
        self._lock = threading.Lock()
        self.load_seconds = 0.0

    # ------------------------------------------------------------------ model
    def load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(config.cpu_threads())
        t0 = time.time()
        # Use the local cache first so we don't contact Hugging Face on every start.
        try:
            self._load_from(local_only=True)
        except OSError:
            self._load_from(local_only=False)  # first run: download
        self.load_seconds = round(time.time() - t0, 2)

    def _load_from(self, local_only: bool) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tok = AutoTokenizer.from_pretrained(self.model_name, local_files_only=local_only)
        try:
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name, dtype=torch.float32, local_files_only=local_only
            )
        except TypeError:  # older transformers
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name, torch_dtype=torch.float32, local_files_only=local_only
            )
        self._model.eval()

    def _context_size(self) -> int:
        cfg = self._model.config
        n = getattr(cfg, "n_positions", None) or getattr(cfg, "max_position_embeddings", None) or 1024
        # Large-vocabulary models make big logit tensors, so keep windows modest on CPU.
        return int(min(n, 512))

    # ----------------------------------------------------------- token stats
    def token_stats(self, text: str) -> TokenStats:
        import torch

        self.load()
        tok = self._tok
        tok.model_max_length = 10**9  # we window long texts ourselves; silences the length warning
        enc = tok(text, return_offsets_mapping=True, add_special_tokens=False)
        ids: list[int] = list(enc["input_ids"])
        offsets = enc["offset_mapping"]
        bos = tok.bos_token_id if tok.bos_token_id is not None else None
        prefix = [bos] if bos is not None else []
        all_ids = prefix + ids
        first_target = len(prefix) if prefix else 1
        if len(all_ids) <= first_target:
            empty = np.zeros(0)
            return TokenStats(empty, empty, empty, empty)

        window = self._context_size()
        overlap = min(64, window // 4)
        lls, mus, vars_, starts = [], [], [], []
        pos = first_target
        with torch.inference_mode():
            while pos < len(all_ids):
                ctx_start = max(0, pos - overlap)
                end = min(len(all_ids), ctx_start + window)
                inp = torch.tensor([all_ids[ctx_start:end]])
                logits = self._model(inp).logits[0]
                # logits[i] predicts token i+1 of the window
                rows = logits[pos - 1 - ctx_start : end - 1 - ctx_start]
                targets = torch.tensor(all_ids[pos:end])
                for b in range(0, rows.shape[0], 128):
                    r = rows[b : b + 128].float()
                    logp = torch.log_softmax(r, dim=-1)
                    p = logp.exp()
                    t = targets[b : b + 128]
                    ll = logp.gather(-1, t.unsqueeze(-1)).squeeze(-1)
                    mu = (p * logp).sum(-1)
                    var = (p * logp.pow(2)).sum(-1) - mu.pow(2)
                    lls.append(ll.numpy())
                    mus.append(mu.numpy())
                    vars_.append(var.clamp_min(1e-6).numpy())
                for t_idx in range(pos, end):
                    starts.append(offsets[t_idx - len(prefix)][0])
                pos = end
        return TokenStats(
            np.asarray(starts),
            np.concatenate(lls),
            np.concatenate(mus),
            np.concatenate(vars_),
        )

    # ------------------------------------------------------------- scoring
    def _load_calibration(self) -> dict | None:
        path = config.calibration_path()
        if not path.exists():
            return None
        try:
            cal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return cal if cal.get("model") == self.model_name else None

    def _probability(self, features: dict, cal: dict | None) -> float:
        if cal:
            z = cal["bias"]
            for name, w, m, s in zip(cal["features"], cal["weights"], cal["mean"], cal["std"]):
                z += w * (features[name] - m) / (s or 1.0)
            return _sigmoid(z)
        threshold, scale = _DEFAULTS.get(self.model_name, _FALLBACK_DEFAULT)
        return _sigmoid((features["discrepancy"] - threshold) / scale)

    def features(self, text: str) -> tuple[dict, list[dict]]:
        """Return text-level features and per-sentence details."""
        stats = self.token_stats(text)
        spans = sentences(text)
        span_starts = [s.start for s in spans]
        buckets: list[list[int]] = [[] for _ in spans]
        for i, c in enumerate(stats.starts):
            k = bisect.bisect_right(span_starts, int(c)) - 1
            if 0 <= k < len(spans) and c < spans[k].end:
                buckets[k].append(i)

        sent_rows = []
        for k, span in enumerate(spans):
            idx = buckets[k]
            n_words = len(words(span.text))
            if not idx:
                continue
            ll, mu, var = stats.ll[idx], stats.mu[idx], stats.var[idx]
            sent_rows.append(
                {
                    "index": k,
                    "text": span.text,
                    "words": n_words,
                    "discrepancy": round(_discrepancy(ll, mu, var), 3),
                    "perplexity": round(float(math.exp(-ll.mean())), 1),
                }
            )

        scored = [r for r in sent_rows if r["words"] >= 3]
        feats = {
            "discrepancy": _discrepancy(stats.ll, stats.mu, stats.var),
            "perplexity": float(math.exp(-stats.ll.mean())) if len(stats.ll) else 0.0,
            "sentence_length_cv": _cv([r["words"] for r in scored]),
            "perplexity_cv": _cv([r["perplexity"] for r in scored]),
            "tokens": int(len(stats.ll)),
        }
        return feats, sent_rows

    def analyze(self, text: str, max_flagged: int = 12) -> dict:
        with self._lock:
            was_loaded = self._model is not None
            self.load()
            t0 = time.time()
            body = strip_references(text)
            feats, sent_rows = self.features(body)
            cal = self._load_calibration()
            prob = self._probability(feats, cal)

            threshold, _ = _DEFAULTS.get(self.model_name, _FALLBACK_DEFAULT)
            if cal and "sentence_threshold" in cal:
                sent_threshold = cal["sentence_threshold"]
            else:
                sent_threshold = threshold + 0.10
            candidates = [r for r in sent_rows if _flaggable(r["text"], r["words"])]
            flagged = sorted(
                (r for r in candidates if r["discrepancy"] > sent_threshold),
                key=lambda r: r["discrepancy"],
                reverse=True,
            )[:max_flagged]

            score = round(prob * 100, 1)
            if score < 30:
                verdict = "likely human"
            elif score < 60:
                verdict = "mixed"
            else:
                verdict = "likely AI"

            notes = []
            if feats["sentence_length_cv"] and feats["sentence_length_cv"] < 0.35:
                notes.append(
                    "Sentence lengths are very even. Mix short and long sentences."
                )
            if feats["perplexity_cv"] and feats["perplexity_cv"] < 0.25:
                notes.append(
                    "Every sentence is about equally predictable. Add specific, less obvious word choices in places."
                )
            if not cal:
                notes.append(
                    "Score is uncalibrated (rough defaults). Run scripts/calibrate.py to line it up with GPTZero."
                )
            if feats["tokens"] < 120:
                notes.append("Short text: scores under ~100 words are unreliable.")

            return {
                "ai_likelihood": score,
                "verdict": verdict,
                "calibrated": bool(cal),
                "model": self.model_name,
                "skipped_reference_list": len(body) < len(text),
                "features": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in feats.items()},
                "flagged_sentences": flagged,
                "sentence_threshold": round(sent_threshold, 3),
                "notes": notes,
                "seconds": round(time.time() - t0, 2),
                "model_load_seconds": 0.0 if was_loaded else self.load_seconds,
            }


_CACHE: dict[str, Detector] = {}
_CACHE_LOCK = threading.Lock()


def get_detector(model_name: str | None = None) -> Detector:
    name = model_name or config.detector_model()
    name = config.MODEL_PRESETS.get(name, name)
    with _CACHE_LOCK:
        if name not in _CACHE:
            _CACHE[name] = Detector(name)
        return _CACHE[name]
