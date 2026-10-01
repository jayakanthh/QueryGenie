"""
The evaluated model: Spider-fine-tuned CodeS with the full CodeS prompt, 4 scored beam
candidates, execution-agreement selection and confidence (harness v2, 77.8% EX on Spider dev
with CodeS-1B). Runs locally with transformers on Apple Silicon (MPS), CUDA or CPU.

The abstention threshold was calibrated on CodeS-1B; 3B uses the same threshold uncalibrated.
Older experimental backends (MLX, GGUF, base CodeS) live in legacy/models.py.
"""

from __future__ import annotations

import gc
import os

SFT_PIPELINE_MODELS = {
    "CodeS-1B-Spider · evaluated pipeline + confidence": "seeklhy/codes-1b-spider",
    "CodeS-3B-Spider · evaluated pipeline + confidence (threshold from 1B)": "seeklhy/codes-3b-spider",
}


def default_model() -> str:
    """The evaluated pipeline (the one whose accuracy and abstention were measured)."""
    return next(iter(SFT_PIPELINE_MODELS))


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


class CodesSFTBackend:
    """SFT CodeS + full CodeS prompt + 4 scored beam candidates. Returns a Decision
    (candidates, selection, confidence) — see pipeline.py."""

    has_confidence = True

    def __init__(self, model_id: str, label: str = ""):
        self.model_id = model_id
        self.label = label or model_id
        self._tok = None
        self._model = None
        self.device = None
        self._schema_cache = {}

    def load(self):
        if self._model is not None:
            return
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

    def decide(self, db_path: str, question: str, db_comments: dict | None = None,
               max_new_tokens: int = 256):
        """The evaluated setting: a local SQLite file."""
        from .pipeline import build_prefix

        key = (db_path, os.path.getmtime(db_path))
        schema, prefix = build_prefix(db_path, question, schema=self._schema_cache.get(key),
                                      db_comments={os.path.splitext(os.path.basename(db_path))[0]: db_comments}
                                      if db_comments else None)
        self._schema_cache[key] = schema
        return self._generate_and_decide(db_path, schema, prefix, max_new_tokens)

    def decide_connected(self, source, question: str, max_new_tokens: int = 256):
        """A connected database (connectors.SqlAlchemySource): same model, prompt shape and
        selection; SQL is translated to the target dialect and run read-only."""
        from .pipeline import build_prefix_connected

        schema, prefix = build_prefix_connected(source, question)
        return self._generate_and_decide(source, schema, prefix, max_new_tokens)

    def _generate_and_decide(self, target, schema, prefix, max_new_tokens):
        import torch
        from .pipeline import decide, encode

        self.last_context = (target, schema, prefix)       # for an optional repair step (querygenie/repair.py)
        self.load()
        ids = torch.tensor([encode(self._tok, prefix)], device=self.device)
        with torch.no_grad():
            gen = self._model.generate(input_ids=ids, attention_mask=torch.ones_like(ids),
                                       max_new_tokens=max_new_tokens, num_beams=4,
                                       num_return_sequences=4, pad_token_id=self._tok.eos_token_id,
                                       return_dict_in_generate=True, output_scores=True)
        texts = self._tok.batch_decode(gen.sequences[:, ids.shape[1]:], skip_special_tokens=True,
                                       clean_up_tokenization_spaces=False)
        return decide(target, schema, texts, [float(x) for x in gen.sequences_scores])

    def fix_sql(self, failed_sql: str, error: str, max_new_tokens: int = 256) -> str:
        """One repair attempt for a query that failed (application feature, not part of the evaluated
        pipeline): the same prompt with the failed query and its error as an SQL comment, greedy."""
        import torch
        from .pipeline import encode
        from .repair import completion_hint

        _target, _schema, prefix = self.last_context
        self.load()
        ids = torch.tensor([encode(self._tok, prefix + completion_hint(failed_sql, error))], device=self.device)
        with torch.no_grad():
            out = self._model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=max_new_tokens,
                                       num_beams=1, do_sample=False, pad_token_id=self._tok.eos_token_id)
        return self._tok.decode(out[0][ids.shape[1]:], skip_special_tokens=True, clean_up_tokenization_spaces=False)
