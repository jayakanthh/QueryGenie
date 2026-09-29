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
  $("#db-title").textContent = S.db.label;
  $("#db-meta").textContent = S.db.live ? "Live · read-only" : S.db.group === "Files" ? "SQLite file" : "Sample";
  $("#search").value = "";
  await loadChats();
  const last = localStorage.getItem("qg.chat." + id);
  if (last && S.chats.some((c) => c.id === last)) openChat(last); else newChat();
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
  $$("#rows [data-id]").forEach((b) => (b.onclick = () => openChat(b.dataset.id)));
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
  const c = S.chat, working = S.working && S.working.chat === (c ? c.id : null) && S.working.db === S.db.id;
  $("#chat-title").innerHTML = c ? `<span class="t selectable">${esc(c.title)}</span><span class="n">${c.turns.length} question${c.turns.length === 1 ? "" : "s"}</span>`
                                 : `<span class="t">New chat</span><span class="n">${esc(S.db.label)}</span>`;
  $("#rename-chat").hidden = $("#delete-chat").hidden = !c;
  $("#layout-seg").hidden = !c;
  $$("#layout-seg [data-layout]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.layout === S.layout));
  $("#question").placeholder = c ? "Ask another question…" : S.db.examples[0] ? `e.g. ${S.db.examples[0]}` : `Ask about ${S.db.label}…`;
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
    <div class="sub">${it.created ? `<span>${when(it.created)}</span>` : ""}<span>${modeName(it.mode)}</span></div></div>`;
  const top = it.answered ? verdictHtml(it) : unsureHtml(it, t);
  let body;
  if (!it.answered && t.reading == null) body = "";
  else if (S.layout === "confidence") body = `<div class="stack">${candidatesHtml(it)}${tabsHtml(it, t, ["table", "chart", "sql"])}</div>`;
  else if (S.layout === "split") body = `<div class="split"><div>${tabsHtml(it, t, ["table", "chart"])}</div><div class="stack">${sqlHtml(it, t)}${candidatesHtml(it)}</div></div>`;
  else body = tabsHtml(it, t, ["table", "chart", "sql", "candidates"]);
  const live = it.live ? `<p class="note">${icon("info")}Connected to ${esc(it.backend)}: the query was translated and run in a read-only transaction. The confidence percentages were measured on SQLite and are not yet calibrated for ${esc(it.backend)}.</p>` : "";
  return head + top + body + live;
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
  $("#new-chat").onclick = newChat;
  $("#rename-chat").onclick = renameChat;
  $("#delete-chat").onclick = deleteChat;
  $("#schema-btn").onclick = openSchema;
  $("#add-db").onclick = (e) => toggleMenu($("#add-menu"), e.currentTarget);
  $("#m-file").onclick = addFile;
  $("#m-server").onclick = () => { $("#add-menu").hidden = true; openConnect(); };
  $("#open-settings").onclick = openSettings;
  $$("dialog [data-close]").forEach((b) => (b.onclick = () => b.closest("dialog").close()));
  document.addEventListener("click", (e) => { if (!e.target.closest(".menu") && !e.target.closest("#add-db")) $$(".menu").forEach((m) => (m.hidden = true)); });
  document.addEventListener("keydown", (e) => {
    const m = S.os === "mac" ? e.metaKey : e.ctrlKey;
    if (m && e.key.toLowerCase() === "n") { e.preventDefault(); newChat(); }
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
async function openSchema() {
  $("#schema-title").textContent = S.db.label;
  $("#schema-list").innerHTML = '<div class="sk" style="width:60%"></div>';
  $("#dlg-schema").showModal();
  const tables = await api.schema(S.db.id);
  $("#schema-list").innerHTML = tables.map((t) => `<div><b>${esc(t.table)}</b> <span style="color:var(--ink-3);font-size:var(--fs-xs)" class="mono">${t.rows.toLocaleString()} rows</span>
    <div class="mono" style="color:var(--ink-2);font-size:var(--fs-sm);margin-top:3px">${t.columns.map(esc).join(", ")}</div></div>`).join("");
}
async function openSettings() {
  const d = $("#dlg-settings"); const ops = S.boot.operating_points || {};
  const modes = [["answer_all", "Answer everything", "answer_all"], ["balanced", "Balanced — recommended, the tested setting", "calibrated_90"],
                 ["strict", "Strict — only when 3 of 4 queries agree", "min_3_of_4"], ["very_strict", "Very strict — only when all 4 agree", "all_4"]];
  $("#mode-opts").innerHTML = modes.map(([k, label, op]) => { const o = ops[op];
    return `<label class="opt"><input type="radio" name="mode" value="${k}" ${S.mode === k ? "checked" : ""}><div><b>${label}</b>
      <span>${o ? `Answers about ${Math.round(o.coverage * 100)}% of questions; ${(o.accuracy * 100).toFixed(1)}% of those answers were correct.` : ""}</span></div></label>`; }).join("");
  $$("#mode-opts input").forEach((i) => (i.onchange = () => { S.mode = i.value; api.settings_set({ mode: i.value }); }));
  const s = await api.settings_get(); S.boot = await api.boot();
  $("#model-opts").innerHTML = S.boot.models.map((m) => `<label class="opt"><input type="radio" name="model" value="${m.key}" ${s.model === m.key ? "checked" : ""} ${m.installed ? "" : "disabled"}><div>
      <b>${m.label} · ${m.size_gb} GB</b><span>${m.installed ? "Installed" : `Not installed — <button class="btn quiet" style="height:20px;padding:0 4px" data-dl="${m.key}">Download</button>`}</span></div></label>`).join("");
  $$("#model-opts input").forEach((i) => (i.onchange = () => api.settings_set({ model: i.value })));
  $$("#model-opts [data-dl]").forEach((b) => (b.onclick = async (e) => { e.preventDefault(); await api.setup_start(b.dataset.dl, false); pollModel(); }));
  const st = await api.storage();
  $("#storage-kv").innerHTML = `<dt>App data</dt><dd>${esc(st.app_dir)}</dd><dt>Models</dt><dd>${esc(st.models_dir)}</dd><dt>Databases</dt><dd>${esc(st.data_dir)}</dd>`;
  $("#clear-history").onclick = async () => {
    if (!confirm("Delete every chat on every database? This can't be undone.")) return;
    await api.history_clear(); await loadChats(); refreshCounts(); newChat(); $("#clear-history").textContent = "All chats deleted";
  };
  $$("[data-set]").forEach((b) => (b.onclick = () => { $$("[data-set]").forEach((x) => x.setAttribute("aria-pressed", x === b)); $$("[data-setpanel]").forEach((p) => (p.hidden = p.dataset.setpanel !== b.dataset.set)); }));
  d.showModal();
}
async function pollModel() {
  const s = await api.setup_status(); const el = $("#model-dl");
  el.className = s.error ? "form-msg bad" : "form-msg";
  el.textContent = s.error ? s.error : s.total_bytes ? `${s.message}: ${(s.done_bytes / 1e9).toFixed(2)} of ${(s.total_bytes / 1e9).toFixed(2)} GB` : s.message;
  if (!s.finished && !s.error) setTimeout(pollModel, 700); else if (s.finished) openSettings();
}
