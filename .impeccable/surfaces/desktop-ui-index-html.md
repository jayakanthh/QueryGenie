---
version: 1
slug: "desktop-ui-index-html"
primary_target: "desktop/ui/index.html"
related_targets: []
---

## Scope

QueryGenie desktop app (pywebview window, macOS + Windows): first-run setup, Ask workspace,
Connections manager, History & settings. Visitor mode: **Operate**.

## Audience and task

Non-technical staff (ask, read the answer, trust or pick an interpretation) and data analysts
(read/edit the SQL, compare candidates). Frequent, repeated use. Must not look like a web page, must
not hide uncertainty, must not look like an AI chat. The user chooses what they see first: answer
first, confidence first, or answer and SQL side by side (remembered).

## Direction contract

THESIS: A database is a mailbox and every question is a message you can come back to; the answer
reads like the open message, with its confidence as the first line of the letter. Refuses the
category default of a chat transcript with a prompt box pinned to the bottom.

OWN-WORLD: The three-pane mail window of each OS, played straight: system window chrome; a
translucent-neutral sidebar of databases grouped by source (Samples, Files, Live connections) with
counts; a middle message list of past questions, each row carrying a confidence mark (four small
cells, filled per agreeing candidate) and a relative time; a white reading pane. Montserrat for UI,
IBM Plex Mono for SQL and table cells. Restrained colour: system neutrals plus one accent for
selection and primary action; status colours only for confidence (good / warning / serious /
critical), always with icon and words. macOS and Windows differ in title-bar layout, button order,
shortcuts (⌘ vs Ctrl), corner radii and control styling.

STORY: Pick a database in the sidebar, type a question in the compose bar at the top of the list,
read the answer in the reading pane; when the four candidates disagree the pane opens on "Did you
mean…?" with the readings as choices, never a silent table. Every question stays in the list.

FIRST VIEWPORT: 1280×800. Left 220 px sidebar; middle 320 px list with the compose field at its top;
right reading pane: header with the question, confidence line with the four-cell mark and plain
words, then (by the user's layout choice) the table, the chart tab, and the SQL with a Copy button.

FORM: Three-pane mail window — own list position 1 (IMPECCABLE’S PICK); seed key 2c27445a.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Memorable moment

The abstention: the reading pane opens on "I'm not sure which you mean" with two or three reading
cards (A / B / C, how many candidates back each, a preview of each result) instead of a table.

## Unresolved

Code signing / notarisation; auto-update; offering 4-bit models in the desktop app.
