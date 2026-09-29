"""
The bridge between the desktop interface (desktop/ui) and the QueryGenie engine (src/).

pywebview exposes every public method of `Api` to JavaScript as window.pywebview.api.<name>(),
returning a promise. Everything returned here is plain JSON.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import sqlite3
import sys
import threading
import uuid

import setup_tasks as st

HISTORY_DB = os.path.join(st.app_dir(), "history.sqlite")
SETTINGS = os.path.join(st.app_dir(), "settings.json")
DEFAULT_SETTINGS = {"layout": "answer", "mode": "balanced", "model": "codes-1b-spider"}
MAX_ROWS = 200


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v and abs(v) != float("inf") else str(v)
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray)):
        return v.decode(errors="replace")
    if isinstance(v, (dt.date, dt.datetime, dt.time)):
        return v.isoformat()
    return str(v)


def _rows(rows):
    return [[_jsonable(c) for c in r] for r in rows[:MAX_ROWS]]


def chart_spec(columns, rows):
    """The same choice rules as src/charts.py (bar / line / scatter / histogram), as data for the UI."""
    if not columns or not rows:
        return None
    rows = rows[:50]

    def numeric(i):
        vals = [r[i] for r in rows if r[i] is not None]
        return bool(vals) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)

    num = [i for i in range(len(columns)) if numeric(i)]
    cat = [i for i in range(len(columns)) if i not in num]
    if cat and num:
        return {"kind": "bar", "x": columns[cat[0]], "y": columns[num[0]],
                "points": [[str(r[cat[0]]), r[num[0]]] for r in rows]}
    if len(num) >= 2:
        return {"kind": "scatter", "x": columns[num[0]], "y": columns[num[1]],
                "points": [[r[num[0]], r[num[1]]] for r in rows]}
    if len(num) == 1 and len(rows) > 1:
        return {"kind": "histogram", "x": columns[num[0]], "points": [r[num[0]] for r in rows]}
    return None


class Api:
    def __init__(self):
        self._setup = st.SetupJob()
        self._backend = None
        self._backend_key = None
        self._lock = threading.Lock()
        self._decisions = {}           # history id -> Decision (this session), for "Did you mean…?"
        self._init_history()

    # ---------------------------------------------------------------- boot & settings
    def boot(self):
        from databases import build_catalog  # noqa: F401  (import check)
        s = self.settings_get()
        return {"platform": {"darwin": "mac", "win32": "win"}.get(sys.platform, "linux"),
                "setup_needed": not st.model_installed(s["model"]),
                "models": [{"key": k, "label": v[1], "installed": st.model_installed(k),
                            "size_gb": round(v[2] / 1e9, 1) if v[2] else None} for k, v in st.MODELS.items()],
                "spider_installed": st.spider_installed(), "settings": s,
                "operating_points": self._operating_points()}

    def _operating_points(self):
        from engine import operating_points
        return operating_points()

    def hardware(self):
        return st.hardware()

    def settings_get(self):
        try:
            return {**DEFAULT_SETTINGS, **json.load(open(SETTINGS))}
        except (OSError, ValueError):
            return dict(DEFAULT_SETTINGS)

    def settings_set(self, changes):
        s = {**self.settings_get(), **{k: v for k, v in (changes or {}).items() if k in DEFAULT_SETTINGS}}
        json.dump(s, open(SETTINGS, "w"), indent=2)
        return s

    def storage(self):
        return {"app_dir": st.app_dir(), "models_dir": st.models_dir(), "data_dir": st.data_dir()}

    # ---------------------------------------------------------------- first-run setup
    def setup_start(self, model_key="codes-1b-spider", with_spider=True):
        self.settings_set({"model": model_key})
        return self._setup.start(model_key, bool(with_spider))

    def setup_status(self):
        return self._setup.snapshot()

    # ---------------------------------------------------------------- databases
    def _catalog(self):
        from databases import build_catalog
        return build_catalog()

    @staticmethod
    def _group(info):
        if info.conn is not None:
            return "Live connections"
        if "Spider" in info.source:
            return "Sample databases"
        if "Uploaded" in info.source:
            return "Files"
        return "Sample databases"

    def databases(self):
        out = []
        for label, info in self._catalog().items():
            nice = label.replace(" · Spider", "").replace(" · uploaded", "")
            if info.conn is None and "Uploaded" not in info.source:
                nice = nice[:1].upper() + nice[1:]          # sample names only; real database names stay as-is
            out.append({"id": label, "label": nice,
                        "group": self._group(info), "source": info.source,
                        "examples": info.examples[:6], "live": info.conn is not None})
        return out

    def schema(self, db_id):
        from databases import tables_of
        info = self._catalog()[db_id]
        return [{"table": t, "columns": cols, "rows": n} for t, cols, n in tables_of(info)]

    def add_sqlite(self):
        import webview
        from databases import add_upload
        win = webview.windows[0]
        picked = win.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False,
                                        file_types=("SQLite databases (*.sqlite;*.db;*.sqlite3)", "All files (*.*)"))
        if not picked:
            return {"cancelled": True}
        try:
            return {"id": add_upload(picked[0])}
        except ValueError as exc:
            return {"error": str(exc)}

    def connect(self, kind, host, port, database, user, password):
        from databases import connect
        try:
            return {"id": connect(kind, host, port, database, user, password)}
        except Exception as exc:  # noqa: BLE001 - shown to the user
            return {"error": str(exc).splitlines()[0][:300]}

    def disconnect(self, db_id):
        from databases import CONNECTED
        info = CONNECTED.pop(db_id, None)
        if info is not None:
            info.conn.engine.dispose()
        return True

    def remove_file(self, db_id):
        info = self._catalog().get(db_id)
        if info and "Uploaded" in info.source and os.path.exists(info.path):
            os.remove(info.path)
        return True

    # ---------------------------------------------------------------- asking
    def _get_backend(self):
        from model import CodesSFTBackend
        key = self.settings_get()["model"]
        if self._backend_key != key:
            if self._backend is not None:
                self._backend.unload()
            self._backend = CodesSFTBackend(st.model_path(key), label=st.MODELS[key][1])
            self._backend_key = key
        return self._backend

    def ask(self, db_id, question, mode=None):
        from engine import ConfidentRun
        info = self._catalog()[db_id]
        mode = mode or self.settings_get()["mode"]
        with self._lock:                                   # one generation at a time
            backend = self._get_backend()
            if info.conn is not None:
                d = backend.decide_connected(info.conn, question)
            else:
                d = backend.decide(info.path, question, info.comments)
        run = ConfidentRun(question, d, mode)
        result = self._serialize(run, info)
        hid = self._save_history(db_id, question, result)
        self._decisions[hid] = (d, info)
        result["id"] = hid
        return result

    def _serialize(self, run, info):
        d = run.decision
        interp = []
        for k, (i, n) in enumerate(d.interpretations()):
            c = d.candidates[i]
            interp.append({"letter": "ABC"[k], "index": i, "support": n, "rows_total": len(c.rows),
                           "preview": _rows(c.rows[:3]), "columns": list(c.columns)})
        cands = []
        for i, c in enumerate(d.candidates):
            item = {"sql": c.sql, "runs": c.runs, "error": c.error, "rows_total": len(c.rows),
                    "agrees": c.runs and c.result_hash == d.candidates[d.selected].result_hash and
                    d.candidates[d.selected].runs}
            if info.conn is not None:
                try:
                    item["sent_sql"] = info.conn.translate(c.sql)
                except Exception:  # noqa: BLE001
                    item["sent_sql"] = None
            cands.append(item)
        chosen = d.candidates[d.selected]
        return {"question": run.question, "mode": run.mode, "answered": bool(run.answered),
                "agree": d.n_agree if chosen.runs else 0, "ran": chosen.runs,
                "beam_prob": round(d.beam_prob, 3), "confidence": round(d.confidence, 4),
                "selected": d.selected, "columns": list(chosen.columns), "rows": _rows(chosen.rows),
                "rows_total": len(chosen.rows), "chart": chart_spec(list(chosen.columns), chosen.rows),
                "interpretations": interp, "candidates": cands, "live": info.conn is not None,
                "backend": getattr(info.conn, "backend", "sqlite")}

    def interpretation(self, hid, index):
        """Table for one candidate reading (the "Did you mean…?" choices)."""
        d, _info = self._decisions.get(hid, (None, None))
        if d is None:
            item = self.history_item(hid)
            c = item["candidates"][int(index)]
            return {"columns": [], "rows": [], "sql": c["sql"], "note": "Re-ask to see this reading's table."}
        c = d.candidates[int(index)]
        return {"columns": list(c.columns), "rows": _rows(c.rows), "rows_total": len(c.rows),
                "chart": chart_spec(list(c.columns), c.rows), "sql": c.sql}

    def run_sql(self, db_id, sql):
        """An analyst's edited query, run read-only on the same database."""
        from codes_prompt import SqliteTarget
        info = self._catalog()[db_id]
        target = info.conn if info.conn is not None else SqliteTarget(info.path)
        ok, cols, rows, _h, err = target.signature(sql)
        if not ok:
            return {"error": err}
        return {"columns": list(cols), "rows": _rows(rows), "rows_total": len(rows),
                "chart": chart_spec(list(cols), rows)}

    # ---------------------------------------------------------------- history
    def _init_history(self):
        con = sqlite3.connect(HISTORY_DB)
        con.execute("CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, db_id TEXT, question TEXT, "
                    "agree INTEGER, answered INTEGER, created TEXT, result TEXT)")
        con.commit(); con.close()

    def _save_history(self, db_id, question, result):
        hid = uuid.uuid4().hex[:12]
        con = sqlite3.connect(HISTORY_DB)
        con.execute("INSERT INTO history VALUES (?,?,?,?,?,?,?)",
                    (hid, db_id, question, result["agree"], int(result["answered"]),
                     dt.datetime.now().isoformat(timespec="seconds"), json.dumps(result)))
        con.commit(); con.close()
        return hid

    def history(self, db_id=None, query=None, limit=300):
        con = sqlite3.connect(HISTORY_DB)
        sql, args = "SELECT id, db_id, question, agree, answered, created FROM history", []
        where = []
        if db_id:
            where.append("db_id = ?"); args.append(db_id)
        if query:
            where.append("question LIKE ?"); args.append(f"%{query}%")
        if where:
            sql += " WHERE " + " AND ".join(where)
        rows = con.execute(sql + " ORDER BY created DESC LIMIT ?", args + [int(limit)]).fetchall()
        con.close()
        return [{"id": r[0], "db_id": r[1], "question": r[2], "agree": r[3], "answered": bool(r[4]),
                 "created": r[5]} for r in rows]

    def history_counts(self):
        con = sqlite3.connect(HISTORY_DB)
        rows = con.execute("SELECT db_id, COUNT(*) FROM history GROUP BY db_id").fetchall()
        con.close()
        return {db: n for db, n in rows}

    def history_item(self, hid):
        con = sqlite3.connect(HISTORY_DB)
        r = con.execute("SELECT result FROM history WHERE id = ?", (hid,)).fetchone()
        con.close()
        if not r:
            return None
        item = json.loads(r[0]); item["id"] = hid
        return item

    def history_delete(self, hid):
        con = sqlite3.connect(HISTORY_DB); con.execute("DELETE FROM history WHERE id = ?", (hid,))
        con.commit(); con.close(); self._decisions.pop(hid, None)
        return True

    def history_clear(self):
        con = sqlite3.connect(HISTORY_DB); con.execute("DELETE FROM history"); con.commit(); con.close()
        self._decisions.clear()
        return True
