"""
QueryGenie — prototype web app.

Ask a plain-English question about a database; QueryGenie generates SQL with the
local CodeS-1B model, executes it, self-corrects if it fails, and shows the
results table plus an auto-selected chart. Everything runs locally.

Run:
    # real model (downloads ~4.5 GB the first time):
    python src/app.py
    # UI-only, no model download:
    QUERYGENIE_BACKEND=mock python src/app.py
"""

from __future__ import annotations

import os
import sqlite3

import gradio as gr
import pandas as pd

from build_sample_db import ensure_sample_dbs
from charts import pick_chart
from engine import run_query
from model import get_backend

SAMPLE_DBS = ensure_sample_dbs()
BACKEND = get_backend()

EXAMPLES = [
    "Which students failed more than two subjects? A subject is failed if marks are below 40.",
    "What is the average marks per department?",
    "How many students are in each year?",
    "List the top 3 students by total marks.",
]


def _attempts_markdown(run) -> str:
    lines = [f"**Backend:** `{getattr(BACKEND, 'device', '?')}`  ·  "
             f"**Attempts:** {len(run.attempts)}"]
    if run.self_corrected:
        lines.append("✅ **Self-corrected** — the first query failed to execute and "
                     "was automatically repaired.")
    for i, a in enumerate(run.attempts, 1):
        status = "✅ executed" if a.ok else f"❌ {a.error}"
        lines.append(f"\n**Attempt {i}** — {status}\n```sql\n{a.sql}\n```")
    return "\n".join(lines)


def ask(db_label: str, question: str):
    if not question.strip():
        return "Enter a question.", pd.DataFrame(), None
    conn = sqlite3.connect(SAMPLE_DBS[db_label])
    try:
        run = run_query(BACKEND, conn, question)
    finally:
        conn.close()

    trace = _attempts_markdown(run)
    if not run.ok:
        return trace, pd.DataFrame(), None

    df = pd.DataFrame(run.result.rows, columns=run.result.columns)
    fig = pick_chart(df)
    return trace, df, fig


def build_ui():
    with gr.Blocks(title="QueryGenie") as demo:
        gr.Markdown(
            "# 🧞 QueryGenie\n"
            "A self-correcting natural-language → SQL interface. "
            "Runs locally on open weights (CodeS-1B) — your schema never leaves this machine."
        )
        with gr.Row():
            db = gr.Dropdown(choices=list(SAMPLE_DBS.keys()),
                             value=list(SAMPLE_DBS.keys())[0], label="Database")
            question = gr.Textbox(label="Ask in plain English", scale=3,
                                  placeholder=EXAMPLES[0])
        with gr.Row():
            submit = gr.Button("Generate SQL & run", variant="primary")
        gr.Examples(examples=[[e] for e in EXAMPLES], inputs=[question])

        trace = gr.Markdown(label="Generated SQL & self-correction trace")
        table = gr.Dataframe(label="Results", interactive=False)
        chart = gr.Plot(label="Auto chart")

        submit.click(ask, inputs=[db, question], outputs=[trace, table, chart])
        question.submit(ask, inputs=[db, question], outputs=[trace, table, chart])
    return demo


if __name__ == "__main__":
    print(f"[QueryGenie] backend = {os.environ.get('QUERYGENIE_BACKEND', 'codes')}")
    build_ui().launch(theme=gr.themes.Soft())
