"""
The text-to-SQL model wrapper + a small manager for switching between CodeS sizes.

Loads a CodeS checkpoint (`seeklhy/codes-1b` / `-3b` / ...) and generates SQL from a
serialized schema + a natural-language question. Runs locally on Apple Silicon (MPS)
or CPU — no data leaves the machine.

CodeS ships in exactly four sizes: 1B, 3B, 7B, 15B (there is no 4B/8B). On a 16 GB
Mac, 1B and 3B are comfortable in bf16; 7B is tight and 15B won't fit.

Backends (QUERYGENIE_BACKEND env var):
  - "codes" (default): the real model.
  - "mock"          : a rule-based stand-in so the UI can be developed without the
                      multi-GB download. Never used in the actual demo.
"""

from __future__ import annotations

import gc
import os
import re

# label -> Hugging Face id. All four exist; the UI exposes the ones that fit the machine.
MODELS = {
    "CodeS-1B": "seeklhy/codes-1b",
    "CodeS-3B": "seeklhy/codes-3b",
    "CodeS-7B": "seeklhy/codes-7b",   # ~14 GB in bf16 — needs >16 GB RAM to be comfortable
    "CodeS-15B": "seeklhy/codes-15b",  # ~30 GB — not for a 16 GB Mac
}
# Shown in the app's dropdown (kept to what runs well on a 16 GB Apple Silicon Mac).
UI_MODELS = ["CodeS-1B", "CodeS-3B"]
DEFAULT_MODEL = "CodeS-1B"

_DEFAULT_MAX_NEW_TOKENS = 200


def _pick_device():
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _dtype_for(device):
    import torch

    # bf16 on GPU: same numeric range as fp32 (no fp16 NaNs) at half the memory.
    if device in ("mps", "cuda"):
        return torch.bfloat16
    return torch.float32


class CodesBackend:
    """A single CodeS checkpoint. Loads lazily on first generate()."""

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
        dtype = _dtype_for(self.device)
        self._tok = AutoTokenizer.from_pretrained(self.model_id)
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, dtype=dtype)
        self._model.to(self.device)
        self._model.eval()

    def unload(self):
        import torch

        self._model = None
        self._tok = None
        gc.collect()
        if hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.empty_cache()
        elif torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate(self, schema: str, question: str, prior_error: str | None = None,
                 max_new_tokens: int = _DEFAULT_MAX_NEW_TOKENS) -> str:
        import torch

        self.load()
        prompt = f"{schema}\n{question}\n"
        if prior_error:
            prompt = f"{schema}\n{question}\n-- previous attempt failed: {prior_error}\n"

        inputs = self._tok(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                # Beam search (deterministic) — markedly more accurate than greedy here.
                num_beams=4,
                do_sample=False,
                pad_token_id=self._tok.eos_token_id,
            )
        text = self._tok.decode(
            out[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return _clean_sql(text)


class MockBackend:
    """Rule-based stand-in for offline UI development. NOT for the demo."""

    device = "mock"
    label = "mock"

    def load(self):
        pass

    def generate(self, schema: str, question: str, prior_error: str | None = None, **_) -> str:
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


class ModelManager:
    """Holds at most one loaded CodeS backend and swaps it on request.

    A 16 GB Mac can't hold two large models at once, so switching models unloads the
    previous one and frees GPU memory before loading the next.
    """

    def __init__(self):
        self._mock = os.environ.get("QUERYGENIE_BACKEND", "codes").lower() == "mock"
        self._current: CodesBackend | MockBackend | None = None
        self._current_label: str | None = None

    def get(self, label: str):
        if self._mock:
            if self._current is None:
                self._current = MockBackend()
            return self._current
        if label not in MODELS:
            label = DEFAULT_MODEL
        if self._current_label == label and self._current is not None:
            return self._current
        # Switching: free the old model first.
        if isinstance(self._current, CodesBackend):
            self._current.unload()
        self._current = CodesBackend(MODELS[label], label=label)
        self._current_label = label
        return self._current


def _clean_sql(text: str) -> str:
    """Keep only the first statement; strip comments/markdown fences the model may echo."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
    text = text.replace("```", "").strip()
    text = text.split(";")[0].strip()
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return " ".join(" ".join(lines).split())


# Backwards-compatible single-backend helper (used by tests / scripts).
def get_backend(label: str = DEFAULT_MODEL):
    name = os.environ.get("QUERYGENIE_BACKEND", "codes").lower()
    if name == "mock":
        return MockBackend()
    return CodesBackend(MODELS.get(label, MODELS[DEFAULT_MODEL]), label=label)
