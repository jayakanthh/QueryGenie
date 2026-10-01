/* QueryGenie desktop — interface logic. Talks to desktop/api.py through pywebview
   (window.pywebview.api) or, in development, through desktop/devserver.py over HTTP. */
"use strict";

// ------------------------------------------------------------------ bridge
async function call(name, ...args) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[name]) return window.pywebview.api[name](...args);
  const r = await fetch("/api/" + name, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(args) });
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}
const api = new Proxy({}, { get: (_, name) => (...a) => call(name, ...a) });

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const icon = (n, cls = "i") => `<svg class="${cls}"><use href="#i-${n}"/></svg>`;
const S = { boot: null, dbs: [], db: null, chats: [], chat: null, T: {}, layout: "answer", mode: "balanced", working: false, failed: null, os: "mac" };

function when(iso) {
  const d = new Date(iso), s = (Date.now() - d) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 172800) return "Yesterday";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function cells(n, ran = true, lg = false) {
  const lvl = ran ? n : 0;
  return `<span class="cells lvl-${lvl}${lg ? " lg" : ""}" role="img" aria-label="${ran ? n : 0} of 4 candidate queries agree">${[0, 1, 2, 3].map((i) => `<i class="${i < lvl ? "on" : ""}"></i>`).join("")}</span>`;
}
const LEVEL = { 4: ["good", "circle-check", "High confidence"], 3: ["warning", "circle-alert", "Medium confidence"],
                2: ["serious", "triangle-alert", "Low confidence"], 1: ["critical", "circle-x", "Very low confidence"],
                0: ["critical", "circle-x", "No candidate query ran"] };
const SHORT = { 4: "High", 3: "Medium", 2: "Low", 1: "Very low", 0: "Failed" };
const isNum = (v) => typeof v === "number";
const fmt = (v) => (v === null || v === undefined ? "—" : isNum(v) ? (Number.isInteger(v) ? v.toLocaleString() : (+v.toFixed(2)).toLocaleString()) : String(v));
const mod = () => (S.os === "mac" ? "⌘" : "Ctrl+");

// ------------------------------------------------------------------ boot
async function boot() {
  if (S.booting) return;                       // pywebviewready and the dev fallback must not both boot
  S.booting = true;
  try {
    const r = await fetch("icons.svg"); $("#sprite").innerHTML = await r.text();
  } catch (e) { /* icons are decorative */ }
  S.boot = await api.boot();
  const forced = new URLSearchParams(location.search).get("os");
  S.os = forced || S.boot.platform;
  document.documentElement.classList.add(S.os === "win" ? "os-win" : "os-mac");
  // The packaged macOS window has no title bar (desktop/main.py): make room for the window buttons,
  // and let a double-click on a top bar zoom the window as the title bar would.
  if (S.os === "mac" && window.pywebview && !forced) {
    document.documentElement.classList.add("mac-frameless");
    document.addEventListener("dblclick", (e) => { if (e.target.classList && e.target.classList.contains("pywebview-drag-region")) api.window_zoom(); });
  }
  // Windows puts the primary button first; macOS last.
  if (S.os === "win") $$("[data-order]").forEach((el) => { const ok = $("[data-role=ok]", el); if (ok) el.prepend(ok); });
  S.layout = S.boot.settings.layout; S.mode = S.boot.settings.mode;
  // ?setup previews the assistant in development without downloading anything
  if (S.boot.setup_needed || new URLSearchParams(location.search).has("setup")) return startSetup();
  openApp();
}
window.addEventListener("pywebviewready", () => boot());
// In the packaged app pywebview fires "pywebviewready"; desktop/devserver.py defines QG_DEV instead.
window.addEventListener("DOMContentLoaded", () => { if (window.QG_DEV) boot(); });

// ------------------------------------------------------------------ first-run setup
const STEPS = ["welcome", "machine", "download", "ready"];
function showStep(name) {
  $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== name));
  const i = STEPS.indexOf(name);
  $$(".step").forEach((s, k) => { s.classList.toggle("now", k === i); s.classList.toggle("done", k < i); $(".dot", s).innerHTML = k < i ? icon("check", "i sm") : k + 1; });
}
function footButtons(panel, buttons) {
  const slot = $(`[data-panel=${panel}] [data-order]`);
  const ordered = S.os === "win" ? [...buttons].reverse() : buttons;
  slot.outerHTML = `<span data-order style="display:flex;gap:8px">${ordered.join("")}</span>`;
}
function startSetup() {
  $("#setup").hidden = false; showStep("welcome");
  $("[data-go=machine]").onclick = machineStep;
  $("#setup-finish").onclick = () => { $("#setup").hidden = true; openApp(); };
}
async function machineStep() {
  showStep("machine");
  footButtons("machine", ['<button class="btn" data-back>Back</button>', '<button class="btn primary" data-next disabled>Continue</button>']);
  $("[data-panel=machine] [data-back]").onclick = () => showStep("welcome");
  const hw = await api.hardware();
  $("#hw-lead").textContent = hw.note;
  $("#hw").innerHTML = [["Runs on", hw.accelerator_name], ["System", `${hw.os} ${hw.os_version || ""}`.trim()],
    ["Memory", hw.ram_gb ? `${hw.ram_gb} GB` : "Unknown"], ["Free disk", `${hw.free_disk_gb} GB`]]
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join("");
  const enough = hw.free_disk_gb >= 6;
  $("#hw-hint").textContent = enough ? "" : "Free at least 6 GB of disk space to continue.";
  const next = $("[data-panel=machine] [data-next]"); next.disabled = !enough; next.onclick = () => downloadStep(hw);
}
function downloadStep(hw) {
  showStep("download");
  const m1 = S.boot.models.find((m) => m.key === "codes-1b-spider"), m3 = S.boot.models.find((m) => m.key === "codes-3b-spider");
  const big = (hw.ram_gb || 0) >= 24;
  $("#dl-options").innerHTML = `
    <label class="opt"><input type="radio" name="dl-model" value="${m1.key}" checked><div><b>${m1.label} · ${m1.size_gb} GB</b><span>Recommended. The model whose accuracy was measured: 77.8% on the Spider benchmark, 83.3% when it may decline unsure questions.</span></div></label>
    <label class="opt"><input type="radio" name="dl-model" value="${m3.key}"><div><b>${m3.label} · ${m3.size_gb} GB</b><span>Larger and slower${big ? "" : " — needs about 24 GB of memory"}. Its confidence settings have not been calibrated separately.</span></div></label>
    <label class="opt"><input type="checkbox" id="dl-spider" ${S.boot.spider_installed ? "disabled" : "checked"}><div><b>20 sample databases${S.boot.spider_installed ? " · already installed" : " · about 0.2 GB"}</b><span>Concerts, flights, world countries and more, from the Spider benchmark (Hugging Face), each with example questions.</span></div></label>`;
  footButtons("download", ['<button class="btn" data-back>Back</button>', '<button class="btn primary" data-next>Download</button>']);
  $("[data-panel=download] [data-back]").onclick = () => machineStep();
  $("[data-panel=download] [data-next]").onclick = async (ev) => {
    const btn = ev.currentTarget; btn.disabled = true; $("[data-panel=download] [data-back]").disabled = true;
    $$("#dl-options input").forEach((i) => (i.disabled = true));
    const key = $("input[name=dl-model]:checked").value;
    $("#dl-error").textContent = ""; $("#dl-progress").hidden = false;
    await api.setup_start(key, $("#dl-spider").checked);
    pollSetup(btn);
  };
}
async function pollSetup(btn) {
  const s = await api.setup_status();
  $("#dl-msg").textContent = s.message || "Working…";
  if (s.total_bytes) {
    const pct = Math.min(100, (100 * s.done_bytes) / s.total_bytes);
    $("#dl-bar").style.transform = `scaleX(${(pct / 100).toFixed(4)})`;
    const eta = s.eta_s != null ? ` · ${s.eta_s > 90 ? Math.round(s.eta_s / 60) + " min" : s.eta_s + " s"} left` : "";
    $("#dl-num").textContent = `${(s.done_bytes / 1e9).toFixed(2)} of ${(s.total_bytes / 1e9).toFixed(2)} GB${s.rate_mb_s ? ` · ${s.rate_mb_s} MB/s` : ""}${eta}`;
  } else { $("#dl-num").textContent = ""; $("#dl-bar").style.transform = s.phase === "spider" ? "scaleX(1)" : "scaleX(0)"; }
  if (s.error) { $("#dl-error").textContent = s.error + " — check your connection and try again."; btn.disabled = false; btn.textContent = "Try again"; return; }
  if (s.finished) { S.boot = await api.boot(); return showStep("ready"); }
  setTimeout(() => pollSetup(btn), 500);
}

// ------------------------------------------------------------------ main window
async function refreshCounts() { S.counts = await api.history_counts(); $$("#sources [data-db]").forEach((b) => { const c = $(".count", b); if (c) c.textContent = S.counts[b.dataset.db] || ""; }); }
async function openApp() {
  $("#app").hidden = false;
  $("#new-chat-kbd").textContent = mod() + "N";
  S.dbs = await api.databases(); S.counts = await api.history_counts();
  let hidden = false; try { hidden = localStorage.getItem("qg.sidebar") === "hidden"; } catch (e) { /* default: shown */ }
  setSidebar(hidden); renderModelPill();
  try { S.view = localStorage.getItem("qg.view") === "map" ? "map" : "chat"; } catch (e) { S.view = "chat"; }
  renderSources();
  const last = localStorage.getItem("qg.db");
  selectDb(S.dbs.find((d) => d.id === last) ? last : S.dbs[0]?.id);
  wireApp();
}
const GROUPS = ["Sample databases", "Files", "Live connections"];
function renderSources() {
  const html = GROUPS.map((g) => {
    const items = S.dbs.filter((d) => d.group === g);
    if (!items.length && g !== "Live connections") return "";
    const body = items.length ? items.map((d) => `
      <button class="src" role="option" data-db="${esc(d.id)}" aria-selected="${S.db && S.db.id === d.id}">
        ${icon(d.live ? "server" : d.group === "Files" ? "file" : "database", "i src-icon")}
        <span class="name">${esc(d.label)}</span>${d.live ? '<span class="live-dot" title="Connected"></span>' : ""}
        <span class="count" title="Chats">${(S.counts || {})[d.id] || ""}</span>
        ${d.live || d.group === "Files" ? `<span class="src-x" role="button" tabindex="0" data-remove="${esc(d.id)}" title="${d.live ? "Disconnect" : "Remove from QueryGenie"}" aria-label="${d.live ? "Disconnect" : "Remove"} ${esc(d.label)}">${icon(d.live ? "x" : "trash-2", "i sm")}</span>` : ""}
      </button>`).join("") : `<button class="src" data-add-server>${icon("plug-zap", "i src-icon")}<span class="name" style="color:var(--ink-3)">Connect a server…</span></button>`;
    return `<div class="src-group"><h3>${g}</h3>${body}</div>`;
  }).join("");
  $("#sources").innerHTML = html;
  $$("#sources [data-db]").forEach((b) => (b.onclick = () => selectDb(b.dataset.db)));
  $$("#sources [data-db]").forEach((b) => (b.oncontextmenu = (e) => { e.preventDefault(); dbMenu(e, b.dataset.db); }));
  const add = $("#sources [data-add-server]"); if (add) add.onclick = () => openConnect();
  $$("#sources [data-remove]").forEach((x) => (x.onclick = (e) => { e.stopPropagation(); removeDb(x.dataset.remove); }));
}
async function selectDb(id) {
  if (!id) return;
  S.db = S.dbs.find((d) => d.id === id); localStorage.setItem("qg.db", id);
  $$("#sources [data-db]").forEach((b) => b.setAttribute("aria-selected", b.dataset.db === id));
  $("#db-title").textContent = S.db.label; $("#db-title").title = S.db.label;
  $("#db-meta").textContent = S.db.live ? "Live · read-only" : S.db.group === "Files" ? "SQLite file" : "Sample";
  $("#search").value = "";
  await loadChats();
  const last = localStorage.getItem("qg.chat." + id);
  S.mapSel = null; $("#map-pop").hidden = true;
  if (last && S.chats.some((c) => c.id === last)) await openChat(last); else newChat();
  showView();
}
async function loadChats() {
  S.chats = await api.chats(S.db.id, $("#search").value || null);
  renderChats();
}
function renderChats() {
  if (!S.chats.length) {
    $("#rows").innerHTML = `<div class="empty"><h4>${$("#search").value ? "No matching chats" : "No chats yet"}</h4>
      <p>${$("#search").value ? "Nothing matches your search." : `Start a chat and ask anything about <b>${esc(S.db.label)}</b>. Your chats stay here.`}</p></div>`;
    return;
  }
  $("#rows").innerHTML = S.chats.map((c) => `
    <button class="row" role="option" data-id="${c.id}" aria-selected="${S.chat && S.chat.id === c.id}">
      <div class="q">${esc(c.title)}</div>
      <div class="meta">${cells(c.agree, c.agree > 0)}<span>${c.questions} question${c.questions === 1 ? "" : "s"}</span>${S.working && S.working.chat === c.id ? `<span>${icon("loader-circle", "i sm spin")}</span>` : ""}<span class="when">${when(c.updated)}</span></div>
    </button>`).join("");
  $$("#rows [data-id]").forEach((b) => (b.onclick = () => { S.view = "chat"; openChat(b.dataset.id).then(showView); }));
}
function markSelected() { $$("#rows [data-id]").forEach((b) => b.setAttribute("aria-selected", !!S.chat && b.dataset.id === S.chat.id)); }

// ------------------------------------------------------------------ chats
function newChat() {
  S.chat = null; S.T = {}; localStorage.removeItem("qg.chat." + S.db.id);
  markSelected(); renderThread(); $("#question").focus();
}
async function openChat(id, scroll = "end") {
  const chat = await api.chat(id);
  if (!chat) return newChat();
  if (!S.chat || S.chat.id !== id) S.T = {};
  S.chat = chat; localStorage.setItem("qg.chat." + S.db.id, id);
  markSelected(); renderThread(scroll);
}
const turnState = (id) => (S.T[id] ||= { tab: null, reading: null, readingData: null, edited: null });

function renderThread(scroll = "end") {
  const c = S.chat;
  $("#question").placeholder = c ? "Ask another question…" : S.db.examples[0] ? `e.g. ${S.db.examples[0]}` : `Ask about ${S.db.label}…`;
  if (S.view === "map") { markSelected(); return; }
  const working = S.working && S.working.chat === (c ? c.id : null) && S.working.db === S.db.id;
  $("#chat-title").innerHTML = c ? `<span class="t pywebview-drag-region">${esc(c.title)}</span><span class="n pywebview-drag-region">${c.turns.length} question${c.turns.length === 1 ? "" : "s"}</span>`
                                 : `<span class="t pywebview-drag-region">New chat</span><span class="n pywebview-drag-region">${esc(S.db.label)}</span>`;
  $("#rename-chat").hidden = $("#delete-chat").hidden = !c;
  $("#layout-seg").hidden = !c;
  $$("#layout-seg [data-layout]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.layout === S.layout));
  $("#dock-hint").innerHTML = c ? `${icon("info", "i sm")}Each question is answered on its own — the model doesn't see earlier questions, so name the table or filter again.`
                                : `Return to ask · Shift+Return for a new line`;
  let html;
  if (!c && !working) {
    const ex = S.db.examples;
    html = `<div class="start"><div class="start-mark">${icon("messages-square")}</div><h1>New chat</h1>
      <p>Ask anything about <b>${esc(S.db.label)}</b> in plain English. You can keep asking in the same chat.</p>
      ${ex.length ? `<div class="suggest">${ex.slice(0, 4).map((q) => `<button data-ex="${esc(q)}">${icon("message-square-text", "i sm")}<span>${esc(q)}</span></button>`).join("")}</div>` : ""}</div>`;
  } else {
    html = (c ? c.turns : []).map((it) => `<article class="turn" data-hid="${it.id}">${turnHtml(it)}</article>`).join("");
    if (working) html += `<article class="turn" id="pending">${workingHtml(S.working.q)}</article>`;
    if (S.failed && S.failed.chat === (c ? c.id : null)) html += `<article class="turn">${failedHtml(S.failed)}</article>`;
  }
  $("#thread").innerHTML = html;
  $$("#thread [data-ex]").forEach((b) => (b.onclick = () => submitQuestion(b.dataset.ex)));
  $$("#thread .turn[data-hid]").forEach((el) => wireTurn(el));
  if (working) startTicker();
  const th = $("#thread");
  if (scroll === "end") th.scrollTop = th.scrollHeight;
}

// ------------------------------------------------------------------ asking
function autosize() { const t = $("#question"); t.style.height = "auto"; t.style.height = Math.min(120, t.scrollHeight) + "px"; }
async function submitQuestion(text) {
  const q = (text ?? $("#question").value).trim();
  if (!q || S.working) return;
  if (S.view === "map") { closePop(); setView("chat"); }
  const chatId = S.chat ? S.chat.id : null, db = S.db.id;
  S.working = { q, chat: chatId, db, t0: Date.now() }; S.failed = null;
  $("#question").value = ""; autosize(); $("#ask-btn").disabled = true;
  renderThread(); renderChats();
  try {
    const res = await api.ask(db, q, S.mode, chatId);
    S.working = false;
    if (S.db.id === db && (S.chat ? S.chat.id : null) === chatId) { await loadChats(); await openChat(res.chat_id); }
    else if (S.db.id === db) await loadChats();
    refreshCounts();
  } catch (e) {
    S.working = false; S.failed = { q, chat: chatId, msg: e.message || String(e) };
    if (S.db.id === db) { renderThread(); renderChats(); }
  } finally { $("#ask-btn").disabled = false; }
}
function workingHtml(q) {
  return `<div class="q-head"><h1>${esc(q)}</h1></div>
    <div class="working"><div class="w-line">${icon("loader-circle", "i spin")}<span id="w-msg">Writing four candidate queries…</span><span class="mono" id="w-t" style="margin-left:auto;color:var(--ink-3)"></span></div>
    <div class="sk" style="width:62%"></div><div class="sk" style="width:88%"></div><div class="sk" style="width:74%"></div></div>`;
}
function failedHtml(f) {
  return `<div class="q-head"><h1>${esc(f.q)}</h1></div><div class="error-box">${icon("triangle-alert")}<div><b>Something went wrong</b><div>${esc(f.msg)}</div></div></div>`;
}
function startTicker() {
  clearInterval(S.tick);
  S.tick = setInterval(() => {
    const el = $("#w-t"); if (!S.working || !el) return clearInterval(S.tick);
    const s = Math.round((Date.now() - S.working.t0) / 1000); el.textContent = s + " s";
    if (s >= 8 && s < 25) $("#w-msg").textContent = "Loading the model — only the first question takes this long…";
    if (s >= 25) $("#w-msg").textContent = "Still working — checking whether the four candidates agree…";
  }, 1000);
}

// ------------------------------------------------------------------ one turn of a chat
function turnHtml(it) {
  const t = turnState(it.id);
  const head = `<div class="q-head"><div class="q-line"><h1 class="selectable">${esc(it.question)}</h1>
      <span class="turn-tools">
        <button class="btn quiet icon" data-act="copy" title="Copy SQL">${icon("copy", "i sm")}</button>
        <button class="btn quiet icon" data-act="reask" title="Ask again in this chat">${icon("refresh-cw", "i sm")}</button>
        <button class="btn quiet icon" data-act="delete" title="Remove this question">${icon("trash-2", "i sm")}</button>
      </span></div>
    <div class="sub">${it.created ? `<span>${when(it.created)}</span>` : ""}<span>${modeName(it.mode)}</span>${it.engine ? `<span>${esc(it.engine.label)}${it.engine.cloud ? " · cloud" : ""}</span>` : ""}</div></div>`;
  const cal = it.engine && !it.engine.calibrated
    ? `<p class="note engine-note">${icon("info")}<span>Confidence here is how many of ${esc(it.engine.label)}'s four answers agree. How often that is right was measured only for CodeS-1B on Spider, not for this model.</span></p>` : "";
  // A question that names nothing in the database: ask "all of what?" - unless all four queries agree
  // on one reading, in which case show it, saying that it is the model's reading.
  const unanimous = it.ran && it.agree === 4;
  const showGuess = t.guess ?? unanimous;
  if (it.unclear && !showGuess) return head + clarifyHtml(it);
  const top = (it.unclear ? `<p class="note">${icon("info")}<span>Your question doesn't name a table or column here, so this is the model's reading of it${unanimous ? " (all four queries agree on it)" : ""}. <button class="btn quiet link" data-unclear-back>Choose what you meant instead</button></span></p>` : "")
    + (it.answered ? verdictHtml(it) : unsureHtml(it, t)) + cal;
  let body;
  if (!it.answered && t.reading == null) body = "";
  else if (S.layout === "confidence") body = `<div class="stack">${candidatesHtml(it)}${tabsHtml(it, t, ["table", "chart", "sql"])}</div>`;
  else if (S.layout === "split") body = `<div class="split"><div>${tabsHtml(it, t, ["table", "chart"])}</div><div class="stack">${sqlHtml(it, t)}${candidatesHtml(it)}</div></div>`;
  else body = tabsHtml(it, t, ["table", "chart", "sql", "candidates"]);
  const live = it.live ? `<p class="note">${icon("info")}Connected to ${esc(it.backend)}: the query was translated and run in a read-only transaction. The confidence percentages were measured on SQLite and are not yet calibrated for ${esc(it.backend)}.</p>` : "";
  return head + top + body + live;
}
// "Show me all": the question names no table, column or value, so ask which one instead of
// presenting the model's guess (see querygenie/mentions.py).
function clarifyHtml(it) {
  const tables = it.unclear.tables;
  return `<div class="unsure clarify"><div class="unsure-head">${icon("circle-help")}<div><h2>All of what?</h2>
    <p>Your question doesn't name anything in <b>${esc(S.db.label)}</b>, so any answer would be a guess. Choose what you mean and I'll ask again —
    or <button class="btn quiet link" data-guess>see what the model guessed</button>.</p></div></div>
    <div class="readings">${tables.map((t) => `
      <button class="reading" data-clarify="${esc(t.table)}"><span class="r-top">${icon("table", "i sm")}${esc(t.table)}<span style="margin-left:auto" class="mono">${t.rows.toLocaleString()} rows</span></span>
        <span class="r-prev">${t.columns.map(esc).join(", ")}${t.more ? ` … +${t.more}` : ""}</span></button>`).join("")}</div></div>`;
}
function clarifiedQuestion(q, table) {
  const m = q.trim().match(/^(.*?)([?.!]*)$/);
  return `${m[1]} in the ${table} table${m[2] || ""}`;
}
function modeName(m) {
  return { answer_all: "Answers everything", balanced: "Balanced", strict: "Strict (3 of 4 agree)", very_strict: "Very strict (all 4 agree)" }[m] || m;
}
function verdictHtml(it) {
  const [lvl, ic, word] = LEVEL[it.ran ? it.agree : 0];
  const alt = it.interpretations.length > 1 ? `<div class="note" style="margin-top:-6px">${icon("info")}<span>Other readings give different results: ${it.interpretations.filter((r) => r.index !== it.selected).map((r) => `<button class="btn quiet" style="height:20px;padding:0 5px" data-reading="${r.index}">Reading ${r.letter} · ${r.support} of 4</button>`).join(" ")}</span></div>` : "";
  return `<div class="verdict ${lvl}">${cells(it.agree, it.ran, true)}<div class="v-text"><strong>${word}</strong>
    <span>${it.ran ? `${it.agree} of 4 candidate queries return this answer.` : "None of the candidate queries could run."}</span></div>
    <span style="flex:1"></span>${icon(ic, "i v-icon")}</div>${alt}`;
}
function unsureHtml(it, t) {
  if (!it.interpretations.length) {
    return `<div class="unsure"><div class="unsure-head">${icon("circle-x")}<div><h2>I couldn't answer this reliably</h2>
      <p>None of the four candidate queries ran on this database. Try naming the table or column you mean, or rephrase the question.</p></div></div></div>`;
  }
  return `<div class="unsure"><div class="unsure-head">${icon("circle-help")}<div><h2>I'm not sure which you mean</h2>
    <p>The four candidate queries disagree — the most common answer has only ${it.agree} of 4 behind it. Choose the reading you meant; I won't guess.</p></div></div>
    <div class="readings">${it.interpretations.map((r) => `
      <button class="reading" data-reading="${r.index}" aria-pressed="${t.reading === r.index}">
        <span class="r-top"><span class="letter">${r.letter}</span>Reading ${r.letter}<span style="margin-left:auto">${cells(r.support)}</span></span>
        <span class="r-sub">${r.support} of 4 queries · ${r.rows_total} row${r.rows_total === 1 ? "" : "s"}</span>
        <span class="r-prev">${r.preview.map((row) => esc(row.map(fmt).join(", "))).join("<br>") || "no rows"}${r.rows_total > 3 ? "<br>…" : ""}</span>
      </button>`).join("")}</div></div>`;
}
function currentTable(it, t) {
  if (t.edited) return t.edited;
  if (!it.answered || t.reading != null) return t.readingData || { columns: [], rows: [] };
  return it;
}
function tabsHtml(it, t, list) {
  const names = { table: ["Table", "table"], chart: ["Chart", "chart-column"], sql: ["SQL", "code"], candidates: ["All 4 queries", "rows-3"] };
  if (!t.tab || !list.includes(t.tab)) t.tab = list[0];
  return `<div class="tabs" role="tablist">${list.map((x) => `<button role="tab" data-tab="${x}" aria-selected="${t.tab === x}">${icon(names[x][1], "i sm")}${names[x][0]}</button>`).join("")}</div>
    <div class="tab-body">${tabBody(it, t, t.tab)}</div>`;
}
function tabBody(it, t, x) {
  if (x === "table") return tableHtml(it, t, currentTable(it, t));
  if (x === "chart") return `<div class="chart">${chartSvg(currentTable(it, t).chart)}</div>`;
  if (x === "sql") return sqlHtml(it, t);
  return candidatesHtml(it);
}
function tableHtml(it, t, d) {
  const label = t.edited ? '<div class="table-note" style="margin:0 0 6px">Result of your edited query</div>' : t.reading != null && it.answered ? `<div class="table-note" style="margin:0 0 6px">Showing Reading ${it.interpretations.find((r) => r.index === t.reading)?.letter ?? ""}</div>` : "";
  if (!d.columns || !d.columns.length) return label + `<div class="chart-empty">${d.note ? esc(d.note) : "The query returned no rows."}</div>`;
  const numCol = d.columns.map((_, i) => d.rows.length && d.rows.every((r) => r[i] === null || isNum(r[i])));
  return label + `<div class="table-wrap"><table><thead><tr>${d.columns.map((c, i) => `<th class="${numCol[i] ? "n" : ""}">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${d.rows.map((r) => `<tr>${r.map((v, i) => `<td class="${numCol[i] ? "n" : ""}" title="${esc(fmt(v))}">${esc(fmt(v))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
    ${d.rows_total > d.rows.length ? `<div class="table-note">Showing the first ${d.rows.length} of ${d.rows_total.toLocaleString()} rows.</div>` : `<div class="table-note">${d.rows.length} row${d.rows.length === 1 ? "" : "s"}</div>`}`;
}
function selectedSql(it, t) {
  const idx = t.reading != null ? t.reading : it.selected;
  return it.candidates[idx] || it.candidates[0];
}
function sqlHtml(it, t) {
  const c = selectedSql(it, t);
  const sent = c.sent_sql ? `<div class="sql-block" style="margin-top:10px"><div class="sql-bar">${icon("server", "i sm")}Sent to ${esc(it.backend)} (translated)</div><pre class="sql selectable">${esc(c.sent_sql)}</pre></div>` : "";
  return `<div class="sql-block"><div class="sql-bar" title="Edit the query and run your own version">${icon("code", "i sm")}SQL<span class="spacer"></span>
      <button class="btn quiet" data-sql="copy">${icon("copy", "i sm")}Copy</button><button class="btn" data-sql="run" disabled title="Run your edited query (read-only)">${icon("play", "i sm")}Run edit</button></div>
    <textarea class="sql" data-sql="edit" spellcheck="false">${esc(c.sql)}</textarea></div>${sent}<div class="form-msg bad" data-sql="msg"></div>`;
}
function candidatesHtml(it) {
  return `<div class="cands">${it.candidates.map((c, i) => {
    const st = !c.runs ? `<span class="state bad">${icon("circle-x", "i sm")}Did not run</span>` : c.agrees ? `<span class="state ok">${icon("circle-check", "i sm")}Agrees</span>` : `<span class="state diff">${icon("circle-alert", "i sm")}Different result</span>`;
    return `<div class="cand"><div class="cand-top">Query ${i + 1}${i === it.selected ? ' <span class="kbd">selected</span>' : ""}${st}</div>
      <pre class="selectable">${esc(c.sql)}</pre>${!c.runs && c.error ? `<pre style="color:var(--critical)">${esc(c.error)}</pre>` : ""}</div>`;
  }).join("")}</div>`;
}

// ------------------------------------------------------------------ views: chat or schema map
function setView(v) {
  S.view = v; try { localStorage.setItem("qg.view", v); } catch (e) { /* per-viewer convenience only */ }
  showView();
}
function showView() {
  const map = S.view === "map";
  $("#thread").hidden = map; $("#map").hidden = !map; $("#bar-chat").hidden = map;
  $$("#view-seg [data-view]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.view === S.view));
  if (map) renderMap(); else renderThread("keep");
}

// ------------------------------------------------------------------ schema map
// A left-to-right tree: database -> tables -> columns. Tap a node for questions to ask about it;
// they are placed in the question box, never sent without the user pressing Return.
const MAPS = {};                                            // db id -> { data, open:Set, t:{k,tx,ty}, fitted }
const FONT = { root: "700 14px Montserrat", table: "700 13px Montserrat", col: "500 12px Montserrat", mono: "400 12px 'IBM Plex Mono'" };
const G = { tableH: 34, colH: 26, colPitch: 32, blockGap: 16, gap1: 84, gap2: 64, rootH: 40 };
function textW(text, font) { const c = (textW.c ||= document.createElement("canvas").getContext("2d")); c.font = font; return c.measureText(String(text)).width; }

async function renderMap() {
  const db = S.db, m = (MAPS[db.id] ||= { data: null, open: new Set(), t: { k: 1, tx: 0, ty: 0 }, fitted: false });
  $("#chat-title").innerHTML = `<span class="t pywebview-drag-region">Schema map</span><span class="n pywebview-drag-region">${esc(db.label)}</span>`;
  $("#dock-hint").innerHTML = `${icon("info", "i sm")}Tap a table or column to ask about it. Questions you pick appear here — edit, then press Return.`;
  if (!m.data) {
    $("#map-g").innerHTML = "";
    try { m.data = await api.schema_map(db.id); } catch (e) { m.data = []; }
    if (S.db.id !== db.id) return;
    const cols = m.data.reduce((n, t) => n + t.columns.length, 0);
    if (cols <= 32) m.data.forEach((t) => m.open.add(t.table));   // small databases open fully; larger ones fold
    await document.fonts.ready;
  }
  const nT = m.data.length, nC = m.data.reduce((n, t) => n + t.columns.length, 0);
  $("#chat-title").innerHTML = `<span class="t pywebview-drag-region">Schema map</span><span class="n pywebview-drag-region">${nT} table${nT === 1 ? "" : "s"} · ${nC} columns</span>`;
  $("#map-all").title = m.open.size === nT ? "Hide all columns" : "Show all columns";
  drawMap(m);
  if (!m.fitted) { fitMap(m, false); m.fitted = true; } else applyT(m);
}
function layoutMap(m) {
  const root = { kind: "root", id: "root", label: S.db.label, x: 0, w: textW(S.db.label, FONT.root) + 48, h: G.rootH };
  const tables = m.data.map((t) => ({ kind: "table", id: "t:" + t.table, t, label: t.table, open: m.open.has(t.table),
    w: 14 + textW(t.table, FONT.table) + 10 + textW(t.rows.toLocaleString(), FONT.mono) + 32, h: G.tableH }));
  const tw = Math.max(120, ...tables.map((n) => n.w)), x1 = root.w + G.gap1, x2 = x1 + tw + G.gap2;
  const cols = []; let y = 0;
  tables.forEach((n) => {
    n.x = x1; n.w = tw;
    const list = n.open ? n.t.columns : [];
    const block = Math.max(G.tableH, list.length * G.colPitch - (G.colPitch - G.colH));
    n.y = y + block / 2 - G.tableH / 2;
    list.forEach((c, i) => {
      const extra = (c.pk ? 18 : 0) + (c.ref ? 18 : 0);
      cols.push({ kind: "col", id: `c:${n.t.table}.${c.name}`, c, parent: n, label: c.name, x: x2, y: y + i * G.colPitch, h: G.colH,
        w: 12 + extra + textW(c.name, FONT.col) + (c.type ? 8 + textW(c.type, FONT.mono) : 0) + 12 });
    });
    y += block + G.blockGap;
  });
  const H = Math.max(G.rootH, y - G.blockGap);
  root.y = H / 2 - G.rootH / 2;
  const W = cols.length ? Math.max(...cols.map((c) => c.x + c.w)) : x1 + tw;
  return { root, tables, cols, W, H };
}
function curve(x1, y1, x2, y2) { const mx = x1 + (x2 - x1) * 0.55; return `M${x1},${y1} C${mx},${y1} ${x1 + (x2 - x1) * 0.45},${y2} ${x2},${y2}`; }
function drawMap(m) {
  const L = (m.L = layoutMap(m)), q = ($("#map-find").value || "").trim().toLowerCase();
  const hit = (s) => q && s.toLowerCase().includes(q);
  const match = (n) => !q || (n.kind === "table" ? hit(n.t.table) || n.t.columns.some((c) => hit(c.name)) : n.kind === "col" ? hit(n.c.name) || hit(n.parent.t.table) : true);
  const sel = S.mapSel, linked = sel && sel.kind === "col" && sel.c.ref ? "t:" + sel.c.ref[0].toLowerCase() : null;
  let edges = "", nodes = "";
  L.tables.forEach((n) => { edges += `<path class="m-edge root${match(n) ? "" : " dim"}" d="${curve(L.root.x + L.root.w, L.root.y + L.root.h / 2, n.x, n.y + n.h / 2)}"/>`; });
  L.cols.forEach((c) => { edges += `<path class="m-edge${match(c) ? "" : " dim"}" d="${curve(c.parent.x + c.parent.w, c.parent.y + c.parent.h / 2, c.x, c.y + c.h / 2)}"/>`; });
  const r = L.root;
  nodes += `<g class="m-node root" data-node="root" tabindex="0" role="button" aria-label="${esc(S.db.label)}" transform="translate(${r.x},${r.y})">
    <rect width="${r.w}" height="${r.h}" rx="9"/><use href="#i-database" x="14" y="12" width="16" height="16"/>
    <text x="38" y="${r.h / 2 + 5}">${esc(r.label)}</text></g>`;
  L.tables.forEach((n) => {
    const cls = ["m-node", "table", n.open ? "open" : "", match(n) ? "" : "dim", hit(n.t.table) ? "hit" : "", sel && sel.id === n.id ? "sel" : "", linked === n.id.toLowerCase() ? "linked" : ""].join(" ");
    nodes += `<g class="${cls}" data-node="${esc(n.id)}" tabindex="0" role="button" aria-expanded="${n.open}" aria-label="Table ${esc(n.t.table)}, ${n.t.rows} rows" transform="translate(${n.x},${n.y})">
      <rect width="${n.w}" height="${n.h}" rx="7"/><text x="14" y="${n.h / 2 + 4.5}">${esc(n.t.table)}</text>
      <text class="m-rows" x="${n.w - 30}" y="${n.h / 2 + 4}" text-anchor="end">${n.t.rows.toLocaleString()}</text>
      <g transform="translate(${n.w - 24},${n.h / 2 - 7})"><use class="m-chev" href="#i-chevron-right" width="14" height="14"${n.open ? ' transform="rotate(90 7 7)"' : ""}/></g></g>`;
  });
  L.cols.forEach((c) => {
    const cls = ["m-node", "col", match(c) ? "" : "dim", hit(c.c.name) ? "hit" : "", sel && sel.id === c.id ? "sel" : ""].join(" ");
    let x = 12, marks = "";
    if (c.c.pk) { marks += `<use class="m-pk" href="#i-key-round" x="${x}" y="${c.h / 2 - 6}" width="12" height="12"/>`; x += 18; }
    if (c.c.ref) { marks += `<use class="m-fk" href="#i-link" x="${x}" y="${c.h / 2 - 6}" width="12" height="12"/>`; x += 18; }
    const nameW = textW(c.c.name, FONT.col);
    nodes += `<g class="${cls}" data-node="${esc(c.id)}" tabindex="0" role="button" aria-label="Column ${esc(c.c.name)} in ${esc(c.parent.t.table)}${c.c.pk ? ", primary key" : ""}${c.c.ref ? `, links to ${esc(c.c.ref[0])}` : ""}" transform="translate(${c.x},${c.y})">
      <rect width="${c.w}" height="${c.h}" rx="6"/>${marks}<text x="${x}" y="${c.h / 2 + 4}">${esc(c.c.name)}</text>
      ${c.c.type ? `<text class="m-type" x="${x + nameW + 8}" y="${c.h / 2 + 4}">${esc(c.c.type)}</text>` : ""}</g>`;
  });
  $("#map-g").innerHTML = edges + nodes;
  $$("#map-g [data-node]").forEach((g) => {
    g.onclick = (e) => { if (S.mapDragged) return; e.stopPropagation(); tapNode(m, g.dataset.node); };
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); tapNode(m, g.dataset.node); } };
  });
}
const nodeById = (m, id) => (id === "root" ? m.L.root : m.L.tables.find((n) => n.id === id) || m.L.cols.find((n) => n.id === id));
function applyT(m) { const t = m.t; $("#map-g").setAttribute("transform", `translate(${t.tx.toFixed(1)},${t.ty.toFixed(1)}) scale(${t.k.toFixed(4)})`); placePop(m); }
function mapBox() { const r = $("#map").getBoundingClientRect(); return { w: r.width, h: r.height }; }
function fitMap(m, animate = true) {
  const b = mapBox(), pad = 48, top = 56;                                   // leave room for the find box
  const k = Math.max(0.2, Math.min(1.15, (b.w - pad * 2) / m.L.W, (b.h - top - pad) / m.L.H));
  moveT(m, { k, tx: (b.w - m.L.W * k) / 2, ty: top + Math.max(0, (b.h - top - pad - m.L.H * k) / 2) }, animate);
}
function moveT(m, to, animate = true) {
  if (!animate || matchMedia("(prefers-reduced-motion: reduce)").matches) { m.t = to; return applyT(m); }
  const from = { ...m.t }, t0 = performance.now(), D = 220;
  const step = (now) => { const p = Math.min(1, (now - t0) / D), e = 1 - Math.pow(1 - p, 3);
    m.t = { k: from.k + (to.k - from.k) * e, tx: from.tx + (to.tx - from.tx) * e, ty: from.ty + (to.ty - from.ty) * e }; applyT(m);
    if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function zoomAt(m, factor, px, py) {
  const t = m.t, k = Math.max(0.2, Math.min(2.5, t.k * factor));
  m.t = { k, tx: px - ((px - t.tx) * k) / t.k, ty: py - ((py - t.ty) * k) / t.k }; applyT(m);
}
function centerOn(m, n) {
  const b = mapBox(), k = Math.max(m.t.k, 0.9);
  moveT(m, { k, tx: b.w / 2 - (n.x + n.w / 2) * k, ty: b.h / 2 - (n.y + n.h / 2) * k });
}
function toggleTable(m, name) {
  const id = "t:" + name, before = nodeById(m, id);
  const y0 = before ? before.y : 0;
  m.open.has(name) ? m.open.delete(name) : m.open.add(name);
  drawMap(m);
  const after = nodeById(m, id);                                             // keep the tapped table where it was
  if (after) { m.t.ty -= (after.y - y0) * m.t.k; }
  applyT(m);
  $("#map-all").title = m.open.size === m.data.length ? "Hide all columns" : "Show all columns";
}
function tapNode(m, id) {
  const n = nodeById(m, id); if (!n) return;
  if (n.kind === "table" && !n.open) toggleTable(m, n.t.table);
  S.mapSel = nodeById(m, id); drawMap(m); applyT(m); openPop(m);
}

// the menu shown next to a tapped node
const CATEGORY = /type|status|categor|dep(t|artment)|city|country|state|gender|sex|year|level|class|genre|role|kind|group|nationality|language|region|brand|position/i;
const numeric = (ty) => /int|real|float|double|num|dec|money/i.test(ty || "");
function nodeQuestions(n) {
  if (n.kind === "root") return S.db.examples.slice(0, 4);
  if (n.kind === "table") {
    const t = n.t.table, text = n.t.columns.find((c) => !c.pk && !c.ref && CATEGORY.test(c.name)), num = n.t.columns.find((c) => !c.pk && !c.ref && numeric(c.type));
    return [`How many records are in the ${t} table?`, `Show the first 10 rows of ${t}.`,
      text ? `How many ${t} records are there for each ${text.name}?` : null, num ? `What is the average ${num.name} in ${t}?` : null].filter(Boolean);
  }
  const t = n.parent.t.table, c = n.c.name;
  if (n.c.ref) return [`For each ${n.c.ref[0]}, how many ${t} records are there?`, `Show the ${t} records with their ${n.c.ref[0]} details.`];
  if (numeric(n.c.type) && !n.c.pk) return [`What is the average ${c} in ${t}?`, `Which ${t} record has the highest ${c}?`, `What are the minimum and maximum ${c} in ${t}?`];
  return [`What are the distinct ${c} values in ${t}?`].concat(CATEGORY.test(c) ? [`How many ${t} records are there for each ${c}?`] : []);
}
function openPop(m) {
  const n = S.mapSel, pop = $("#map-pop"); if (!n) { pop.hidden = true; return; }
  let head, foot = "";
  if (n.kind === "root") head = `<div class="pop-head"><b>${esc(S.db.label)}</b><span class="mono">${m.data.length} tables</span></div><p class="pop-note">Example questions for this database:</p>`;
  else if (n.kind === "table") {
    head = `<div class="pop-head"><b>${esc(n.t.table)}</b><span class="mono">${n.t.rows.toLocaleString()} rows · ${n.t.columns.length} columns</span></div>`;
    foot = `<button class="btn quiet" data-pop="cols">${icon("list-tree", "i sm")}${m.open.has(n.t.table) ? "Hide columns" : "Show columns"}</button>`;
  } else {
    const c = n.c;
    head = `<div class="pop-head"><b class="mono">${esc(n.parent.t.table)}.${esc(c.name)}</b><span class="mono">${esc(c.type || "")}</span></div>
      ${c.pk || c.ref ? `<p class="pop-note">${c.pk ? `${icon("key-round", "i sm")}Primary key` : ""}${c.pk && c.ref ? " · " : ""}${c.ref ? `${icon("link", "i sm")}Links to ${esc(c.ref[0])}${c.ref[1] ? "." + esc(c.ref[1]) : ""}` : ""}</p>` : ""}`;
    if (c.ref) foot = `<button class="btn quiet" data-pop="goto">${icon("chevron-right", "i sm")}Go to ${esc(c.ref[0])}</button>`;
  }
  const name = n.kind === "table" ? `the ${n.t.table} table` : n.kind === "col" ? `${n.c.name} in ${n.parent.t.table}` : null;
  pop.innerHTML = head + `<div class="pop-qs">${nodeQuestions(n).map((q) => `<button data-q="${esc(q)}">${icon("message-square-text", "i sm")}<span>${esc(q)}</span></button>`).join("")}</div>
    <div class="pop-foot">${name ? `<button class="btn" data-insert="${esc(name)}">${icon("text-cursor-input", "i sm")}Use in my question</button>` : ""}${foot}</div>`;
  pop.hidden = false;
  $$("[data-q]", pop).forEach((b) => (b.onclick = () => putQuestion(b.dataset.q, true)));
  const ins = $("[data-insert]", pop); if (ins) ins.onclick = () => putQuestion(ins.dataset.insert, false);
  const cols = $("[data-pop=cols]", pop); if (cols) cols.onclick = () => { toggleTable(m, n.t.table); S.mapSel = nodeById(m, n.id); drawMap(m); applyT(m); openPop(m); };
  const go = $("[data-pop=goto]", pop);
  if (go) go.onclick = () => { const tgt = m.L.tables.find((x) => x.t.table.toLowerCase() === n.c.ref[0].toLowerCase()); if (tgt) { S.mapSel = tgt; drawMap(m); centerOn(m, tgt); openPop(m); } };
  placePop(m);
}
function placePop(m) {
  const pop = $("#map-pop"), n = S.mapSel; if (pop.hidden || !n || !m.L) return;
  const t = m.t, b = mapBox(), pw = pop.offsetWidth, ph = pop.offsetHeight;
  let x = t.tx + (n.x + n.w) * t.k + 12, y = t.ty + n.y * t.k - 6;
  if (x + pw > b.w - 12) x = t.tx + n.x * t.k - pw - 12;                  // no room on the right: open to the left
  if (x < 12) { x = Math.min(b.w - pw - 12, Math.max(12, t.tx + n.x * t.k)); y = t.ty + (n.y + n.h) * t.k + 10; }
  y = Math.max(52, Math.min(b.h - ph - 12, y));
  pop.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
}
function closePop() { $("#map-pop").hidden = true; if (S.mapSel) { S.mapSel = null; const m = MAPS[S.db.id]; if (m && m.L) { drawMap(m); applyT(m); } } }
function putQuestion(text, replace) {
  const ta = $("#question");
  if (replace || !ta.value.trim()) ta.value = text + (replace ? "" : " ");
  else { const a = ta.selectionStart ?? ta.value.length, pre = ta.value.slice(0, a), post = ta.value.slice(a);
    ta.value = pre + (pre && !/\s$/.test(pre) ? " " : "") + text + (post && !/^\s/.test(post) ? " " : "") + post; }
  autosize(); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
  const dock = $(".dock"); dock.classList.remove("flash"); void dock.offsetWidth; dock.classList.add("flash");
}
function wireMap() {
  const svg = $("#map-svg"), cur = () => MAPS[S.db.id];
  svg.addEventListener("wheel", (e) => {
    const m = cur(); if (!m || !m.L) return; e.preventDefault();
    const r = svg.getBoundingClientRect();
    if (e.ctrlKey || e.metaKey) zoomAt(m, Math.exp(-e.deltaY * 0.01), e.clientX - r.left, e.clientY - r.top);
    else { m.t.tx -= e.deltaX; m.t.ty -= e.deltaY; applyT(m); }
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; drag = { x: e.clientX, y: e.clientY, moved: false }; S.mapDragged = false; });
  window.addEventListener("pointermove", (e) => {
    if (!drag) return; const m = cur(); const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    if (!drag.moved) { drag.moved = true; svg.setPointerCapture?.(e.pointerId); svg.classList.add("grabbing"); }
    drag.x = e.clientX; drag.y = e.clientY; m.t.tx += dx; m.t.ty += dy; applyT(m);
  });
  window.addEventListener("pointerup", () => { if (!drag) return; S.mapDragged = drag.moved; drag = null; svg.classList.remove("grabbing"); setTimeout(() => (S.mapDragged = false), 0); });
  svg.addEventListener("click", (e) => { if (!S.mapDragged && !e.target.closest("[data-node]")) closePop(); });
  const b = () => { const r = mapBox(); return [r.w / 2, r.h / 2]; };
  $("#map-in").onclick = () => zoomAt(cur(), 1.25, ...b());
  $("#map-out").onclick = () => zoomAt(cur(), 0.8, ...b());
  $("#map-fit").onclick = () => fitMap(cur());
  $("#map-all").onclick = () => { const m = cur(); const all = m.open.size === m.data.length;
    m.open = new Set(all ? [] : m.data.map((t) => t.table)); closePop(); drawMap(m); fitMap(m); $("#map-all").title = all ? "Show all columns" : "Hide all columns"; };
  let ft; $("#map-find").oninput = () => { clearTimeout(ft); ft = setTimeout(() => {
    const m = cur(), q = $("#map-find").value.trim().toLowerCase();
    if (q) m.data.forEach((t) => { if (t.columns.some((c) => c.name.toLowerCase().includes(q))) m.open.add(t.table); });
    drawMap(m); applyT(m); }, 120); };
  $("#map-find").onkeydown = (e) => {
    if (e.key === "Escape") { e.currentTarget.value = ""; $("#map-find").oninput(); }
    if (e.key !== "Enter") return;
    const m = cur(), q = e.currentTarget.value.trim().toLowerCase(); if (!q) return;
    const n = m.L.tables.find((t) => t.t.table.toLowerCase().includes(q)) || m.L.cols.find((c) => c.c.name.toLowerCase().includes(q));
    if (n) { S.mapSel = n; drawMap(m); centerOn(m, n); openPop(m); }
  };
  window.addEventListener("resize", () => { const m = cur(); if (S.view === "map" && m && m.L) placePop(m); });
}

// ------------------------------------------------------------------ chart (SVG, one series)
function chartSvg(spec) {
  if (!spec) return `<div class="chart-empty">No chart for this result — it needs a column of numbers to plot.</div>`;
  const W = 640, H = 300, L = 54, B = 46, T = 14, R = 12, w = W - L - R, h = H - T - B;
  const css = getComputedStyle(document.documentElement);
  const ink3 = css.getPropertyValue("--ink-3").trim(), line = css.getPropertyValue("--line").trim(), col = css.getPropertyValue("--chart").trim();
  let pts = spec.points, marks = "", xLabels = "";
  const nice = (m) => { const e = Math.pow(10, Math.floor(Math.log10(m || 1))); return Math.ceil(m / e) * e; };
  if (spec.kind === "histogram") {
    const vals = pts.filter(isNum), lo = Math.min(...vals), hi = Math.max(...vals), k = Math.min(12, Math.max(4, Math.round(Math.sqrt(vals.length))));
    const step = (hi - lo) / k || 1; const bins = Array.from({ length: k }, (_, i) => [`${fmt(lo + i * step)}–${fmt(lo + (i + 1) * step)}`, 0]);
    vals.forEach((v) => bins[Math.min(k - 1, Math.floor((v - lo) / step))][1]++);
    pts = bins; spec = { ...spec, kind: "bar", y: "count" };
  }
  if (spec.kind === "bar") {
    const max = nice(Math.max(0, ...pts.map((p) => p[1] || 0)));
    const bw = w / pts.length, gap = Math.min(10, bw * 0.25);
    marks = pts.map((p, i) => { const v = p[1] || 0, bh = (v / max) * h, x = L + i * bw + gap / 2, y = T + h - bh;
      return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1, bw - gap).toFixed(1)}" height="${bh.toFixed(1)}" rx="3" fill="${col}" data-tip="${esc(p[0])}: ${esc(fmt(v))}"/>`; }).join("");
    const every = Math.ceil(pts.length / 10);
    xLabels = pts.map((p, i) => (i % every ? "" : `<text x="${(L + i * bw + bw / 2).toFixed(1)}" y="${T + h + 16}" text-anchor="middle" font-size="11" fill="${ink3}">${esc(String(p[0]).slice(0, 12))}</text>`)).join("");
    return svgFrame(W, H, L, T, w, h, 0, max, ink3, line, marks + xLabels, spec);
  }
  // scatter
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymax = nice(Math.max(...ys)), ymin = Math.min(0, Math.min(...ys));
  const X = (v) => L + ((v - xmin) / ((xmax - xmin) || 1)) * w, Y = (v) => T + h - ((v - ymin) / ((ymax - ymin) || 1)) * h;
  marks = pts.map((p) => `<circle cx="${X(p[0]).toFixed(1)}" cy="${Y(p[1]).toFixed(1)}" r="5" fill="${col}" stroke="var(--bg-pane)" stroke-width="2" data-tip="${esc(fmt(p[0]))}, ${esc(fmt(p[1]))}"/>`).join("");
  xLabels = [xmin, (xmin + xmax) / 2, xmax].map((v) => `<text x="${X(v).toFixed(1)}" y="${T + h + 16}" text-anchor="middle" font-size="11" fill="${ink3}">${esc(fmt(v))}</text>`).join("");
  return svgFrame(W, H, L, T, w, h, ymin, ymax, ink3, line, marks + xLabels, spec);
}
function svgFrame(W, H, L, T, w, h, lo, hi, ink3, line, inner, spec) {
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => { const v = lo + f * (hi - lo), y = T + h - f * h;
    return `<line x1="${L}" x2="${L + w}" y1="${y}" y2="${y}" stroke="${line}" stroke-width="1"/><text x="${L - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="${ink3}">${esc(fmt(v))}</text>`; }).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(spec.y || "")} by ${esc(spec.x)}" font-family="IBM Plex Mono, monospace">${ticks}${inner}
    <text x="${L + w / 2}" y="${H - 6}" text-anchor="middle" font-size="12" font-family="Montserrat, sans-serif" fill="${ink3}">${esc(spec.x)}</text>
    <text x="14" y="${T + h / 2}" text-anchor="middle" font-size="12" font-family="Montserrat, sans-serif" fill="${ink3}" transform="rotate(-90 14 ${T + h / 2})">${esc(spec.y || "")}</text></svg><div class="tip" hidden></div>`;
}

// ------------------------------------------------------------------ turn wiring
const turnItem = (el) => S.chat.turns.find((x) => x.id === el.dataset.hid);
function rerenderTurn(el) { const it = turnItem(el); el.innerHTML = turnHtml(it); wireTurn(el); }
function wireTurn(el) {
  const it = turnItem(el), t = turnState(it.id);
  $$("[data-tab]", el).forEach((b) => (b.onclick = () => { t.tab = b.dataset.tab; $$("[data-tab]", el).forEach((x) => x.setAttribute("aria-selected", x === b)); $(".tab-body", el).innerHTML = tabBody(it, t, t.tab); wireTab(el, it, t); }));
  $$("[data-reading]", el).forEach((b) => (b.onclick = async () => {
    t.reading = +b.dataset.reading; t.edited = null;
    t.readingData = await api.interpretation(it.id, t.reading);
    rerenderTurn(el);
  }));
  $$("[data-clarify]", el).forEach((b) => (b.onclick = () => submitQuestion(clarifiedQuestion(it.question, b.dataset.clarify))));
  const guess = $("[data-guess]", el); if (guess) guess.onclick = () => { t.guess = true; rerenderTurn(el); };
  const back = $("[data-unclear-back]", el); if (back) back.onclick = () => { t.guess = false; rerenderTurn(el); };
  $("[data-act=copy]", el).onclick = (e) => copyText(selectedSql(it, t).sql, e.currentTarget, true);
  $("[data-act=reask]", el).onclick = () => submitQuestion(it.question);
  $("[data-act=delete]", el).onclick = async () => {
    await api.history_delete(it.id);
    const left = S.chat.turns.length - 1;
    await loadChats(); refreshCounts();
    if (left) openChat(S.chat.id, "keep"); else newChat();
  };
  wireTab(el, it, t);
}
function wireTab(el, it, t) {
  const ed = $("[data-sql=edit]", el);
  if (ed) {
    const original = ed.value, run = $("[data-sql=run]", el);
    ed.oninput = () => { run.disabled = ed.value.trim() === original.trim(); };
    run.onclick = async () => {
      $("[data-sql=msg]", el).textContent = "";
      const r = await api.run_sql(S.db.id, ed.value);
      if (r.error) { $("[data-sql=msg]", el).textContent = r.error; return; }
      t.edited = r; t.tab = "table"; rerenderTurn(el);
    };
    $("[data-sql=copy]", el).onclick = (e) => copyText(ed.value, e.currentTarget);
  }
  $$(".chart", el).forEach((ch) => {
    const tip = $(".tip", ch); if (!tip) return;
    ch.onmousemove = (e) => { const x = e.target.closest("[data-tip]"); if (!x) { tip.hidden = true; return; }
      const r = ch.getBoundingClientRect(); tip.hidden = false; tip.textContent = x.dataset.tip; tip.style.left = e.clientX - r.left + 12 + "px"; tip.style.top = e.clientY - r.top - 30 + "px"; };
    ch.onmouseleave = () => (tip.hidden = true);
  });
}
function copyText(text, btn, iconOnly = false) {
  navigator.clipboard.writeText(text).then(() => { const o = btn.innerHTML; btn.innerHTML = icon("check", "i sm") + (iconOnly ? "" : "Copied"); setTimeout(() => (btn.innerHTML = o), 1400); });
}
function renameChat() {
  const box = $("#chat-title"), cur = S.chat.title;
  box.innerHTML = `<input class="input rename" value="${esc(cur)}" aria-label="Chat name">`;
  const inp = $("input", box); inp.focus(); inp.select();
  const done = async (save) => {
    if (save && inp.value.trim() && inp.value.trim() !== cur) { await api.chat_rename(S.chat.id, inp.value); S.chat.title = inp.value.trim(); loadChats(); }
    renderThread("keep");
  };
  inp.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); done(true); } if (e.key === "Escape") done(false); };
  inp.onblur = () => done(true);
}
async function deleteChat() {
  const n = S.chat.turns.length;
  if (!confirm(`Delete this chat and its ${n} question${n === 1 ? "" : "s"}? This can't be undone.`)) return;
  await api.chat_delete(S.chat.id); await loadChats(); refreshCounts(); newChat();
}

// ------------------------------------------------------------------ app wiring
function wireApp() {
  $("#compose").onsubmit = (e) => { e.preventDefault(); submitQuestion(); };
  $("#question").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submitQuestion(); } });
  $("#question").addEventListener("input", autosize);
  let t; $("#search").oninput = () => { clearTimeout(t); t = setTimeout(() => loadChats(), 180); };
  $$("#layout-seg [data-layout]").forEach((b) => (b.onclick = () => { S.layout = b.dataset.layout; Object.values(S.T).forEach((x) => (x.tab = null)); api.settings_set({ layout: S.layout }); renderThread("keep"); }));
  $("#new-chat").onclick = () => { newChat(); setView("chat"); };
  $("#toggle-sidebar").onclick = toggleSidebar;
  $("#model-pill").onclick = (e) => { e.preventDefault(); openModelMenu(); };
  $("#rename-chat").onclick = renameChat;
  $("#delete-chat").onclick = deleteChat;
  $("#schema-btn").onclick = () => setView("map");
  $$("#view-seg [data-view]").forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  wireMap();
  $("#add-db").onclick = (e) => toggleMenu($("#add-menu"), e.currentTarget);
  $("#m-file").onclick = addFile;
  $("#m-server").onclick = () => { $("#add-menu").hidden = true; openConnect(); };
  $("#open-settings").onclick = openSettings;
  $$("dialog [data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));
  document.addEventListener("click", (e) => { if (!e.target.closest(".menu") && !e.target.closest("#add-db") && !e.target.closest("#model-pill")) { $$(".menu").forEach((m) => (m.hidden = true)); $("#model-pill").setAttribute("aria-expanded", "false"); } });
  document.addEventListener("keydown", (e) => {
    const m = S.os === "mac" ? e.metaKey : e.ctrlKey;
    if (m && e.key.toLowerCase() === "n") { e.preventDefault(); newChat(); setView("chat"); }
    if (e.key.toLowerCase() === "s" && (S.os === "mac" ? e.metaKey && e.ctrlKey : e.ctrlKey && e.shiftKey)) { e.preventDefault(); toggleSidebar(); }
    if (e.key === "Escape" && !$("#model-menu").hidden) closeModelMenu();
    if (e.key === "Escape" && S.view === "map" && !$("#map-pop").hidden) closePop();
    if (m && e.key.toLowerCase() === "f") { e.preventDefault(); $("#search").focus(); }
    if (m && e.key === ",") { e.preventDefault(); openSettings(); }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && document.activeElement.closest("#rows")) {
      e.preventDefault(); const list = $$("#rows [data-id]"); const i = list.indexOf(document.activeElement.closest("[data-id]"));
      const n = list[Math.max(0, Math.min(list.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))]; if (n) { n.focus(); n.click(); }
    }
  });
  $("#c-kind").onchange = () => ($("#c-port").value = $("#c-kind").value.startsWith("Postgre") ? "5432" : "3306");
}
function toggleMenu(menu, anchor) {
  const r = anchor.getBoundingClientRect(); menu.hidden = !menu.hidden;
  menu.style.left = r.left + "px"; menu.style.top = r.top - 8 - menu.offsetHeight + "px";
}
function dbMenu(e, id) {
  const db = S.dbs.find((d) => d.id === id); if (!db || (!db.live && db.group !== "Files")) return;
  let m = $("#db-menu"); if (!m) { m = document.createElement("div"); m.className = "menu"; m.id = "db-menu"; document.body.append(m); }
  m.innerHTML = `<button id="dm-go">${icon(db.live ? "circle-x" : "trash-2", "i sm")}${db.live ? "Disconnect" : "Remove from QueryGenie"}</button>`;
  m.hidden = false; m.style.left = e.clientX + "px"; m.style.top = e.clientY + "px";
  $("#dm-go").onclick = () => { m.hidden = true; removeDb(id); };
}
async function removeDb(id) {
  const db = S.dbs.find((d) => d.id === id); if (!db) return;
  await (db.live ? api.disconnect(id) : api.remove_file(id));
  S.dbs = await api.databases(); renderSources(); if (S.db.id === id) selectDb(S.dbs[0].id);
}
async function addFile() {
  $("#add-menu").hidden = true;
  const r = await api.add_sqlite();
  if (r.cancelled) return;
  if (r.error) { alert(r.error); return; }
  S.dbs = await api.databases(); renderSources(); selectDb(r.id);
}
function openConnect() {
  $("#c-msg").textContent = ""; $("#c-msg").className = "form-msg"; $("#c-pass").value = "";
  const d = $("#dlg-connect"); d.showModal(); $("#c-db").focus();
  $("#connect-form").onsubmit = async (e) => {
    if (e.submitter && e.submitter.value === "cancel") return;
    e.preventDefault();
    const go = $("#c-go"); go.disabled = true; $("#c-msg").className = "form-msg"; $("#c-msg").textContent = "Connecting and reading the schema…";
    const r = await api.connect($("#c-kind").value, $("#c-host").value, $("#c-port").value, $("#c-db").value, $("#c-user").value, $("#c-pass").value);
    go.disabled = false; $("#c-pass").value = "";
    if (r.error) { $("#c-msg").className = "form-msg bad"; $("#c-msg").textContent = "Couldn't connect: " + r.error; return; }
    d.close(); S.dbs = await api.databases(); renderSources(); selectDb(r.id);
  };
}
async function openSettings() {
  const d = $("#dlg-settings"); const ops = S.boot.operating_points || {};
  const modes = [["answer_all", "Answer everything", "answer_all"], ["balanced", "Balanced — recommended, the tested setting", "calibrated_90"],
                 ["strict", "Strict — only when 3 of 4 queries agree", "min_3_of_4"], ["very_strict", "Very strict — only when all 4 agree", "all_4"]];
  $("#mode-opts").innerHTML = modes.map(([k, label, op]) => { const o = ops[op];
    return `<label class="opt"><input type="radio" name="mode" value="${k}" ${S.mode === k ? "checked" : ""}><div><b>${label}</b>
      <span>${o ? `Answers about ${Math.round(o.coverage * 100)}% of questions; ${(o.accuracy * 100).toFixed(1)}% of those answers were correct.` : ""}</span></div></label>`; }).join("");
  $$("#mode-opts input").forEach((i) => (i.onchange = () => { S.mode = i.value; api.settings_set({ mode: i.value }); }));
  S.boot = await api.boot(); S.provider = null; renderModelPanel();
  const st = await api.storage();
  $("#storage-kv").innerHTML = `<dt>App data</dt><dd>${esc(st.app_dir)}</dd><dt>Models</dt><dd>${esc(st.models_dir)}</dd><dt>Databases</dt><dd>${esc(st.data_dir)}</dd>`;
  $("#clear-history").onclick = async () => {
    if (!confirm("Delete every chat on every database? This can't be undone.")) return;
    await api.history_clear(); await loadChats(); refreshCounts(); newChat(); $("#clear-history").textContent = "All chats deleted";
  };
  $$("[data-set]").forEach((b) => (b.onclick = () => { $$("[data-set]").forEach((x) => x.setAttribute("aria-pressed", x === b)); $$("[data-setpanel]").forEach((p) => (p.hidden = p.dataset.setpanel !== b.dataset.set)); }));
  d.showModal();
}
// ------------------------------------------------------------------ collapsible sidebar
const sidebarKey = () => (S.os === "mac" ? "⌃⌘S" : "Ctrl+Shift+S");
function setSidebar(collapsed) {
  document.documentElement.classList.toggle("sidebar-collapsed", collapsed);
  const b = $("#toggle-sidebar"), what = collapsed ? "Show sidebar" : "Hide sidebar";
  b.title = `${what} (${sidebarKey()})`; b.setAttribute("aria-label", what); b.setAttribute("aria-expanded", String(!collapsed));
  try { localStorage.setItem("qg.sidebar", collapsed ? "hidden" : "shown"); } catch (e) { /* convenience only */ }
}
const toggleSidebar = () => setSidebar(!document.documentElement.classList.contains("sidebar-collapsed"));

// ------------------------------------------------------------------ model picker in the question box
const EFFORT_NAME = { low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Max", on: "Thinking on", off: "Thinking off" };
function shortName(label) { const l = String(label || ""); const last = l.includes("/") ? l.split("/").pop() : l; return last.length > 30 ? last.slice(0, 29) + "…" : last; }
function renderModelPill() {
  const e = (S.boot && S.boot.engine) || {};
  $("#model-pill .mp-name").textContent = shortName(e.label);
  $("#model-pill .mp-effort").textContent = e.effort_levels ? (EFFORT_NAME[e.effort] || "Default") : "";
  $("#model-pill").title = `${e.label}${e.cloud ? " · cloud" : " · on this computer"}${e.calibrated ? " · accuracy measured" : ""} — choose the model`;
}
async function openModelMenu() {
  const m = $("#model-menu"), pill = $("#model-pill");
  if (!m.hidden) return closeModelMenu();
  m.innerHTML = `<div class="sk" style="width:60%;margin:10px"></div>`; m.hidden = false; placeModelMenu();
  pill.setAttribute("aria-expanded", "true");
  const q = await api.models_quick(), cur = q.current;
  await loadProviderIcons();
  const isCur = (o) => (o.evaluated ? cur.kind === "evaluated" && q.current_model === o.evaluated
                                    : cur.kind === o.spec.kind && cur.model === o.spec.model && (cur.base_url || "") === (o.spec.base_url || ""));
  const flat = [];
  let html = "";
  if (cur.effort_levels) {
    html += `<h4>Effort</h4>` + [null, ...cur.effort_levels].map((lvl) => `
      <button role="menuitemradio" aria-checked="${(cur.effort || null) === lvl}" data-effort="${lvl ?? ""}"><span class="mm-l"><span>${lvl ? EFFORT_NAME[lvl] : "Default"}</span></span>${(cur.effort || null) === lvl ? icon("check", "i sm") : ""}</button>`).join("");
    html += `<p class="mm-note">Higher effort thinks longer — slower, and costlier on paid services. Models that can't reason reject it.</p><hr>`;
  }
  html += q.groups.map((g) => `<h4 class="mm-group">${picon(g.icon, "pi sm")}${esc(g.name)}${g.cloud ? " · cloud" : ""}</h4>` + g.models.map((o) => {
    const i = flat.push({ ...o, cloud: g.cloud }) - 1;
    return `<button role="menuitemradio" aria-checked="${isCur(o)}" data-opt="${i}" title="${esc(o.label)}"><span class="mm-l"><span>${esc(shortName(o.label))}</span>
      ${o.evaluated === "codes-1b-spider" ? `<span class="mm-sub">Accuracy measured on Spider</span>` : ""}</span>${isCur(o) ? icon("check", "i sm") : ""}</button>`;
  }).join("")).join("");
  if (!cur.effort_levels && (cur.kind === "evaluated" || ["mlx", "gguf", "hf"].includes(cur.kind))) {
    html += `<hr><p class="mm-note">CodeS models have no effort setting: every question gets four candidate queries${cur.calibrated ? " — the evaluated setup" : ""}.</p>`;
  }
  html += `<hr><button data-more>${icon("settings", "i sm")}<span class="mm-l"><span>More models…</span><span class="mm-sub">Switch models on or off, add cloud services</span></span></button>`;
  m.innerHTML = html; placeModelMenu();
  $$("[data-opt]", m).forEach((b) => (b.onclick = async () => {
    const o = flat[+b.dataset.opt]; closeModelMenu();
    if (o.cloud && !confirm(`Use ${o.label}?\n\nFor every question, the database's schema, a few example values and the question are sent to this service. Result rows stay on this computer.`)) return;
    if (o.evaluated) await api.settings_set({ model: o.evaluated });
    const r = await api.engine_set(o.evaluated ? null : o.spec); if (r.error) return alert(r.error);
    S.boot = await api.boot(); renderModelPill();
  }));
  $$("[data-effort]", m).forEach((b) => (b.onclick = async () => {
    closeModelMenu(); const r = await api.engine_effort(b.dataset.effort || null); if (r.error) return alert(r.error);
    S.boot = await api.boot(); renderModelPill();
  }));
  $("[data-more]", m).onclick = async () => { closeModelMenu(); S.provider = null; await openSettings(); $("[data-set=model]").click(); };
}
function placeModelMenu() {
  const m = $("#model-menu"), r = $("#model-pill").getBoundingClientRect();
  m.style.left = Math.max(12, Math.min(window.innerWidth - m.offsetWidth - 12, r.right - m.offsetWidth)) + "px";
  m.style.top = Math.max(12, r.top - m.offsetHeight - 8) + "px";
}
function closeModelMenu() { $("#model-menu").hidden = true; $("#model-pill").setAttribute("aria-expanded", "false"); }

// ------------------------------------------------------------------ settings: providers and their models
// Settings -> Model is a grid of provider tiles; a tile opens that provider's page, where models are
// switched on or off for the picker under the question box, chosen, or added by name. API keys go
// straight to the OS keychain through api.key_save and are never read back.
const PICON = {};
async function loadProviderIcons() {
  const keys = ["ollama", "anthropic", "openai", "gemini", "xai", "deepseek", "mistral", "groq", "openrouter", "together", "hf", "compat"];
  await Promise.all(keys.filter((k) => !(k in PICON)).map(async (k) => {
    try { PICON[k] = await (await fetch(`providers/${k}.svg`)).text(); } catch (e) { PICON[k] = ""; }
  }));
}
function picon(key, cls = "pi") {
  if (key === "brand") return `<span class="${cls}"><img src="brand/mark.png" alt=""></span>`;
  return `<span class="${cls}" aria-hidden="true">${PICON[key] || icon("cpu")}</span>`;
}
function engineLine(cur) {
  const cal = cur.calibrated ? `${icon("circle-check", "i sm")}Accuracy measured on Spider` : `${icon("info", "i sm")}Confidence not calibrated for this model`;
  return `<div class="engine-now"><div><span class="lbl-sm">Answering with</span><b>${esc(cur.label)}</b>
    <span class="where">${cur.cloud ? `${esc(cur.where)} · sends the schema to the provider` : `Runs on this computer${cur.where && cur.where !== "this computer" ? " · " + esc(cur.where) : ""}`}</span></div>
    <span class="cal ${cur.calibrated ? "ok" : ""}">${cal}</span></div>`;
}
async function renderModelPanel() {
  const box = $("#model-panel");
  if (S.provider) return renderProvider(S.provider);
  box.innerHTML = `<div class="sk" style="width:70%"></div>`;
  await loadProviderIcons();
  const o = await api.providers_overview();
  const tile = (t) => {
    const status = (t.current ? "In use · " : "") + t.status;
    return `<button class="ptile${t.current ? " cur" : ""}" data-provider="${t.key}" title="${esc(t.detail || t.name)} — ${esc(status)}">
      ${picon(t.icon)}<span class="pt-text"><b>${esc(t.detail || t.name)}</b><span>${esc(status)}</span></span></button>`;
  };
  box.innerHTML = engineLine(o.current) + `
    <section class="mgroup"><h3>On this computer</h3><div class="ptiles">${o.tiles.filter((t) => t.group === "local").map(tile).join("")}</div></section>
    <section class="mgroup"><h3>Cloud services</h3>
      <p class="gnote">These receive your database's schema, a few example values and the question — never result rows — and each question costs four requests on your account.</p>
      <div class="ptiles">${o.tiles.filter((t) => t.group === "cloud").map(tile).join("")}</div></section>`;
  $$("[data-provider]", box).forEach((b) => (b.onclick = () => { S.provider = b.dataset.provider; renderProvider(S.provider); }));
}
const PROVIDER_INFO = {
  evaluated: ["Evaluated model", "brand", "The CodeS model whose accuracy was measured on Spider. It runs on this computer."],
  legacy: ["Earlier prototype", "brand", "CodeS models from the Gradio prototype. Same prompt and confidence check; their accuracy was not measured in this app."],
  ollama: ["Ollama", "ollama", "Runs any model you have pulled in Ollama, on this computer. Pull more in Terminal, e.g. ollama pull qwen2.5-coder."],
  hf: ["Your CodeS model", "hf", "A CodeS-format model from Hugging Face or a folder on this computer — for example a CodeS fine-tune of your own."],
  compat: ["OpenAI-compatible server", "compat", "LM Studio, vLLM, a llama.cpp server, or any hosted endpoint with an OpenAI-style API."],
};
async function renderProvider(key) {
  const box = $("#model-panel");
  box.innerHTML = `<div class="sk" style="width:60%"></div>`;
  await loadProviderIcons();
  const [o, d] = await Promise.all([api.providers_overview(), api.provider_detail(key)]);
  const t = o.tiles.find((x) => x.key === key);
  const [name, ic, blurb] = PROVIDER_INFO[key] || [t.detail || t.name, t.icon, "A cloud service. It receives the schema, a few example values and the question for every question; result rows stay on this computer."];
  let html = `<div class="phead"><button class="btn quiet icon" data-back title="All providers" aria-label="All providers">${icon("chevron-right", "i flip")}</button>
      ${picon(ic, "pi lg")}<div><h3>${esc(name)}</h3><p>${esc(blurb)}</p></div></div>`;
  if (d.cloud) {
    html += `<div class="prow"><div><b>API key</b><span>${d.key_saved ? `${icon("lock", "i sm")}Saved in your ${S.os === "mac" ? "Keychain" : "Credential Manager"}` : "Not added"}</span></div>
      <div class="pkey"><input class="input" type="password" autocomplete="off" placeholder="${d.key_saved ? "Paste a new key to replace it" : `Paste your ${esc(name)} API key`}" aria-label="API key">
      <button class="btn primary" data-key-save>Save</button>${d.key_saved ? `<button class="btn quiet" data-key-remove>Remove</button>` : ""}</div></div>`;
  }
  if (key === "compat") {
    html += `<div class="prow"><div><b>Server address</b><span>The OpenAI-style base address, ending in /v1</span></div>
      <div class="pkey"><input class="input" id="p-url" value="${esc(d.base_url || "")}" placeholder="http://localhost:1234/v1" aria-label="Server address"><button class="btn" data-url-save>Save</button></div></div>
      <div class="prow"><div><b>API key</b><span>${d.key_saved ? `${icon("lock", "i sm")}Saved` : "Only if the server needs one"}</span></div>
      <div class="pkey"><input class="input" type="password" autocomplete="off" placeholder="Optional" aria-label="API key"><button class="btn" data-key-save>Save</button>${d.key_saved ? `<button class="btn quiet" data-key-remove>Remove</button>` : ""}</div></div>`;
  }
  if (d.error) html += `<p class="form-msg bad">${esc(d.error)}</p>`;
  const rows = d.models.map((m, i) => `
    <div class="mrow${m.available ? "" : " off"}${m.current ? " cur" : ""}">
      <div class="mr-l"><b title="${esc(m.label)}">${esc(m.label)}</b>${m.note ? `<span>${esc(m.note)}</span>` : ""}</div>
      ${m.evaluated && !m.available ? `<button class="btn" data-dl="${m.evaluated}">${icon("download", "i sm")}Download${m.size_gb ? ` · ${m.size_gb} GB` : ""}</button>`
        : m.current ? `<span class="pt-badge cur">${icon("check", "i sm")}In use</span>`
        : `<button class="btn" data-use="${i}" ${m.available ? "" : "disabled"}>Use</button>`}
      ${key === "evaluated" ? "" : `<label class="switch" title="${m.on ? "Shown" : "Hidden"} in the model picker"><input type="checkbox" role="switch" data-toggle="${i}" ${m.on ? "checked" : ""} ${m.available ? "" : "disabled"} aria-label="Show ${esc(m.label)} in the model picker"><span></span></label>`}
      ${m.custom ? `<button class="btn quiet icon" data-remove-model="${i}" title="Remove" aria-label="Remove ${esc(m.label)}">${icon("x", "i sm")}</button>` : ""}
    </div>`).join("");
  const empty = d.cloud && !d.key_saved ? "Add your API key to see this service's models." : key === "compat" && !d.base_url ? "Save the server's address to see its models." : "No models yet.";
  html += `<div class="mlist"><div class="ml-head"><span>Model</span><span>In picker</span></div>${rows || `<p class="gnote" style="padding:10px 12px">${empty}</p>`}</div>`;
  if (d.can_add) html += `<div class="padd"><input class="input" id="p-add" placeholder="${key === "hf" ? "e.g. seeklhy/codes-7b-spider, or /path/to/model" : "Add a model by name"}" aria-label="Model name"><button class="btn" data-add>${icon("plus", "i sm")}Add</button></div>`;
  box.innerHTML = html;
  const msg = (text) => { let p = $(".form-msg.bad", box); if (!p) { p = document.createElement("p"); p.className = "form-msg bad"; $(".phead", box).after(p); } p.textContent = text; };
  $("[data-back]", box).onclick = () => { S.provider = null; renderModelPanel(); };
  $$("[data-use]", box).forEach((b) => (b.onclick = () => useEngine(d.models[+b.dataset.use], d)));
  $$("[data-toggle]", box).forEach((c) => (c.onchange = async () => { await api.provider_toggle(key, d.models[+c.dataset.toggle].id, c.checked); }));
  $$("[data-remove-model]", box).forEach((b) => (b.onclick = async () => { await api.provider_remove_model(key, d.models[+b.dataset.removeModel].id); renderProvider(key); }));
  $$("[data-dl]", box).forEach((b) => (b.onclick = async () => { await api.setup_start(b.dataset.dl, false); pollModel(); }));
  const add = $("[data-add]", box);
  if (add) { const go = async () => { const v = $("#p-add").value.trim(); if (!v) return; const r = await api.provider_add_model(key, v); if (r.error) return msg(r.error); renderProvider(key); };
    add.onclick = go; $("#p-add").onkeydown = (e) => { if (e.key === "Enter") go(); }; }
  const save = $("[data-key-save]", box);
  if (save) save.onclick = async () => { const inp = save.previousElementSibling; if (!inp.value.trim()) return;
    const r = await api.key_save(key, inp.value); inp.value = ""; if (r.error) return msg(r.error); renderProvider(key); };
  const rm = $("[data-key-remove]", box); if (rm) rm.onclick = async () => { await api.key_save(key, null); renderProvider(key); };
  const url = $("[data-url-save]", box); if (url) url.onclick = async () => { await api.provider_set_url(key, $("#p-url").value); renderProvider(key); };
}
async function useEngine(m, d) {
  if (d && d.cloud && !confirm(`Use ${m.label}?\n\nFor every question, the database's schema, a few example values and the question are sent to this service. Result rows stay on this computer.`)) return;
  if (m.evaluated) await api.settings_set({ model: m.evaluated });
  const r = await api.engine_set(m.evaluated ? null : m.spec);
  if (r.error) { alert(r.error); return; }
  S.boot = await api.boot(); renderModelPill();
  if (S.provider) renderProvider(S.provider); else renderModelPanel();
}
async function pollModel() {
  const s = await api.setup_status(); const el = $("#model-dl");
  el.className = s.error ? "form-msg bad" : "form-msg";
  el.textContent = s.error ? s.error : s.total_bytes ? `${s.message}: ${(s.done_bytes / 1e9).toFixed(2)} of ${(s.total_bytes / 1e9).toFixed(2)} GB` : s.message;
  if (!s.finished && !s.error) setTimeout(pollModel, 700); else if (s.finished) renderModelPanel();
}
