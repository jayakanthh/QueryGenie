"""
QueryGenie — prototype web app.

Ask a plain-English question about a database; QueryGenie generates SQL with a local
CodeS model, executes it, self-corrects if it fails, and shows the results table plus
an auto-selected chart. Everything runs locally. You can switch model size in the UI.

Run:
    # real model (downloads weights the first time):
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
from model import DEFAULT_MODEL, UI_MODELS, ModelManager

SAMPLE_DBS = ensure_sample_dbs()
MANAGER = ModelManager()

EXAMPLES = [
    "Which students failed more than two subjects? A subject is failed if marks are below 40.",
    "How many students are in each year?",
    "What is the highest marks for each subject?",
    "List the subjects and the average marks for each subject.",
    "List all students in the CSE department.",
    "Which students scored above 70 in any subject?",
]


def _attempts_markdown(run, model_label, device) -> str:
    lines = [f"**Model:** `{model_label}`  ·  **Device:** `{device}`  ·  "
             f"**Attempts:** {len(run.attempts)}"]
    if run.self_corrected:
        lines.append("✅ **Self-corrected** — the first query failed to execute and "
                     "was automatically repaired.")
    for i, a in enumerate(run.attempts, 1):
        status = "✅ executed" if a.ok else f"❌ {a.error}"
        lines.append(f"\n**Attempt {i}** — {status}\n```sql\n{a.sql}\n```")
    return "\n".join(lines)


def ask(db_label: str, model_label: str, question: str):
    if not question.strip():
        return "Enter a question.", pd.DataFrame(), None
    backend = MANAGER.get(model_label)
    conn = sqlite3.connect(SAMPLE_DBS[db_label])
    try:
        run = run_query(backend, conn, question)
    finally:
        conn.close()

    trace = _attempts_markdown(run, model_label, getattr(backend, "device", "?"))
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
            "Runs locally on open weights (CodeS) — your schema never leaves this machine."
        )
        with gr.Row():
            db = gr.Dropdown(choices=list(SAMPLE_DBS.keys()),
                             value=list(SAMPLE_DBS.keys())[0], label="Database")
            model = gr.Dropdown(choices=UI_MODELS, value=DEFAULT_MODEL, label="Model",
                                info="Larger = more accurate, slower. Switching reloads the model.")
        question = gr.Textbox(label="Ask in plain English", placeholder=EXAMPLES[0])
        submit = gr.Button("Generate SQL & run", variant="primary")
        gr.Examples(examples=[[e] for e in EXAMPLES], inputs=[question])

        trace = gr.Markdown(label="Generated SQL & self-correction trace")
        table = gr.Dataframe(label="Results", interactive=False)
        chart = gr.Plot(label="Auto chart")

        submit.click(ask, inputs=[db, model, question], outputs=[trace, table, chart])
        question.submit(ask, inputs=[db, model, question], outputs=[trace, table, chart])
    return demo


if __name__ == "__main__":
    print(f"[QueryGenie] backend = {os.environ.get('QUERYGENIE_BACKEND', 'codes')}")
    build_ui().launch(theme=gr.themes.Soft())
