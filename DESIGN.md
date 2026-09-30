---
name: QueryGenie
description: A self-correcting natural-language-to-SQL desktop app that tells you when it isn't sure.
colors:
  accent-blue: "#1a6fdb"
  accent-blue-win: "#005fb8"
  accent-blue-dark-text: "#5aa0ff"
  accent-blue-dark-fill: "#2a6dd6"
  window-ground: "#f2f2f5"
  sidebar-layer: "#e9e9ee"
  list-layer: "#fbfbfc"
  pane-white: "#ffffff"
  hairline: "#dcdce2"
  hairline-strong: "#c7c7cf"
  ink: "#1d1d1f"
  ink-secondary: "#55555c"
  ink-tertiary: "#6e6e75"
  dark-pane: "#19191b"
  dark-sidebar: "#232326"
  dark-ink: "#f2f2f5"
  confidence-good: "#0ca30c"
  confidence-warning: "#fab219"
  confidence-serious: "#ec835a"
  confidence-critical: "#d03b3b"
  chart-series: "#2a78d6"
typography:
  title:
    fontFamily: "Montserrat, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.3
    letterSpacing: "-0.015em"
  heading:
    fontFamily: "Montserrat, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    letterSpacing: "-0.01em"
  body:
    fontFamily: "Montserrat, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Montserrat, -apple-system, Segoe UI, system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 600
  data:
    fontFamily: "IBM Plex Mono, ui-monospace, SF Mono, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 400
    fontFeature: "tnum"
rounded:
  sm: "5px"
  md: "7px"
  lg: "10px"
  win-sm: "4px"
  win-lg: "8px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "28px"
components:
  button-primary:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.pane-white}"
    rounded: "{rounded.sm}"
    height: "26px"
    padding: "0 11px"
  button-secondary:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "26px"
    padding: "0 11px"
  source-item-selected:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.pane-white}"
    rounded: "{rounded.sm}"
    padding: "5px 8px"
  question-row-selected:
    backgroundColor: "{colors.accent-blue}"
    textColor: "{colors.pane-white}"
    padding: "10px 14px 10px 16px"
  compose-field:
    backgroundColor: "{colors.pane-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  verdict:
    backgroundColor: "#f4f4f7"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "12px 14px"
---

# Design System: QueryGenie

## Overview

**Creative North Star: "The Glass Ledger"**

QueryGenie's working is always visible: the SQL behind every table, the four candidate queries
behind every answer, and how many of them agree. The window is the familiar three-pane mail layout
of each operating system — databases in the sidebar, chats as messages, the chat's questions and
answers in the reading pane — so nothing about the frame needs learning; all the attention goes to the ledger of
evidence inside it.

It follows each OS rather than one look on both: macOS gets its 13px base, filled accent selection,
sheets that drop from the top of the window and Cancel-then-OK button order; Windows gets a 14px
base, the Fluent selection pill, centred dialogs with a footer band and OK-then-Cancel. Light or dark
follows the system setting. Components are **native but crisp**: OS conventions, with slightly
stronger type and sharper confidence states than a stock control.

**Key Characteristics:**
- Three panes: sources · chats · the open chat. The layout inside the answer is the user's choice
  (answer first, confidence first, or side by side) and is remembered.
- Confidence is a four-cell mark — one cell per candidate query — always paired with an icon and words.
- "I'm not sure which you mean" is a designed outcome with its own block, never an error.
- Montserrat for the interface, IBM Plex Mono for SQL and data; both self-hosted.

## Colors

Restrained: system-like neutrals in three layers plus one blue, with four confidence colours
reserved for confidence alone.

### Primary
- **Accent Blue** (`#1a6fdb`, macOS light): primary buttons, selection, focus, links, active tabs.
  White text on it is 4.9:1. Windows uses **Fluent Blue** (`#005fb8`).
- In dark mode the accent splits into **Sky Text Blue** (`#5aa0ff`, text and icons, 6.6:1 on the pane)
  and **Deep Fill Blue** (`#2a6dd6`, filled buttons and selection, white text 4.9:1).

### Neutral
- **Window Ground** (`#f2f2f5`), **Sidebar Layer** (`#e9e9ee`), **List Layer** (`#fbfbfc`),
  **Pane White** (`#ffffff`): four steps from frame to content, the reading pane brightest.
- **Hairline** (`#dcdce2`) separates panes and rows; **Strong Hairline** (`#c7c7cf`) outlines controls.
- **Ink** (`#1d1d1f`), **Secondary Ink** (`#55555c`, 7.4:1), **Tertiary Ink** (`#6e6e75`, 5.0:1).

### Confidence (status)
- **Good** `#0ca30c` (4 of 4 agree) · **Warning** `#fab219` (3 of 4) · **Serious** `#ec835a` (2 of 4) ·
  **Critical** `#d03b3b` (1 of 4, nothing ran, or the "not sure" block).

**The Reserved Status Rule.** The four confidence colours mean confidence and nothing else, and
never alone: every use carries the four-cell mark or an icon plus words ("High confidence", "2 of 4
candidate queries return this answer").

## Typography

**Interface:** Montserrat (400 / 500 / 600 / 700). **Data:** IBM Plex Mono (400 / 500), tabular figures.

One family carries headings, labels and body; the tight product scale (12 · 13 · 15 · 19 · 24 on
macOS, 12 · 14 · 16 · 20 · 26 on Windows) keeps density high without shouting.

- **Title** (700, 19px, -0.015em): the question at the top of the reading pane, max 70ch.
- **Heading** (700, 15px): pane titles, dialog titles, the verdict line.
- **Body** (400, 13px / 1.45): list rows, prose, form text.
- **Label** (600, 12px): sidebar group names, table headers, tab labels.
- **Data** (Plex Mono 12px): SQL, table cells, timestamps, row counts.

**The Code Is Mono Rule.** IBM Plex Mono is for SQL, data and measurements only — never as a
decorative "technical" voice for labels or headings.

## Layout

A fixed three-column window: sidebar 232px, question list 336px, reading pane fills the rest
(Windows 248 / 348). Below 1180px wide the columns tighten (208 / 292), the reading-pane toolbar
drops to icons with tooltips, and "side by side" stacks into one column. Minimum window 980 × 640.

Spacing is tight inside groups (4–8px) and generous between them (18–28px), with more space above a
heading than below it. The reading pane pads 22px 28px; list rows pad 10px 14px.

## Elevation & Depth

Flat and tonal: depth comes from the four neutral layers and hairlines, not shadows. Shadows appear
only on things that float above the window — menus, dialogs/sheets and the first-run assistant —
as a soft two-layer shadow with a 1px hairline, the native popover treatment of both OSes.

## Shapes

Small, even radii: 5px controls, 7px fields and tables, 10px panels (Windows: 4px and 8px).
Dialog sheets on macOS square their top corners where they attach to the window.

## Components

- **Source item (sidebar):** icon + name + question count; selected = accent fill (macOS) or subtle
  fill with a 3px accent pill (Windows). Files and live connections show a remove/disconnect control
  on hover or selection; live connections carry a green connected dot.
- **New chat button:** full-width primary button at the top of the chat list, with its ⌘N / Ctrl+N hint.
- **Chat row:** two-line title (the first question, renamable), then the latest answer's four-cell mark,
  the number of questions, and a relative time in mono. Keyboard: arrow keys move through rows.
- **Thread:** the open chat's questions oldest first, one ledger entry each (question, verdict, tabs),
  separated by hairlines; per-question Copy SQL / Ask again / Remove appear on hover.
- **Compose field:** docked at the bottom of the reading pane; Return asks, Shift+Return adds a line.
  Under it, a standing note that each question is answered on its own (the model does not see earlier
  turns) — the chat groups questions; it does not give the model memory.
- **Verdict:** tinted panel with the large four-cell mark, the level in words and the agreement
  sentence, plus the level's icon. Other readings appear as small inline buttons beneath it.
- **"Not sure" block:** critical-tinted header ("I'm not sure which you mean") above a row of reading
  cards (letter, support cells, row count, three-row preview); choosing one shows its table.
- **Tabs:** Table · Chart · SQL · All 4 queries, with a 2px accent underline on the active tab.
- **SQL block:** editable Plex Mono text area with Copy and "Run edit"; on live databases a second
  block shows the SQL actually sent to the server.
- **Candidate card:** "Query n" with Agrees / Different result / Did not run, and its SQL.
- **Schema map (Map view):** the reading pane's second view (Chat · Map). A left-to-right tree —
  database (accent fill) → tables (accent outline, row count in mono, chevron) → columns (neutral outline,
  type in mono, key icon for primary keys, link icon for foreign keys) — on a faint dot grid, joined by
  tapering accent curves. Drag or scroll to move, pinch / ⌘-scroll to zoom, controls bottom-right, find box
  top-left. Databases over ~32 columns start folded. Tapping a node opens a popover of ready-made
  questions and "Use in my question"; choices go into the compose field and are never sent without
  Return. A foreign key highlights its target table with a dashed outline and offers "Go to".
- **Model settings:** an "Answering with" panel (model, where it runs, calibrated or not) above five
  groups — Evaluated, Earlier prototype, Ollama, Your own model, Cloud services. Cloud services sit
  under a standing notice of what is sent; each provider row shows its key state ("Key saved in
  Keychain" / "No key"), a password field to add one, and a live model list from the provider.
  Unavailable models stay listed, dimmed, with the reason. Every answer names the model that wrote it
  and, when that model is not CodeS-1B, carries a "confidence not calibrated" note under the verdict.
- **Setup assistant:** step rail (Welcome · Your computer · Download · Ready) beside a content panel;
  a transform-animated progress meter with GB, MB/s and time left.

## Do's and Don'ts

- **Do** show confidence as cells plus words on every answer, in every layout.
- **Do** keep the SQL one click away, and editable.
- **Do** follow the host OS for button order, shortcuts (⌘ vs Ctrl), selection and dialogs.
- **Don't** use the confidence colours for anything other than confidence.
- **Don't** style the thread as chat bubbles or an assistant persona; each turn stays a ledger entry
  with its evidence, and never imply the model remembers earlier questions.
- **Don't** hide or soften the "not sure" state; it is the product's signature moment.
- **Don't** use emoji or text glyphs as icons; use the bundled Lucide set.
