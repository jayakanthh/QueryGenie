"""
The text-to-SQL model wrapper.

Loads CodeS-1B (`seeklhy/codes-1b`) once and generates SQL from a serialized
schema + a natural-language question. Runs locally on Apple Silicon (MPS) or CPU
— no data leaves the machine, which is the whole point of QueryGenie.

Two backends, selected by the QUERYGENIE_BACKEND env var:
  - "codes"  (default): the real model.
  - "mock"           : a tiny rule-based stand-in so the app/UI can be developed
                        and tested without the ~4.5 GB download. Never used in the
                        actual demo; it exists only for wiring/tests.
"""

from __future__ import annotations

import os
import re

MODEL_NAME = "seeklhy/codes-1b"
_DEFAULT_MAX_NEW_TOKENS = 200


def _pick_device():
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class CodesBackend:
    """Real CodeS-1B. Loads lazily on first generate()."""

    def __init__(self):
        self._tok = None
        self._model = None
        self.device = None

    def load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = _pick_device()
        # float32 everywhere for correctness on the prototype; fp16 on MPS can NaN.
        dtype = torch.float32
        self._tok = AutoTokenizer.from_pretrained(MODEL_NAME)
        self._model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=dtype)
        self._model.to(self.device)
        self._model.eval()

    def generate(self, schema: str, question: str, prior_error: str | None = None,
                 max_new_tokens: int = _DEFAULT_MAX_NEW_TOKENS) -> str:
        import torch

        self.load()
        prompt = f"{schema}\n{question}\n"
        if prior_error:
            # Nudge the model with the failure as a SQL comment before it continues.
            prompt = f"{schema}\n{question}\n-- previous attempt failed: {prior_error}\n"

        inputs = self._tok(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            out = self._model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                # Beam search (deterministic) — matches the Week-4 gate run and is
                # markedly more accurate than greedy on this model. A retry changes
                # the prompt (error hint), so it still explores a different query.
                num_beams=4,
                do_sample=False,
                pad_token_id=self._tok.eos_token_id,
            )
        text = self._tok.decode(
            out[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,  # BPE: cleanup corrupts spacing
        )
        return _clean_sql(text)


class MockBackend:
    """Rule-based stand-in for offline UI development. NOT for the demo."""

    device = "mock"

    def load(self):
        pass

    def generate(self, schema: str, question: str, prior_error: str | None = None,
                 **_) -> str:
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


def _clean_sql(text: str) -> str:
    """Keep only the first statement; strip comments/markdown fences the model may echo."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*", "", text).strip()
    text = text.replace("```", "").strip()
    # First statement only.
    text = text.split(";")[0].strip()
    # Drop leading comment lines.
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return " ".join(" ".join(lines).split())


def get_backend():
    name = os.environ.get("QUERYGENIE_BACKEND", "codes").lower()
    return MockBackend() if name == "mock" else CodesBackend()
