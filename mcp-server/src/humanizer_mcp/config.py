"""Paths and settings. Everything can be overridden with environment variables,
which you set in the "env" block of claude_desktop_config.json."""

from __future__ import annotations

import os
from pathlib import Path

# Two detector presets that run on an ordinary laptop CPU.
MODEL_PRESETS = {
    # ~500 MB download, about 1-2 s per 1,000 words on a modern i5/i7.
    "fast": "openai-community/gpt2",
    # ~1 GB download, roughly 3-4x slower, closer to how modern chatbots write.
    "accurate": "Qwen/Qwen2.5-0.5B",
}


def home_dir() -> Path:
    """Where profiles, outputs and calibration live. Default: ~/Humanizer."""
    p = Path(os.environ.get("HUMANIZER_HOME", Path.home() / "Humanizer")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def output_dir() -> Path:
    p = Path(os.environ.get("HUMANIZER_OUTPUT_DIR", home_dir() / "output")).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def profiles_dir() -> Path:
    p = home_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def calibration_path() -> Path:
    return home_dir() / "calibration.json"


def detector_model() -> str:
    """HUMANIZER_MODEL can be a preset name ("fast", "accurate") or any
    Hugging Face causal language model id."""
    name = os.environ.get("HUMANIZER_MODEL", "fast")
    return MODEL_PRESETS.get(name, name)


def cpu_threads() -> int:
    env = os.environ.get("HUMANIZER_THREADS")
    if env:
        return max(1, int(env))
    # Leave a couple of cores free so the laptop stays responsive.
    return max(1, (os.cpu_count() or 4) - 2)
