# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(A desktop application: web technology rendered in a native window — WKWebView on macOS, Edge
WebView2 on Windows — packaged for macOS and Windows. Confirmed with the team 2026-09-30: the app
should **follow each operating system's conventions** (macOS vs Windows window chrome, controls,
spacing and shortcuts) rather than one identical look on both.)

## Stack

Confirmed 2026-09-30: native window + Python — pywebview for the window, a custom HTML/CSS/JS
interface talking to the existing Python engine (`src/codes_prompt.py`, `src/connectors.py`,
`src/model.py`), packaged with PyInstaller into a macOS `.app` and a Windows `.exe` (the Windows
build is produced on a Windows machine or GitHub Actions). On first launch the app downloads its
model weights and any optional sample data, with visible progress. The Gradio web app remains as a
developer tool.

## Users

Two groups, both confirmed:

- **Non-technical staff** — office, administrative, faculty and management users who know their
  data but not SQL. They ask plain-English questions and need answers they can trust.
- **Data analysts** — people who can read SQL and use QueryGenie to draft and check queries against
  their own databases faster, inspecting the generated SQL and the alternatives.

## Product Purpose

QueryGenie turns a plain-English question into SQL, runs it read-only against the user's database,
and shows the result as a table and a chart. Its distinguishing behaviour is that it says when it is
not sure: it generates four candidate queries, checks whether they agree, and when they do not it
asks "Did you mean…?" instead of returning a confident wrong answer. Success is a user getting a
correct answer, or an honest "I'm not sure — which of these?", never a silently wrong table.

## Positioning

Runs fully locally on open weights (CodeS) — no schema or data is sent to a third party — and it
knows when it doesn't know. Its confidence settings are backed by measured numbers, not claims.

## Operating Context

- Used against the user's own databases: a local SQLite file, or a live PostgreSQL / MySQL
  connection (read-only), plus a bundled academic sample and the 20 Spider databases.
- Analysts read and copy the generated SQL; non-technical users mainly read the table, chart and
  confidence message.
- First run happens on the user's machine with no prior setup; model weights (~4.5 GB for CodeS-1B)
  download then.
- Also presented at university project reviews (Team 18, KL University capstone).

## Capabilities and Constraints

- Evaluated pipeline: SFT CodeS-1B (and 3B), full CodeS database prompt, 4 beam candidates,
  execution-agreement confidence, abstention with alternative interpretations.
- Strictness settings map to measured operating points on Spider dev (CodeS-1B, official
  evaluator): answer everything 100% answered / 77.8% correct; balanced 90.4% / 83.3%; 3-of-4 agree
  62.8% / 86.1%; all 4 agree 39.8% / 88.3%.
- Live connections: SQL translated SQLite → PostgreSQL/MySQL; a single SELECT only; READ ONLY
  transaction; 30 s timeout; 1,000-row limit; password held in memory only.
- Inference is local: Apple Silicon (MPS) or CPU/NVIDIA on Windows. A question takes seconds once
  the model is loaded; the first question after launch is slower.
- Undecided: code signing / notarisation for distribution; auto-update; whether faster 4-bit
  models are offered in the desktop app.

## Brand Commitments

Name: **QueryGenie** (tagline in use: "A Self-Correcting Natural Language to SQL Interface").
Binding (the team explicitly liked them): **Montserrat** for interface text and **IBM Plex Mono**
for SQL, tables and code — the fonts of the current Gradio "Soft" build. Nothing else about the
current look is binding.

## Evidence on Hand

- Measured results: `results/reproduction_log.csv`, `results/week12_comparative_results.md`,
  `results/abstention_operating_points.json`, `results/postgres_translation_check.md`.
- Real app screenshots: `docs/figures/screenshots/`.
- No customers, testimonials, deployments or benchmarks beyond the above exist — do not fabricate
  any. Accuracy on non-SQLite engines and on real enterprise databases is not yet measured.

## Product Principles

1. **Honest over impressive.** Every confidence claim shown is a measured one; unmeasured settings
   say so.
2. **Uncertainty is a first-class answer.** "Did you mean…?" is a designed outcome, not an error.
3. **Show the work.** The SQL behind every table is one glance away, for analysts and reviewers.
4. **Local and read-only by default.** Nothing leaves the machine; nothing is ever written.
5. **Zero-setup first run.** A non-technical user gets from download to first answer without a
   terminal.
