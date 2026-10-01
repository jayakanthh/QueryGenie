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
