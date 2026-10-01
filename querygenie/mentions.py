"""
Does a question name anything in the database?

"Show me all" or "how many are there?" doesn't say *which* table. The model still writes a query - it
has to guess - and with a vague request its four candidates often make the same guess, so execution
agreement can look fine on a question that is really ambiguous. The application therefore checks
first whether the question mentions any table, column (by name or by its readable description) or
stored value; if it mentions none, it asks "all of what?" instead of presenting the guess as the answer.

This is an application safeguard on top of the evaluated pipeline; it changes no measured result
(Spider questions always name what they ask about).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# Words that carry no reference to the schema ("show me all the records").
_STOP = set("""
a about after all also an and any are as at be been by can could did do does each every everything
find for from get give had has have how i in into is it its list many me more most much my no not
of on or our out please records record rows row show so some table tables tell than that the their
them then there these they this those to total us was we were what when where which who whose why
will with would you your data details info information entries entry values value everyone anything
""".split())


def _forms(w: str) -> set[str]:
    """A word and its possible singular forms ("names" -> names, name, nam), so plurals match either way."""
    out = {w}
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        out |= {w[:-1], w[:-2] if w.endswith("es") else w[:-1]}
    if len(w) > 4 and w.endswith("ies"):
        out.add(w[:-3] + "y")
    return out


def _words(text: str) -> list[str]:
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text or "")          # camelCase -> camel Case
    return re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))


def _part_in(p: str, q: set[str]) -> bool:
    """One name part appears in the question: same word up to plurals, the same root ("injured" /
    "injuries"), or a near-identical spelling, which catches typos ("countires" / "countries")."""
    if _forms(p) & q:
        return True
    if len(p) < 5:
        return False
    return any(len(w) >= 5 and (w[:5] == p[:5] or SequenceMatcher(None, p, w).ratio() >= 0.8) for w in q)


def _named(name: str, q: set[str], joined: set[str]) -> bool:
    """A table/column name (or its description) is mentioned when any meaningful part of it is, or when
    two neighbouring question words spell it ("high schoolers" -> Highschooler)."""
    parts = [w for w in _words(name) if len(w) > 2 and w not in _STOP]
    if any(_part_in(p, q) for p in parts):
        return True
    flat = "".join(_words(name))
    return len(flat) >= 6 and bool(_forms(flat) & joined)


def schema_mentions(schema: dict, question: str, matched_values: dict | None = None) -> dict:
    """Tables, columns and stored values the question refers to.

    `schema` is the CodeS schema dict (pipeline / codes_db_utils.get_db_schema or a connector's
    introspect()); `matched_values` is the value retriever's output ({"table.column": [values]})."""
    words = _words(question)
    q = set().union(*[_forms(w) for w in words if w not in _STOP] or [set()])
    joined = set().union(*[_forms(a + b) for a, b in zip(words, words[1:])] or [set()])
    tables, columns = [], []
    for t in schema["schema_items"]:
        if _named(t["table_name"], q, joined) or _named(t.get("table_comment", ""), q, joined):
            tables.append(t["table_name"])
        comments = t.get("column_comments") or [""] * len(t["column_names"])
        for c, desc in zip(t["column_names"], comments):
            if _named(c, q, joined) or _named(desc, q, joined):
                columns.append(f"{t['table_name']}.{c}")
    values = sorted({f"{tc}={v}" for tc, vs in (matched_values or {}).items() for v in vs})
    return {"tables": tables, "columns": columns, "values": values}


def is_unclear(mentions: dict) -> bool:
    return not (mentions["tables"] or mentions["columns"] or mentions["values"])
