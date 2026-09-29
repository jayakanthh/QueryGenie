"""
QueryGenie — web app.

Ask a plain-English question about a database; QueryGenie generates SQL with a local
CodeS model, executes it and shows the results table plus an auto-selected chart.
Everything runs locally.

With the evaluated pipeline (SFT CodeS + full CodeS prompt + 4 beam candidates) the app
also reports how confident it is — how many of its 4 candidate queries return the same
answer — and, depending on the strictness setting, abstains and asks the user to pick an
interpretation instead of returning a confident wrong table (the Month-3 enhancement,
results/week11_abstention.md). The fast MLX / GGUF models keep the simpler
generate -> execute -> self-correct flow and do not report confidence.

Run:
    python src/app.py                        # real models (downloads weights once)
    QUERYGENIE_BACKEND=mock python src/app.py  # UI only, no model
"""

from __future__ import annotations

import os
import sqlite3

import gradio as gr
import pandas as pd

from build_sample_db import ensure_sample_dbs
from charts import pick_chart
from engine import MODES, operating_points, run_confident, run_query
from model import ModelManager, available_models, default_model

SAMPLE_DBS = ensure_sample_dbs()
MANAGER = ModelManager()
OPS = operating_points()

EXAMPLES = [
    "Which students failed more than two subjects? A subject is failed if marks are below 40.",
    "How many students are in each year?",
    "What is the highest marks for each subject?",
    "List the subjects and the average marks for each subject.",
    "Average marks per department",
    "Who is the best student?",
    "List the top 3 students by total marks.",
]


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
HIDE = gr.update(visible=False)


def _table_and_chart(columns, rows):
    df = pd.DataFrame(rows[:200], columns=columns) if columns else pd.DataFrame()
    return df.round(2), pick_chart(df)   # round for display only; the chart uses exact values


def _preview(cand, n=3):
    if not cand.rows:
        return "no rows"
    shown = "; ".join(", ".join(str(v) for v in r) for r in cand.rows[:n])
    more = f" … (+{len(cand.rows) - n} more)" if len(cand.rows) > n else ""
    return f"{len(cand.rows)} row(s): {shown}{more}"


def _confidence_badge(d) -> str:
    if not d.candidates[d.selected].runs:
        return "⚪ **None of the candidate queries ran**"
    k = d.n_agree
    word = {4: "🟢 high", 3: "🟡 medium", 2: "🟠 low", 1: "🔴 very low"}[k]
    return f"**Confidence: {word}** — {k} of 4 candidate queries return this answer"


def _candidates_markdown(d, model_label, device) -> str:
    lines = [f"**Model:** `{model_label}` · **Device:** `{device}` · "
             f"agreement {d.n_agree}/4 · beam probability {d.beam_prob:.2f} · "
             f"confidence score {d.confidence:.3f}"]
    for i, c in enumerate(d.candidates):
        mark = "➡️ selected" if i == d.selected else f"candidate {i + 1}"
        status = _preview(c) if c.runs else f"❌ {c.error}"
        lines.append(f"\n**{mark}** — {status}\n```sql\n{c.sql}\n```")
    return "\n".join(lines)


def _choices(d):
    return [(f"{'ABCD'[k]} · {n} of 4 candidates · {_preview(d.candidates[i])}", i)
            for k, (i, n) in enumerate(d.interpretations())]


def ask(db_label, model_label, mode, question):
    """Returns: status, table, chart, interpretations radio, pick button, trace, state, sql."""
    if not question.strip():
        return "Enter a question.", pd.DataFrame(), None, NO_CHOICE, HIDE, "", None, ""
    backend = MANAGER.get(model_label)
    db_path = SAMPLE_DBS[db_label]

    if not getattr(backend, "has_confidence", False):
        conn = sqlite3.connect(db_path)
        try:
            run = run_query(backend, conn, question)
        finally:
            conn.close()
        trace = [f"**Model:** `{model_label}` · confidence is not measured for this backend "
                 f"(single greedy candidate). Attempts: {len(run.attempts)}"]
        for i, a in enumerate(run.attempts, 1):
            trace.append(f"\n**Attempt {i}** — {'✅ executed' if a.ok else '❌ ' + a.error}\n```sql\n{a.sql}\n```")
        if run.self_corrected:
            trace.insert(1, "✅ **Self-corrected** — the first query failed and was repaired.")
        status = "✅ Answered (no confidence estimate for this model)" if run.ok else "❌ The query failed."
        df, fig = _table_and_chart(run.result.columns, run.result.rows) if run.ok else (pd.DataFrame(), None)
        return status, df, fig, NO_CHOICE, HIDE, "\n".join(trace), None, _sql_md(run.sql)

    cr = run_confident(backend, db_path, question, mode)
    d = cr.decision
    badge = _confidence_badge(d)
    trace = _candidates_markdown(d, model_label, getattr(backend, "device", "?"))
    choices = _choices(d)

    if cr.answered:
        df, fig = _table_and_chart(cr.chosen.columns, cr.chosen.rows)
        if len(choices) > 1:
            status = (f"✅ **Answered.** {badge}\n\nOther readings of the question give different "
                      f"results — pick one below to see it.")
            radio = gr.update(choices=choices, value=d.selected, visible=True,
                              label="Other interpretations")
            return status, df, fig, radio, gr.update(visible=True), trace, d, _sql_md(cr.chosen.sql)
        return f"✅ **Answered.** {badge}", df, fig, NO_CHOICE, HIDE, trace, d, _sql_md(cr.chosen.sql)

    # abstain: no table — ask the user to choose
    if not choices:
        status = (f"🤔 **I couldn't answer this reliably.** {badge}. "
                  "Try rephrasing the question or naming the table/column you mean.")
        return status, pd.DataFrame(), None, NO_CHOICE, HIDE, trace, d, ""
    status = (f"🤔 **I'm not confident enough to answer.** {badge}.\n\n"
              "My candidate queries disagree. Which of these did you mean?")
    radio = gr.update(choices=choices, value=None, visible=True, label="Did you mean…")
    return status, pd.DataFrame(), None, radio, gr.update(visible=True), trace, d, ""


def _sql_md(sql):
    return f"**Query behind this table**\n```sql\n{sql}\n```" if sql else ""


def show_interpretation(d, idx):
    if d is None or idx is None:
        return pd.DataFrame(), None, ""
    c = d.candidates[int(idx)]
    df, fig = _table_and_chart(c.columns, c.rows)
    return df, fig, _sql_md(c.sql)


def build_ui():
    with gr.Blocks(title="QueryGenie") as demo:
        gr.Markdown(
            "# 🧞 QueryGenie\n"
            "Ask a database a question in plain English. Runs locally on open weights (CodeS) — "
            "your schema never leaves this machine. **It tells you when it isn't sure.**"
        )
        with gr.Row():
            db = gr.Dropdown(choices=list(SAMPLE_DBS.keys()),
                             value=list(SAMPLE_DBS.keys())[0], label="Database")
            model = gr.Dropdown(choices=available_models(), value=default_model(), label="Model",
                                info="'evaluated pipeline' = the setup measured on Spider (77.8%), "
                                     "with confidence. MLX / GGUF = faster, no confidence.")
        mode = gr.Radio(choices=MODE_CHOICES, value="balanced", label="When should it abstain?",
                        info="Coverage and accuracy measured on the Spider dev set (1,034 questions) "
                             "with CodeS-1B.")
        question = gr.Textbox(label="Ask in plain English", placeholder=EXAMPLES[0])
        submit = gr.Button("Ask", variant="primary")
        gr.Examples(examples=[[e] for e in EXAMPLES], inputs=[question])

        status = gr.Markdown()
        interp = gr.Radio(choices=[], visible=False, label="Did you mean…")
        pick = gr.Button("Show this interpretation", visible=False)
        table = gr.Dataframe(label="Results", interactive=False)
        sql_box = gr.Markdown()
        chart = gr.Plot(label="Auto chart")
        with gr.Accordion("Generated SQL and candidates", open=False):
            trace = gr.Markdown()
        state = gr.State(None)

        outs = [status, table, chart, interp, pick, trace, state, sql_box]
        submit.click(ask, inputs=[db, model, mode, question], outputs=outs)
        question.submit(ask, inputs=[db, model, mode, question], outputs=outs)
        pick.click(show_interpretation, inputs=[state, interp], outputs=[table, chart, sql_box])
        interp.change(show_interpretation, inputs=[state, interp], outputs=[table, chart, sql_box])
    return demo


if __name__ == "__main__":
    print(f"[QueryGenie] backend = {os.environ.get('QUERYGENIE_BACKEND', 'codes')}")
    build_ui().launch(theme=gr.themes.Soft())
