"""
QueryGenie — web app.

Ask a database a question in plain English; QueryGenie generates SQL with a local CodeS
model, executes it (read-only) and shows the results table plus an auto-selected chart.

With the evaluated pipeline (SFT CodeS + full CodeS prompt + 4 beam candidates) the app
also reports how confident it is — how many of its 4 candidate queries return the same
answer — and, depending on the strictness setting, abstains and asks the user to pick an
interpretation instead of returning a confident wrong table (the Month-3 enhancement,
results/week11_abstention.md). The fast MLX / GGUF models keep the simpler
generate -> execute -> self-correct flow and do not report confidence.

Databases: a bundled academic database, the 20 Spider development databases (if
downloaded — scripts/download_spider_dbs.py) and any SQLite file you upload.

Run:
    python src/app.py                        # real models (downloads weights once)
    QUERYGENIE_BACKEND=mock python src/app.py  # UI only, no model
"""

from __future__ import annotations

import html
import os
import sqlite3

import gradio as gr
import pandas as pd

from charts import pick_chart
from connectors import KINDS
from databases import add_upload, build_catalog, connect, schema_markdown, tables_of
from engine import MODES, operating_points, run_confident, run_confident_connected, run_query
from model import ModelManager, available_models, default_model

CATALOG = build_catalog()
MANAGER = ModelManager()
OPS = operating_points()


def _mode_label(mode: str, text: str) -> str:
    op = OPS.get(MODES[mode][1])
    if not op:
        return text
    return f"{text} — answers {op['coverage']*100:.0f}%, {op['accuracy']*100:.1f}% correct"


MODE_CHOICES = [
    (_mode_label("answer_all", "Answer everything"), "answer_all"),
    (_mode_label("balanced", "Balanced (tested)"), "balanced"),
    (_mode_label("strict", "Strict: 3 of 4 agree"), "strict"),
    (_mode_label("very_strict", "Very strict: all 4 agree"), "very_strict"),
]

NO_CHOICE = gr.update(choices=[], value=None, visible=False)
EMPTY = pd.DataFrame(columns=["Results will appear here"])
HIDE = gr.update(visible=False)

CSS = """
.qg-header {padding: 6px 2px 2px;}
.qg-header h1 {font-size: 2rem; margin: 0;}
.qg-header p {margin: 4px 0 10px; color: var(--body-text-color-subdued);}
.qg-chips {display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 4px;}
.qg-chip {border: 1px solid var(--border-color-primary); border-radius: 999px; padding: 4px 12px;
          font-size: 0.85rem; background: var(--block-background-fill);}
.qg-chip b {color: var(--body-text-color);}
.qg-card {width: 100%; box-sizing: border-box; border: 1px solid var(--border-color-primary); border-left-width: 6px; border-radius: 12px;
          padding: 12px 16px; background: var(--block-background-fill); margin: 4px 0;}
.qg-card .qg-title {font-weight: 700; font-size: 1.05rem;}
.qg-card .qg-sub {color: var(--body-text-color-subdued); margin-top: 2px;}
.qg-good {border-left-color: #0ca30c;} .qg-warning {border-left-color: #fab219;}
.qg-serious {border-left-color: #ec835a;} .qg-critical {border-left-color: #d03b3b;}
.qg-neutral {border-left-color: var(--border-color-primary);}
.qg-cols {color: var(--body-text-color-subdued); font-size: 0.85rem;}
.qg-dbinfo {font-size: 0.9rem;}
"""

HEADER = """
<div class="qg-header">
  <h1>🧞 QueryGenie</h1>
  <p>Ask a database a question in plain English. Runs locally on open weights (CodeS) — your data never
  leaves this machine. <b>It tells you when it isn't sure.</b></p>
  <div class="qg-chips">
    <span class="qg-chip">Reproduced CodeS-1B: <b>77.8%</b> on Spider (paper 77.9%)</span>
    <span class="qg-chip">With abstention: <b>83.3%</b> correct on 90% answered</span>
    <span class="qg-chip">Wrong answers <b>−32%</b></span>
    <span class="qg-chip">Read-only · local</span>
  </div>
</div>
"""


def card(level: str, title: str, sub: str = "") -> str:
    sub_html = f'<div class="qg-sub">{sub}</div>' if sub else ""
    return f'<div class="qg-card qg-{level}"><div class="qg-title">{title}</div>{sub_html}</div>'


def _table_and_chart(columns, rows):
    if not columns:
        return EMPTY, None
    df = pd.DataFrame(rows[:200], columns=columns)
    return df.round(2), pick_chart(df)   # round for display only; the chart uses exact values


def _preview(cand, n=3):
    if not cand.rows:
        return "no rows"
    shown = "; ".join(", ".join(str(v) for v in r) for r in cand.rows[:n])
    more = f" … (+{len(cand.rows) - n} more)" if len(cand.rows) > n else ""
    return f"{len(cand.rows)} row(s): {shown}{more}"


LEVELS = {4: ("good", "✅", "High confidence"), 3: ("warning", "🟡", "Medium confidence"),
          2: ("serious", "🟠", "Low confidence"), 1: ("critical", "🔴", "Very low confidence")}


def _candidates_markdown(d, model_label, device) -> str:
    lines = [f"**Model:** `{model_label}` · **Device:** `{device}` · agreement {d.n_agree}/4 · "
             f"beam probability {d.beam_prob:.2f} · confidence score {d.confidence:.3f}"]
    for i, c in enumerate(d.candidates):
        mark = "➡️ selected" if i == d.selected else f"candidate {i + 1}"
        status = _preview(c) if c.runs else f"❌ {c.error}"
        lines.append(f"\n**{mark}** — {status}\n```sql\n{c.sql}\n```")
    return "\n".join(lines)


def _choices(d):
    return [(f"{'ABCD'[k]} · {n} of 4 candidates · {_preview(d.candidates[i])}", i)
            for k, (i, n) in enumerate(d.interpretations())]


def _sql_md(sql, conn=None):
    if not sql:
        return ""
    md = f"**Query behind this table**\n```sql\n{sql}\n```"
    if conn is not None:
        try:
            md += f"\n**Sent to {conn.backend} (translated, read-only)**\n```sql\n{conn.translate(sql)}\n```"
        except Exception:
            pass
    return md


def ask(db_label, model_label, mode, question):
    """Returns: status, table, chart, interpretations radio, pick button, trace, state, sql."""
    if not question or not question.strip():
        return card("neutral", "Type a question, or pick one of the examples."), EMPTY, None, \
            NO_CHOICE, HIDE, "", None, ""
    info = CATALOG[db_label]
    backend = MANAGER.get(model_label)

    if info.conn is not None and not getattr(backend, "has_confidence", False):
        return card("critical", "Choose an “evaluated pipeline” model",
                    "Live database connections use the evaluated CodeS pipeline (1B or 3B)."), EMPTY, None, \
            NO_CHOICE, HIDE, "", None, ""

    if not getattr(backend, "has_confidence", False):
        conn = sqlite3.connect(f"file:{info.path}?mode=ro", uri=True)
        try:
            run = run_query(backend, conn, question)
        finally:
            conn.close()
        trace = [f"**Model:** `{model_label}` · confidence is not measured for this backend "
                 f"(single greedy candidate). Attempts: {len(run.attempts)}"]
        for i, a in enumerate(run.attempts, 1):
            trace.append(f"\n**Attempt {i}** — {'✅ executed' if a.ok else '❌ ' + a.error}\n```sql\n{a.sql}\n```")
        if run.ok:
            sub = "Self-corrected: the first query failed and was repaired." if run.self_corrected else \
                "This model gives no confidence estimate — use an “evaluated pipeline” model for that."
            status = card("neutral", "Answered", sub)
            df, fig = _table_and_chart(run.result.columns, run.result.rows)
        else:
            status, df, fig = card("critical", "🔴 The query failed", html.escape(run.attempts[-1].error)), EMPTY, None
        return status, df, fig, NO_CHOICE, HIDE, "\n".join(trace), None, _sql_md(run.sql if run.ok else "")

    if info.conn is not None:
        try:
            cr = run_confident_connected(backend, info.conn, question, mode)
        except Exception as exc:  # noqa: BLE001 - lost connection etc.
            return card("critical", "🔴 Database error", html.escape(str(exc).splitlines()[0][:300])), EMPTY, \
                None, NO_CHOICE, HIDE, "", None, ""
    else:
        cr = run_confident(backend, info.path, question, mode, info.comments)
    d = cr.decision
    trace = _candidates_markdown(d, model_label, getattr(backend, "device", "?"))
    choices = _choices(d)
    runs = d.candidates[d.selected].runs
    level, icon, word = LEVELS.get(d.n_agree, ("critical", "⚪", "No candidate ran")) if runs else \
        ("critical", "⚪", "No candidate query ran")
    agree = f"{d.n_agree} of 4 candidate queries return this answer" if runs else "none of the 4 candidates executed"

    if cr.answered:
        df, fig = _table_and_chart(cr.chosen.columns, cr.chosen.rows)
        if len(choices) > 1:
            status = card(level, f"{icon} Answered · {word}",
                          f"{agree}. Other readings give different results — pick one below to compare.")
            radio = gr.update(choices=choices, value=d.selected, visible=True, label="Other interpretations")
            return status, df, fig, radio, gr.update(visible=True), trace, d, _sql_md(cr.chosen.sql, info.conn)
        return card(level, f"{icon} Answered · {word}", agree + "."), df, fig, NO_CHOICE, HIDE, trace, d, \
            _sql_md(cr.chosen.sql, info.conn)

    if not choices:
        status = card("critical", "🤔 I couldn't answer this reliably",
                      f"{agree}. Try rephrasing, or name the table or column you mean.")
        return status, EMPTY, None, NO_CHOICE, HIDE, trace, d, ""
    status = card("critical", "🤔 I'm not confident enough to answer",
                  f"{word}: {agree}. My candidate queries disagree — which of these did you mean?")
    radio = gr.update(choices=choices, value=None, visible=True, label="Did you mean…")
    return status, EMPTY, None, radio, gr.update(visible=True), trace, d, ""


def show_interpretation(d, idx):
    if d is None or idx is None:
        return EMPTY, None, ""
    c = d.candidates[int(idx)]
    df, fig = _table_and_chart(c.columns, c.rows)
    return df, fig, _sql_md(c.sql)


def db_info(label):
    info = CATALOG[label]
    tables = tables_of(info)
    rows = sum(n for _, _, n in tables)
    return f"<div class='qg-dbinfo'>{info.source} · {len(tables)} tables · {rows:,} rows</div>"


def on_db_change(label):
    info = CATALOG[label]
    return (db_info(label), schema_markdown(info),
            gr.update(choices=info.examples, value=None, visible=bool(info.examples)),
            gr.update(value="", placeholder=info.examples[0] if info.examples else "Ask about this database"),
            card("neutral", "Ready", "Ask a question about this database, or pick an example."),
            EMPTY, None, NO_CHOICE, HIDE, "", None, "")


def on_upload(path):
    global CATALOG
    try:
        label = add_upload(path)
    except ValueError as exc:
        return gr.update(), card("critical", "🔴 Upload rejected", html.escape(str(exc)))
    CATALOG = build_catalog()
    return gr.update(choices=list(CATALOG), value=label), card("neutral", "Database added", html.escape(label))


def on_connect(kind, host, port, database, user, password):
    global CATALOG
    try:
        label = connect(kind, host, port, database, user, password)
    except Exception as exc:  # noqa: BLE001 - show the reason (bad password, host unreachable, ...)
        return gr.update(), card("critical", "🔴 Could not connect", html.escape(str(exc).splitlines()[0][:300])), ""
    CATALOG = build_catalog()
    # the password is not kept in the form after connecting
    return gr.update(choices=list(CATALOG), value=label), card("good", "✅ Connected", html.escape(label) +
                                                                " — schema read and value index built."), ""


def build_ui():
    first = next(iter(CATALOG))
    with gr.Blocks(title="QueryGenie") as demo:
        gr.HTML(HEADER)
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=320):
                db = gr.Dropdown(choices=list(CATALOG), value=first, label="Database",
                                 info="Bundled sample, the 20 Spider dev databases, or your own upload")
                info_md = gr.HTML(db_info(first))
                with gr.Accordion("Schema", open=False):
                    schema_md = gr.Markdown(schema_markdown(CATALOG[first]))
                upload = gr.UploadButton("⬆ Upload a SQLite database", file_types=[".sqlite", ".db", ".sqlite3"],
                                         size="sm")
                with gr.Accordion("🔌 Connect a live database", open=False):
                    gr.Markdown("<span class='qg-cols'>PostgreSQL or MySQL/MariaDB. Queries run in a read-only "
                                "transaction; use a read-only database user. The password is kept in memory only.</span>")
                    kind = gr.Dropdown(choices=list(KINDS), value="PostgreSQL", label="Type")
                    with gr.Row():
                        host = gr.Textbox(label="Host", value="localhost", scale=3)
                        port = gr.Textbox(label="Port", value="5432", scale=1, min_width=70)
                    database = gr.Textbox(label="Database")
                    with gr.Row():
                        user = gr.Textbox(label="User")
                        password = gr.Textbox(label="Password", type="password")
                    connect_btn = gr.Button("Connect", size="sm", variant="secondary")
                model = gr.Dropdown(choices=available_models(), value=default_model(), label="Model",
                                    info="“evaluated pipeline” = the setup measured on Spider, with confidence")
                mode = gr.Radio(choices=MODE_CHOICES, value="balanced", label="When should it abstain?",
                                info="Measured on the Spider dev set (1,034 questions), CodeS-1B")
            with gr.Column(scale=3):
                with gr.Row(equal_height=True):
                    question = gr.Textbox(label="Ask in plain English", scale=5, lines=1,
                                          placeholder=CATALOG[first].examples[0] if CATALOG[first].examples else "")
                    submit = gr.Button("Ask", variant="primary", scale=1, min_width=100)
                examples = gr.Radio(choices=CATALOG[first].examples, label="Try a question for this database",
                                    visible=bool(CATALOG[first].examples))
                status = gr.HTML(card("neutral", "Ready", "Ask a question, or pick an example."))
                interp = gr.Radio(choices=[], visible=False, label="Did you mean…")
                pick = gr.Button("Show this interpretation", visible=False, size="sm")
                with gr.Tabs():
                    with gr.Tab("Table"):
                        table = gr.Dataframe(value=EMPTY, interactive=False, show_label=False)
                        sql_box = gr.Markdown()
                    with gr.Tab("Chart"):
                        chart = gr.Plot(show_label=False)
                    with gr.Tab("All 4 candidates"):
                        trace = gr.Markdown()
        state = gr.State(None)

        outs = [status, table, chart, interp, pick, trace, state, sql_box]
        submit.click(ask, [db, model, mode, question], outs)
        question.submit(ask, [db, model, mode, question], outs)
        examples.input(lambda q: q, examples, question).then(ask, [db, model, mode, question], outs)
        pick.click(show_interpretation, [state, interp], [table, chart, sql_box])
        interp.change(show_interpretation, [state, interp], [table, chart, sql_box])
        db.change(on_db_change, db, [info_md, schema_md, examples, question] + outs)
        upload.upload(on_upload, upload, [db, status])
        kind.change(lambda k: str(KINDS[k][1]), kind, port)
        connect_btn.click(on_connect, [kind, host, port, database, user, password], [db, status, password])
    return demo


if __name__ == "__main__":
    print(f"[QueryGenie] backend = {os.environ.get('QUERYGENIE_BACKEND', 'codes')} · {len(CATALOG)} databases")
    build_ui().launch(theme=gr.themes.Soft(), css=CSS)
