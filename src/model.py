"""
The text-to-SQL model wrapper + a manager for switching between CodeS backends.

Two inference backends, both fully local on Apple Silicon:

  - transformers (bf16, MPS): faithful to the reproduction pipeline; supports beam
    search (more accurate) but larger in memory and slower.
  - MLX (4-bit, Apple framework): quantized weights — ~4x smaller and much faster,
    lets bigger sizes fit a 16 GB Mac. Greedy decoding only (no beam search), so it
    needs a big-enough model to stay accurate — CodeS-3B 4-bit is the sweet spot.

CodeS ships in 1B/3B/7B/15B (no 4B/8B). Quantized MLX weights are built locally by
`scripts/convert_mlx.py` and live in `mlx_models/` (git-ignored, regenerable).

Backends (QUERYGENIE_BACKEND env var):
  - "codes" (default): the real model(s).
  - "mock"          : rule-based stand-in for offline UI dev. Never used in the demo.
"""

from __future__ import annotations

import gc
import os
import re

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Full-precision (transformers) checkpoints — downloaded on demand.
TRANSFORMERS_MODELS = {
    "CodeS-1B": "seeklhy/codes-1b",
    "CodeS-3B": "seeklhy/codes-3b",
    "CodeS-7B": "seeklhy/codes-7b",
    "CodeS-15B": "seeklhy/codes-15b",
}
# 4-bit MLX checkpoints — local dirs built by scripts/convert_mlx.py.
# The "-spider" variants are the Spider-fine-tuned (SFT) checkpoints — the ones the
# paper actually evaluates — and are the recommended default for the app.
MLX_MODELS = {
    "CodeS-3B-Spider · SFT (MLX 4-bit)": os.path.join(_REPO_ROOT, "mlx_models", "codes-3b-spider-4bit"),
    "CodeS-7B-Spider · SFT (MLX 4-bit)": os.path.join(_REPO_ROOT, "mlx_models", "codes-7b-spider-4bit"),
    "CodeS-3B base (MLX 4-bit)": os.path.join(_REPO_ROOT, "mlx_models", "codes-3b-4bit"),
    "CodeS-1B base (MLX 4-bit)": os.path.join(_REPO_ROOT, "mlx_models", "codes-1b-4bit"),
}
# GGUF (llama.cpp / Metal) checkpoints — single .gguf files. These are ready-made
# quantizations downloaded from the Hub (no local conversion needed). Q2_K is 2-bit
# and aggressive, but a 7B SFT model handles it well on our schemas.
GGUF_MODELS = {
    "CodeS-7B-Spider · SFT (GGUF Q2_K)": os.path.join(_REPO_ROOT, "gguf_models", "codes-7b-spider-Q2_K.gguf"),
}
DEFAULT_MODEL = "CodeS-1B"
_DEFAULT_MAX_NEW_TOKENS = 200


def available_models() -> list[str]:
    """Labels to show in the UI: MLX models present on disk (fine-tuned '-spider'
    first), then any GGUF models present, then the two safe transformers sizes."""
    labels = [lbl for lbl in MLX_MODELS if os.path.isdir(MLX_MODELS[lbl])]
    labels += [lbl for lbl in GGUF_MODELS if os.path.exists(GGUF_MODELS[lbl])]
    labels += ["CodeS-1B", "CodeS-3B"]
    return labels


def default_model() -> str:
    """Prefer the fine-tuned SFT MLX model if built (best on a Mac), then base MLX-3B,
    else the transformers 1B (always available)."""
    for lbl in ("CodeS-3B-Spider · SFT (MLX 4-bit)", "CodeS-3B base (MLX 4-bit)"):
        if os.path.isdir(MLX_MODELS[lbl]):
            return lbl
    return DEFAULT_MODEL


def _pick_device():
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _dtype_for(device):
    import torch

    if device in ("mps", "cuda"):
        return torch.bfloat16   # same range as fp32, half the memory, no fp16 NaNs
    return torch.float32


def _build_prompt(schema, question, prior_error):
    if prior_error:
        return f"{schema}\n{question}\n-- previous attempt failed: {prior_error}\n"
    return f"{schema}\n{question}\n"


class CodesBackend:
    """A transformers CodeS checkpoint (bf16, beam search). Loads lazily."""

    def __init__(self, model_id: str, label: str = ""):
        self.model_id = model_id
        self.label = label or model_id
        self._tok = None
        self._model = None
        self.device = None

    def load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = _pick_device()
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, dtype=_dtype_for(self.device))
        self._model.to(self.device)
        self._model.eval()

    def unload(self):
        import torch

        self._model = None
        self._tok = None
        gc.collect()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate(self, schema, question, prior_error=None, max_new_tokens=_DEFAULT_MAX_NEW_TOKENS):
        import torch

        self.load()
        inputs = self._tok(_build_prompt(schema, question, prior_error), return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs, max_new_tokens=max_new_tokens,
                num_beams=4, do_sample=False, pad_token_id=self._tok.eos_token_id,
            )
        text = self._tok.decode(out[0][inputs["input_ids"].shape[1]:],
                                skip_special_tokens=True, clean_up_tokenization_spaces=False)
        return _clean_sql(text)


class MLXBackend:
    """A 4-bit MLX CodeS checkpoint (greedy). Fast + small; loads lazily."""

    def __init__(self, path: str, label: str = ""):
        self.path = path
        self.label = label or path
        self.device = "mps (MLX 4-bit)"
        self._model = None
        self._tok = None

    def load(self):
        if self._model is not None:
            return
        from mlx_lm import load as mlx_load
        self._model, self._tok = mlx_load(self.path)

    def unload(self):
        self._model = None
        self._tok = None
        gc.collect()

    def generate(self, schema, question, prior_error=None, max_new_tokens=_DEFAULT_MAX_NEW_TOKENS):
        from mlx_lm import generate as mlx_generate

        self.load()
        text = mlx_generate(self._model, self._tok,
                            prompt=_build_prompt(schema, question, prior_error),
                            max_tokens=max_new_tokens, verbose=False)
        return _clean_sql(text)


class LlamaCppBackend:
    """A GGUF checkpoint run via llama.cpp with Metal (greedy). Loads lazily.

    Lets us run larger sizes (e.g. 7B) from a ready-made quantized .gguf with no
    local conversion. All transformer layers are offloaded to the GPU (Metal)."""

    def __init__(self, path: str, label: str = ""):
        self.path = path
        self.label = label or path
        self.device = "metal (GGUF)"
        self._llm = None

    def load(self):
        if self._llm is not None:
            return
        from llama_cpp import Llama
        self._llm = Llama(model_path=self.path, n_gpu_layers=-1, n_ctx=2048, verbose=False)

    def unload(self):
        self._llm = None
        gc.collect()

    def generate(self, schema, question, prior_error=None, max_new_tokens=_DEFAULT_MAX_NEW_TOKENS):
        self.load()
        out = self._llm(_build_prompt(schema, question, prior_error),
                        max_tokens=max_new_tokens, temperature=0.0, echo=False)
        return _clean_sql(out["choices"][0]["text"])


class MockBackend:
    """Rule-based stand-in for offline UI development. NOT for the demo."""

    device = "mock"
    label = "mock"

    def load(self):
        pass

    def generate(self, schema, question, prior_error=None, **_):
        q = question.lower()
        if "fail" in q and ("more than two" in q or "more than 2" in q):
            return ("SELECT name FROM student WHERE student_id IN "
                    "(SELECT student_id FROM result WHERE marks < 40 "
                    "GROUP BY student_id HAVING COUNT(subject) > 2)")
        if "average" in q or "avg" in q:
            return "SELECT department, AVG(marks) FROM student JOIN result USING(student_id) GROUP BY department"
        if "how many" in q or "count" in q:
            return "SELECT COUNT(*) FROM student"
        return "SELECT * FROM student"


def _make_backend(label: str):
    if label in MLX_MODELS:
        return MLXBackend(MLX_MODELS[label], label=label)
    if label in GGUF_MODELS:
        return LlamaCppBackend(GGUF_MODELS[label], label=label)
    if label in TRANSFORMERS_MODELS:
        return CodesBackend(TRANSFORMERS_MODELS[label], label=label)
    return CodesBackend(TRANSFORMERS_MODELS[DEFAULT_MODEL], label=DEFAULT_MODEL)


class ModelManager:
    """Holds at most one loaded backend and swaps it on request (frees the old one
    first, so a 16 GB Mac never holds two big models at once)."""

    def __init__(self):
        self._mock = os.environ.get("QUERYGENIE_BACKEND", "codes").lower() == "mock"
        self._current = None
        self._current_label = None

    def get(self, label: str):
        if self._mock:
            if self._current is None:
                self._current = MockBackend()
            return self._current
        if self._current_label == label and self._current is not None:
            return self._current
        if self._current is not None and hasattr(self._current, "unload"):
            self._current.unload()
        self._current = _make_backend(label)
        self._current_label = label
        return self._current


def _clean_sql(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*", "", text).strip().replace("```", "").strip()
    text = text.split(";")[0].strip()
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return " ".join(" ".join(lines).split())


# Backwards-compatible single-backend helper (used by tests / scripts).
def get_backend(label: str = DEFAULT_MODEL):
    if os.environ.get("QUERYGENIE_BACKEND", "codes").lower() == "mock":
        return MockBackend()
    return _make_backend(label)
