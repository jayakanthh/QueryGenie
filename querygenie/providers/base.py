"""
Shared plumbing for every model the app can use besides the evaluated one.

A provider only has to return four candidate SQL texts for a prompt. Execution, selection,
agreement and abstention then run through exactly the same code as the evaluated pipeline
(pipeline.decide), so every model gets the four-cell confidence and the "not sure" behaviour.

Only the evaluated CodeS-1B-Spider pipeline was calibrated (results/abstention_operating_points.json);
for every other model the agreement is shown but its accuracy is not measured, and the app says so.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor

from ..pipeline import build_prefix, build_prefix_connected, decide

N_CANDIDATES = 4

SYSTEM_PROMPT = (
    "You translate a question about a database into one SQLite query. The database is described "
    "below: each table with its columns, their types, example values, primary keys and foreign keys, "
    "followed by values found in the database that match words in the question. "
    "Reply with the SQL query only - no explanation, no comments, no code fences."
)


def chat_prompt(prefix: str, question: str, ask: str | None = None, history: list | None = None) -> str:
    """The CodeS database description (the same schema linking the evaluated model sees), laid out
    for an instruction-following chat model. `question` is the text the prefix was built from; `ask`
    the question to put to the model (they differ for follow-ups, see querygenie/context.py)."""
    from ..context import history_block

    q = question.replace("\n", " ")
    context = prefix[: prefix.rfind(q)].rstrip() if q in prefix else prefix
    earlier = history_block(history)
    ask = (ask or question).replace("\n", " ")
    return f"{context}\n\n{earlier + chr(10) + chr(10) if earlier else ''}Question: {ask}\nSQLite query:"


_FENCE = re.compile(r"```(?:sql|sqlite)?\s*(.*?)```", re.S | re.I)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_START = re.compile(r"\b(SELECT|WITH)\b", re.I)


def extract_sql(text: str) -> str:
    """Pull the query out of a chat reply that may wrap it in prose, fences or reasoning tags."""
    text = _THINK.sub("", text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1)
    m = _START.search(text)
    return text[m.start():].strip() if m else text.strip()


class ProviderError(RuntimeError):
    """A failure the user can act on (no key, server not running, unknown model...)."""


class CandidateBackend:
    """Base class: subclasses implement `raw_candidates(prompt, question)`."""

    has_confidence = True
    calibrated = False           # agreement is shown, but its accuracy was never measured
    cloud = False                # True when the schema is sent to a third-party service
    chat = True                  # instruction model (chat prompt) vs CodeS-style completion model

    def __init__(self, model: str, label: str = "", effort: str | None = None):
        self.model = model
        self.label = label or model
        self.effort = effort          # provider-specific reasoning effort, None = the model's default
        self._schema_cache = {}

    # ---- to implement
    def raw_candidates(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def complete_once(self, prompt: str) -> str:
        """One greedy answer to `prompt` (used to repair a failed query)."""
        raise NotImplementedError

    def fix_sql(self, failed_sql: str, error: str) -> str:
        from ..repair import chat_repair_prompt, completion_hint
        _target, _schema, prompt = self.last_context
        if self.chat:
            return extract_sql(self.complete_once(chat_repair_prompt(prompt, failed_sql, error)))
        return self.complete_once(prompt + completion_hint(failed_sql, error))

    def unload(self):
        pass

    # ---- same interface as querygenie.model.CodesSFTBackend
    def _texts(self, question, history):
        """(text the prompt is built from, question to ask) - see querygenie/context.py."""
        from ..context import combined_question, linking_text
        if not history:
            return question, question
        return (linking_text(history, question), question) if self.chat else (combined_question(history, question),) * 2

    def decide(self, db_path: str, question: str, db_comments: dict | None = None, history: list | None = None):
        built, ask = self._texts(question, history)
        key = (db_path, os.path.getmtime(db_path))
        schema, prefix = build_prefix(db_path, built, schema=self._schema_cache.get(key),
                                      db_comments={os.path.splitext(os.path.basename(db_path))[0]: db_comments}
                                      if db_comments else None)
        self._schema_cache[key] = schema
        return self._decide(db_path, schema, prefix, built, ask, history)

    def decide_connected(self, source, question: str, history: list | None = None):
        built, ask = self._texts(question, history)
        schema, prefix = build_prefix_connected(source, built)
        return self._decide(source, schema, prefix, built, ask, history)

    def _decide(self, target, schema, prefix, question, ask=None, history=None):
        prompt = chat_prompt(prefix, question, ask, history) if self.chat else prefix
        self.last_context = (target, schema, prompt)       # for the optional repair step
        texts = [extract_sql(t) if self.chat else t for t in self.raw_candidates(prompt)]
        texts = (texts + [""] * N_CANDIDATES)[:N_CANDIDATES]
        # No beam scores outside the evaluated model: equal scores, so the tie-break is neutral.
        return decide(target, schema, texts, [0.0] * N_CANDIDATES)


def parallel(fn, n: int = N_CANDIDATES) -> list[str]:
    """Run n independent requests at once (used for services that sample one answer per call)."""
    with ThreadPoolExecutor(max_workers=n) as pool:
        futures = [pool.submit(fn, i) for i in range(n)]
        out, errors = [], []
        for f in futures:
            try:
                out.append(f.result())
            except ProviderError as exc:
                errors.append(exc)
            except Exception as exc:  # noqa: BLE001 - one failed sample shouldn't lose the rest
                errors.append(ProviderError(str(exc)))
    if not out and errors:
        raise errors[0]
    return out
