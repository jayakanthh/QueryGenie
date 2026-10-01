"""
Models that run on this computer besides the evaluated one.

  CodesLocal  any CodeS-format model from Hugging Face or a local folder (the base CodeS-1B/3B, a
              CodeS fine-tune of your own) - same prompt and 4-beam search as the evaluated model
  MLXCodes    the 4-bit MLX CodeS checkpoints of the Gradio prototype (Apple Silicon)
  GGUFCodes   the GGUF CodeS checkpoints of the Gradio prototype (llama.cpp, Metal / CPU)

All use the CodeS prompt (schema + matched values + question). MLX and GGUF cannot do beam search,
so they draw the four candidates as one greedy answer plus three samples at temperature 0.7.
"""

from __future__ import annotations

import gc

from ..model import CodesSFTBackend
from ..pipeline import encode
from .base import N_CANDIDATES, CandidateBackend, ProviderError

MAX_NEW_TOKENS = 256
SAMPLE_TEMPERATURE = 0.7


class CodesLocal(CodesSFTBackend):
    """A CodeS-format checkpoint other than the evaluated one: same pipeline, not calibrated."""

    calibrated = False
    cloud = False


class MLXCodes(CandidateBackend):
    chat = False

    def __init__(self, path: str, label: str = ""):
        super().__init__(path, label)
        self._model = self._tok = None

    def load(self):
        if self._model is None:
            try:
                from mlx_lm import load
            except ImportError as exc:
                raise ProviderError("MLX models need the mlx-lm package (Apple Silicon only): "
                                    "pip install -r requirements-apple.txt") from exc
            self._model, self._tok = load(self.model)

    def unload(self):
        self._model = self._tok = None
        gc.collect()

    def raw_candidates(self, prompt):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        self.load()
        ids = encode(getattr(self._tok, "_tokenizer", self._tok), prompt)   # the HF tokenizer inside the wrapper
        return [generate(self._model, self._tok, prompt=ids, max_tokens=MAX_NEW_TOKENS, verbose=False,
                         sampler=make_sampler(temp=0.0 if i == 0 else SAMPLE_TEMPERATURE))
                for i in range(N_CANDIDATES)]

    def complete_once(self, prompt):
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        self.load()
        ids = encode(getattr(self._tok, "_tokenizer", self._tok), prompt)
        return generate(self._model, self._tok, prompt=ids, max_tokens=MAX_NEW_TOKENS, verbose=False,
                        sampler=make_sampler(temp=0.0))


class GGUFCodes(CandidateBackend):
    chat = False

    def __init__(self, path: str, label: str = ""):
        super().__init__(path, label)
        self._llm = None

    def load(self):
        if self._llm is None:
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise ProviderError("GGUF models need the llama-cpp-python package: "
                                    "pip install -r requirements-apple.txt") from exc
            self._llm = Llama(model_path=self.model, n_gpu_layers=-1, n_ctx=4096, verbose=False)

    def unload(self):
        self._llm = None
        gc.collect()

    def raw_candidates(self, prompt):
        self.load()
        ids = self._llm.tokenize(prompt.encode("utf-8"), add_bos=True)
        ids = ids[-(4096 - MAX_NEW_TOKENS):]                      # keep the end (the question)
        return [self._llm.create_completion(ids, max_tokens=MAX_NEW_TOKENS,
                                            temperature=0.0 if i == 0 else SAMPLE_TEMPERATURE,
                                            )["choices"][0]["text"]
                for i in range(N_CANDIDATES)]

    def complete_once(self, prompt):
        self.load()
        ids = self._llm.tokenize(prompt.encode("utf-8"), add_bos=True)[-(4096 - MAX_NEW_TOKENS):]
        return self._llm.create_completion(ids, max_tokens=MAX_NEW_TOKENS, temperature=0.0)["choices"][0]["text"]
