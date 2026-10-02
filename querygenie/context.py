"""
Follow-up questions in a chat ("only from CSE", "and the average?").

Chat models (Ollama, cloud, OpenAI-compatible servers) get real context: the earlier questions of the
chat and the SQL that answered them go into the prompt. CodeS models were fine-tuned on single
questions and have no notion of a conversation, so for them the previous question and the follow-up
are sent as one combined question - a best effort, not measured - and the application shows the text
it asked. With no history the evaluated pipeline runs exactly as measured.
"""
from __future__ import annotations

import re


def combined_question(history: list[dict] | None, question: str) -> str:
    """For CodeS-style models: the most recent earlier question followed by the follow-up."""
    if not history:
        return question
    prev = history[-1]["question"].strip().rstrip("?.! ")
    return f"{prev}? Follow-up: {question.strip()}"


def linking_text(history: list[dict] | None, question: str) -> str:
    """Text used for schema linking and value matching: the follow-up plus the earlier questions, so a
    follow-up that only says "what about IT?" still finds the tables and values the conversation is about."""
    if not history:
        return question
    return " ".join([h["question"] for h in history] + [question])


def history_block(history: list[dict] | None) -> str:
    """For chat models: the conversation so far, oldest first."""
    if not history:
        return ""
    lines = ["Earlier in this conversation (oldest first). The new question may refer to these:"]
    for h in history:
        lines.append(f"Question: {h['question']}")
        if h.get("sql"):
            lines.append(f"SQL used: {h['sql']}")
    return "\n".join(lines)


_SWAP = re.compile(r"^\s*(and|what about|how about|what of|same for|now|but)\b", re.I)


def substitute(history: list[dict] | None, question: str, match, values_of=None) -> str | None:
    """"What about IT?" after "Which students are in the CSE department?" means the same question with a
    different value. If the follow-up is short, starts like that, and names a stored value from the same
    column as a value in the previous question, return the previous question with the value swapped
    ("Which students are in the IT department?"); otherwise None. `match(text)` is the value retriever
    ({"table.column": [values]}); `values_of(column)` the column's stored values, used as a fallback
    because the retriever skips short common words (the department "IT" reads as the word "it")."""
    if not history or len(question.split()) > 8 or not _SWAP.match(question):
        return None
    prev = history[-1]["question"]
    before, now = match(prev), dict(match(question))
    if values_of:
        for column in before:
            hits = [v for v in values_of(column) if len(v) >= 2 and re.search(rf"(?<!\w){re.escape(v)}(?!\w)", question)]
            if hits:
                now.setdefault(column, []).extend(h for h in hits if h not in now.get(column, []))
    for column, new_values in now.items():
        for old in before.get(column, []):
            for new in new_values:
                if new.lower() != old.lower() and re.search(re.escape(old), prev, re.I) and not re.search(rf"\b{re.escape(new)}\b", prev, re.I):
                    return re.sub(re.escape(old), new, prev, count=1, flags=re.I)
    return None


# Words that point back at earlier questions. "that", "more" and "less" are left out: they are just as
# common in a standalone question ("students that failed more than two subjects").
_BACKREF = re.compile(r"\b(those|these|them|their|theirs|they|it|its|this|same|also|too|instead|only|among|above|"
                      r"previous|earlier|again|else|other|others|ones?|which of)\b", re.I)


def stands_alone(question: str, named_tables) -> bool:
    """A question that names a table itself and has no word pointing back ("those", "their", "only",
    "and ...") starts a new topic - "which student is the topper?" after a question about departments.
    Used for CodeS, which would otherwise get both questions glued together (combined_question)."""
    return (bool(named_tables) and len(question.split()) >= 3
            and not _BACKREF.search(question) and not _SWAP.match(question))


FOLLOW_UP_NOTE = ("This question continues the conversation above. Words like \"those\", \"them\", \"their\" or "
                  "\"it\" refer to the earlier questions: keep their conditions unless the new question changes them.")


def _result_text(h: dict) -> str:
    rows = "\n".join(" | ".join("" if v is None else str(v) for v in r) for r in h.get("rows", []))
    more = f"\n({h['rows_total']} rows in total)" if h.get("rows_total", 0) > len(h.get("rows", [])) else ""
    return f"The previous query returned:\n{' | '.join(map(str, h['columns']))}\n{rows}{more}".rstrip()


def history_messages(history: list[dict] | None, with_results: bool = False) -> list[dict]:
    """For chat models: the conversation as real turns - each earlier question as a user message and the
    SQL that answered it as the assistant's reply. If allowed, the first rows each query returned open the
    *next* user message ("The previous query returned: ..."), so the replies stay plain SQL for the model
    to imitate. The last result is returned separately via `last_result_text`."""
    msgs, carry = [], ""
    for h in history or []:
        msgs.append({"role": "user", "content": (carry + "\n\n" if carry else "") + h["question"]})
        msgs.append({"role": "assistant", "content": h.get("sql") or "-- no query ran for this question"})
        carry = _result_text(h) if with_results and h.get("columns") else ""
    return msgs


def last_result_text(history: list[dict] | None, with_results: bool = False) -> str:
    """The rows of the most recent answer, to open the new question's message."""
    h = (history or [None])[-1]
    return _result_text(h) if h and with_results and h.get("columns") else ""


def estimate_tokens(text: str) -> int:
    """A rough size for budgeting the context window (about four characters per token); not exact."""
    return len(text) // 4 + 1


def fit_history(history: list[dict], budget_tokens: int | None, max_turns: int = 20) -> list[dict]:
    """Keep the most recent turns that fit the budget (the oldest are dropped first)."""
    kept, used = [], 0
    for h in reversed(history):
        size = estimate_tokens(h["question"] + (h.get("sql") or "") + repr(h.get("rows", "")))
        if len(kept) >= max_turns or (budget_tokens is not None and used + size > budget_tokens):
            break
        kept.append(h); used += size
    return kept[::-1]
