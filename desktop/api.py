"""
The bridge between the desktop interface (desktop/ui) and the QueryGenie core (querygenie/).

pywebview exposes every public method of `Api` to JavaScript as window.pywebview.api.<name>(),
returning a promise. Everything returned here is plain JSON.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import os
import sqlite3
import sys
import threading
import time
import uuid

import setup_tasks as st

HISTORY_DB = os.path.join(st.app_dir(), "history.sqlite")
SETTINGS = os.path.join(st.app_dir(), "settings.json")
DEFAULT_SETTINGS = {"layout": "answer", "mode": "balanced", "model": "codes-1b-spider",
                    "engine": None,          # None = the evaluated CodeS model in "model"
                    "repair": True,          # send failed candidate queries back once with their error
                    "context_on": True,      # use earlier questions of a chat as context for follow-ups
                    "context_turns": 3,      # how many (-1 = all that fit the model's window)
                    "context_results": "local",   # earlier result rows in the context: local / all / none
                    "recent_engines": []}    # last few models chosen (for the quick picker)

# Models of the earlier Gradio prototype. Looked for in the app's models folder and, when running
# from source, in the repository's mlx_models/ and gguf_models/ (legacy/scripts/convert_mlx.py).
LEGACY_MODELS = [
    ("mlx", "codes-3b-spider-4bit", "CodeS-3B-Spider · MLX 4-bit", "Fine-tuned on Spider; fast on Apple Silicon"),
    ("mlx", "codes-7b-spider-4bit", "CodeS-7B-Spider · MLX 4-bit", "Fine-tuned on Spider; needs about 6 GB of memory"),
    ("gguf", "codes-7b-spider-Q2_K.gguf", "CodeS-7B-Spider · GGUF 2-bit", "Fine-tuned on Spider; llama.cpp"),
    ("mlx", "codes-3b-4bit", "CodeS-3B base · MLX 4-bit", "Not fine-tuned on Spider"),
    ("mlx", "codes-1b-4bit", "CodeS-1B base · MLX 4-bit", "Not fine-tuned on Spider"),
    ("hf", "seeklhy/codes-1b", "CodeS-1B base", "Not fine-tuned on Spider; downloads from Hugging Face on first use"),
    ("hf", "seeklhy/codes-3b", "CodeS-3B base", "Not fine-tuned on Spider; downloads from Hugging Face on first use"),
]
ENGINE_KINDS = {"mlx", "gguf", "hf", "ollama", "compat", "openai", "anthropic", "gemini", "xai",
                "deepseek", "mistral", "groq", "openrouter", "together"}

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


_DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?$")


def chart_spec(columns, rows):
    """The same choice rules as legacy/charts.py, as data for the UI: a date or year column with a number
    -> line (sorted by date); text with a number -> bar; two numbers -> scatter; one number -> histogram."""
    if not columns or not rows:
        return None
    rows = rows[:50]

    def numeric(i):
        vals = [r[i] for r in rows if r[i] is not None]
        return bool(vals) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)

    def datelike(i):
        vals = [r[i] for r in rows if r[i] is not None]
        if not vals:
            return False
        if all(isinstance(v, str) and _DATE.match(v.strip()) for v in vals):
            return True
        name = str(columns[i]).lower()                       # a "year" column holding years
        return ("year" in name or "date" in name) and all(isinstance(v, int) and 1000 <= v <= 2999 for v in vals)

    dates = [i for i in range(len(columns)) if datelike(i)]
    num = [i for i in range(len(columns)) if numeric(i) and i not in dates]
    if dates and num and len(rows) > 1:
        x, y = dates[0], num[0]
        pts = sorted(([str(r[x]), r[y]] for r in rows if r[x] is not None and r[y] is not None), key=lambda p: p[0])
        return {"kind": "line", "x": columns[x], "y": columns[y], "points": pts}
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
        self._usage = {}               # engine -> tokens and reported limits (this session), see usage()
        self._init_history()

    # ---------------------------------------------------------------- boot & settings
    def boot(self):
        from querygenie.databases import build_catalog  # noqa: F401  (import check)
        s = self.settings_get()
        return {"platform": {"darwin": "mac", "win32": "win"}.get(sys.platform, "linux"),
                "setup_needed": s.get("engine") is None and not st.model_installed(s["model"]),
                "engine": self._engine_info(),
                "models": [{"key": k, "label": v[1], "installed": st.model_installed(k),
                            "size_gb": round(v[2] / 1e9, 1) if v[2] else None} for k, v in st.MODELS.items()],
                "spider_installed": st.spider_installed(), "settings": s,
                "operating_points": self._operating_points()}

    def _operating_points(self):
        from querygenie.confidence import operating_points
        return operating_points()

    def window_zoom(self):
        """Double-click on a top bar: zoom the window, as a macOS title bar would."""
        win = getattr(self, "_window", None)
        if win is None or sys.platform != "darwin":
            return False
        from PyObjCTools import AppHelper
        AppHelper.callAfter(lambda: win.native.zoom_(None))
        return True

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
        from querygenie.databases import build_catalog
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
        from querygenie.databases import tables_of
        info = self._catalog()[db_id]
        return [{"table": t, "columns": cols, "rows": n} for t, cols, n in tables_of(info)]

    def schema_map(self, db_id):
        from querygenie.databases import schema_graph
        return schema_graph(self._catalog()[db_id])

    def add_sqlite(self):
        import webview
        from querygenie.databases import add_upload
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
        from querygenie.databases import connect
        try:
            return {"id": connect(kind, host, port, database, user, password)}
        except Exception as exc:  # noqa: BLE001 - shown to the user
            return {"error": str(exc).splitlines()[0][:300]}

    def disconnect(self, db_id):
        from querygenie.databases import CONNECTED
        info = CONNECTED.pop(db_id, None)
        if info is not None:
            info.conn.engine.dispose()
        return True

    def remove_file(self, db_id):
        info = self._catalog().get(db_id)
        if info and "Uploaded" in info.source and os.path.exists(info.path):
            os.remove(info.path)
        return True

    # ---------------------------------------------------------------- models
    @staticmethod
    def _legacy_paths():
        """name -> path for every legacy model found on disk."""
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        dirs = [st.models_dir(), os.path.join(repo, "mlx_models"), os.path.join(repo, "gguf_models")]
        found = {}
        for kind, name, *_ in LEGACY_MODELS:
            if kind == "hf":
                continue
            for d in dirs:
                p = os.path.join(d, name)
                if (os.path.isdir(p) if kind == "mlx" else os.path.isfile(p)):
                    found[name] = p
                    break
        return found

    CODES_KINDS = ("evaluated", "hf", "mlx", "gguf")      # completion models trained on single questions

    def _engine_chat(self, spec=None):
        """Does the current model hold a conversation (Ollama, cloud, OpenAI-style servers)? CodeS doesn't."""
        spec = spec if spec is not None else self.settings_get().get("engine")
        return bool(spec) and spec.get("kind") not in self.CODES_KINDS

    def _engine_info(self, spec=None):
        """What answers questions now: label, and whether its confidence was calibrated."""
        s = self.settings_get()
        spec = spec if spec is not None else s.get("engine")
        if not spec:
            key = s["model"]
            return {"kind": "evaluated", "model": key, "label": st.MODELS[key][1], "chat": False,
                    "calibrated": key == "codes-1b-spider", "cloud": False, "effort": None, "effort_levels": None}
        from querygenie.providers import CLOUD, effort_levels
        kind = spec["kind"]
        cloud = kind in CLOUD or (kind == "compat" and not any(
            h in (spec.get("base_url") or "") for h in ("localhost", "127.0.0.1", "[::1]")))
        where = CLOUD[kind]["name"] if kind in CLOUD else {"ollama": "Ollama", "compat": "OpenAI-compatible server",
                                                           "hf": "this computer", "mlx": "MLX", "gguf": "llama.cpp"}[kind]
        return {"kind": kind, "model": spec.get("model"), "label": spec.get("label") or spec.get("model"),
                "chat": self._engine_chat(spec),
                "where": where, "calibrated": False, "cloud": cloud, "base_url": spec.get("base_url"),
                "effort": spec.get("effort"), "effort_levels": effort_levels(kind)}

    def provider_models(self, kind, base_url=None):
        """Ask a service which models it offers (also a quick check that the key or server works)."""
        from querygenie import providers
        try:
            return {"models": providers.list_models(kind, base_url)}
        except providers.ProviderError as exc:
            return {"error": str(exc)}

    def key_save(self, provider, key):
        """Store an API key in the OS keychain. The key is never returned to the interface."""
        from querygenie import providers
        try:
            providers.key_set(provider, key or None)
        except providers.ProviderError as exc:
            return {"error": str(exc)}
        return {"saved": bool(key)}

    def engine_set(self, spec):
        """Choose what answers questions. None = the evaluated CodeS model (settings["model"])."""
        if spec is not None:
            if spec.get("kind") not in ENGINE_KINDS or not spec.get("model"):
                return {"error": "Choose a model first."}
            spec = {k: spec[k] for k in ("kind", "model", "label", "base_url", "effort") if spec.get(k)}
        if spec:
            key = self._provider_of(spec)
            conf = self._pconf(self.settings_get(), key)
            if key in ("legacy", "ollama"):
                conf["hidden"] = [m for m in conf["hidden"] if m != spec["model"]]
            elif spec["model"] not in conf["enabled"] + conf["custom"]:
                conf["enabled"].append(spec["model"])
            self._save_pconf(key, conf)
        s = self.settings_get(); s["engine"] = spec
        if spec:
            same = lambda e: (e.get("kind"), e.get("model"), e.get("base_url")) == (spec["kind"], spec["model"], spec.get("base_url"))
            s["recent_engines"] = ([spec] + [e for e in s.get("recent_engines", []) if not same(e)])[:8]
        json.dump(s, open(SETTINGS, "w"), indent=2)
        return {"engine": self._engine_info()}

    def engine_effort(self, effort):
        """Change the reasoning effort of the current model (None = the model's default)."""
        s = self.settings_get()
        spec = s.get("engine")
        if not spec:
            return {"error": "The evaluated CodeS model has no effort setting."}
        from querygenie.providers import effort_levels
        if effort is not None and effort not in (effort_levels(spec["kind"]) or []):
            return {"error": "This model has no such effort level."}
        return self.engine_set({**spec, "effort": effort} if effort else {k: v for k, v in spec.items() if k != "effort"})

    # ---------------------------------------------------------------- providers (Settings -> Model tiles)
    # Per provider, settings["providers"][key] keeps: "hidden" (discovered models switched off),
    # "enabled" (listed models switched on), "custom" (model names typed in) and, for a server, "base_url".
    # Models found on this computer (legacy, Ollama) are on by default; cloud models are off until enabled.
    LOCAL_PROVIDERS = [("evaluated", "Evaluated model", "brand"), ("legacy", "Earlier prototype", "brand"),
                       ("ollama", "Ollama", "ollama"), ("hf", "Your CodeS model", "hf"),
                       ("compat", "OpenAI-compatible server", "compat")]

    def _pconf(self, s, key):
        return {"hidden": [], "enabled": [], "custom": [], **(s.get("providers", {}).get(key) or {})}

    def _save_pconf(self, key, conf):
        s = self.settings_get()
        s.setdefault("providers", {})[key] = conf
        json.dump(s, open(SETTINGS, "w"), indent=2)

    @staticmethod
    def _provider_of(spec):
        if not spec:
            return "evaluated"
        legacy_names = {name for _k, name, *_ in LEGACY_MODELS}
        if spec["kind"] in ("mlx", "gguf") or (spec["kind"] == "hf" and spec["model"] in legacy_names):
            return "legacy"
        return spec["kind"]

    def _is_current(self, s, spec, evaluated=None):
        e = s.get("engine")
        if evaluated:
            return not e and s["model"] == evaluated
        return bool(e) and (e["kind"], e["model"], e.get("base_url")) == (spec["kind"], spec["model"], spec.get("base_url"))

    def _provider_models(self, key, s, live=None):
        """Models of one provider: [{id, label, spec, on, current, available, note, custom}]."""
        import importlib.util
        conf, out = self._pconf(s, key), []
        if key == "evaluated":
            for k, v in st.MODELS.items():
                out.append({"id": k, "label": v[1], "spec": None, "evaluated": k, "on": True, "custom": False,
                            "current": self._is_current(s, None, k), "available": st.model_installed(k),
                            "note": ("Accuracy measured on Spider: 77.8%, 83.3% when it may decline" if k == "codes-1b-spider"
                                     else "Uses the confidence threshold measured on 1B") +
                                    ("" if st.model_installed(k) else " · not downloaded"),
                            "size_gb": round(v[2] / 1e9, 1) if v[2] else None})
            return out
        if key == "legacy":
            found = self._legacy_paths()
            runtime = {"mlx": importlib.util.find_spec("mlx_lm") is not None,
                       "gguf": importlib.util.find_spec("llama_cpp") is not None, "hf": True}
            for kind, name, label, note in LEGACY_MODELS:
                ok = runtime[kind] and (kind == "hf" or name in found)
                why = (None if ok else "Needs " + ("mlx-lm (Apple Silicon)" if kind == "mlx" else "llama-cpp-python") +
                       " — run from source with requirements-apple.txt" if not runtime[kind] else
                       "Model files not found" + (" — build with legacy/scripts/convert_mlx.py" if kind == "mlx" else ""))
                spec = {"kind": kind, "model": name, "label": label}
                out.append({"id": name, "label": label, "spec": spec, "on": ok and name not in conf["hidden"],
                            "current": self._is_current(s, spec), "available": ok, "note": note if ok else why, "custom": False})
            return out
        cloud = key not in ("ollama", "hf", "compat")
        base = conf.get("base_url") if key == "compat" else None
        ids = []
        for m in (live or []):
            ids.append((m["id"], m.get("name") or "", False, m.get("size_gb")))
        for c in conf["custom"]:
            if c not in [i[0] for i in ids]:
                ids.append((c, "", True, None))
        for c in conf["enabled"]:
            if c not in [i[0] for i in ids]:
                ids.append((c, "", False, None))
        for mid, name, custom, size in ids:
            spec = {"kind": key, "model": mid, "label": mid}
            if base:
                spec["base_url"] = base
            on = (mid not in conf["hidden"]) if key == "ollama" and not custom else (mid in conf["enabled"] or custom)
            note = name if name and name != mid else ""
            if size:
                note = f"{size} GB" + (f" · {note}" if note else "")
            out.append({"id": mid, "label": mid, "spec": spec, "on": on, "current": self._is_current(s, spec),
                        "available": True, "note": note, "custom": custom, "access": conf.get("access", {}).get(mid)})
        return out

    def providers_overview(self):
        """The tiles: one per provider, with a one-line status."""
        from querygenie import providers
        s = self.settings_get()
        cur = self._provider_of(s.get("engine"))
        tiles = []
        for key, name, icon in self.LOCAL_PROVIDERS:
            conf = self._pconf(s, key)
            running = True
            if key == "ollama":
                try:
                    models = self._provider_models(key, s, providers.list_models("ollama"))
                except providers.ProviderError:
                    models, running = self._provider_models(key, s, []), False
            else:
                models = self._provider_models(key, s)
            avail = [m for m in models if m["available"]]
            on = sum(m["on"] for m in avail)
            counted = (f"{len(avail)} model{'' if len(avail) == 1 else 's'}" if on == len(avail)
                       else f"{on} of {len(avail)} in picker")
            if key == "evaluated":
                status = "Measured on Spider" if avail else "Not downloaded"
            elif key == "ollama":
                status = f"Running · {counted}" if running else "Not running"
            elif key == "compat":
                status = conf.get("base_url") or "Not set up"
            elif key == "hf":
                status = f"{len(models)} added" if models else "Add a model by name"
            else:
                status = counted
            tiles.append({"key": key, "name": name, "icon": icon, "group": "local", "status": status,
                          "on": on, "current": cur == key})
        for key, meta in providers.CLOUD.items():
            conf = self._pconf(s, key)
            saved = providers.key_saved(key)
            on = len(set(conf["enabled"]) | set(conf["custom"])) if saved else 0
            status = ("Key saved" + (f" · {on} in picker" if on else "")) if saved else "No key"
            tiles.append({"key": key, "name": meta["name"].split(" (")[0], "detail": meta["name"], "icon": key, "group": "cloud",
                          "status": status, "on": on, "current": cur == key})
        return {"tiles": tiles, "current": self._engine_info()}

    # ---------------------------------------------------------------- access and usage
    def _set_access(self, key, model, status, note=None):
        conf = self._pconf(self.settings_get(), key)
        conf.setdefault("access", {})[model] = {"status": status, "note": note, "when": time.time()}
        self._save_pconf(key, conf)

    def provider_check(self, key, model):
        """Send one tiny request to see whether this key may use `model` (works / no quota / no access...)."""
        from querygenie import providers
        from querygenie.providers.usage import classify
        spec = {"kind": key, "model": model, "label": model}
        conf = self._pconf(self.settings_get(), key)
        if key == "compat" and conf.get("base_url"):
            spec["base_url"] = conf["base_url"]
        try:
            backend = providers.build(spec, self._legacy_paths())
            backend.complete_once("Reply with the single word OK.")
            status, note = "works", None
        except providers.ProviderError as exc:
            status, note = classify(str(exc), exc.refusal), str(exc)[:300]
        self._set_access(key, model, status, note)
        return {"status": status, "note": note}

    def usage(self):
        """For the meter next to the model picker: the context window and how much of it the last question
        used, tokens this session, and the rate limits the service reported (only reported numbers)."""
        from querygenie import providers
        s = self.settings_get()
        spec, eng = s.get("engine"), self._engine_info()
        ek = json.dumps(spec, sort_keys=True) if spec else "evaluated:" + s["model"]
        if not spec or spec.get("kind") == "hf":
            from querygenie.pipeline import MAX_PROMPT_TOKENS
            window, local = MAX_PROMPT_TOKENS + 256, True      # CodeS: 4,096 tokens (prompt + 256 for the query)
        else:
            window, local = providers.context_window(spec), not eng.get("cloud")
        u = self._usage.get(ek, {})
        return {"label": eng["label"], "where": eng.get("where") or "this computer", "local": local,
                "cloud": bool(eng.get("cloud")), "kind": (spec or {}).get("kind", "evaluated"), "window": window,
                "last": u.get("last"), "session": u.get("session"), "limits": u.get("limits"), "refused": u.get("refused")}

    def _record_usage(self, backend, error=None):
        s = self.settings_get()
        spec = s.get("engine")
        ek = json.dumps(spec, sort_keys=True) if spec else "evaluated:" + s["model"]
        u = self._usage.setdefault(ek, {"session": {"questions": 0, "requests": 0, "input": 0, "output": 0}})
        if error is not None:
            u["refused"] = {"message": str(error)[:300], "refusal": getattr(error, "refusal", None), "when": time.time()}
            if spec:
                from querygenie.providers.usage import classify
                self._set_access(self._provider_of(spec), spec["model"], classify(str(error), getattr(error, "refusal", None)), str(error)[:300])
            return
        calls = list(getattr(backend, "calls", []) or [])
        prompts = [c["prompt"] for c in calls if c.get("prompt")]
        outs = [c["output"] for c in calls if c.get("output")]
        estimated = False
        if not prompts:                                  # the service didn't say: estimate from the prompt text
            from querygenie.context import estimate_tokens
            ctx = getattr(backend, "last_context", None)
            text = (ctx[2] if ctx else "") + " ".join(t["content"] for t in getattr(backend, "turns", []) or [])
            prompts, estimated = ([estimate_tokens(text)] if text else []), True
        u["last"] = {"prompt": max(prompts) if prompts else None, "requests": len(calls) or None,
                     "failed": len(getattr(backend, "failures", []) or []),
                     "input": sum(prompts) if not estimated else None, "output": sum(outs) or None,
                     "estimated": estimated, "when": time.time()}
        u["session"]["questions"] += 1
        u["session"]["requests"] += len(calls)
        u["session"]["input"] += sum(prompts) if not estimated else 0
        u["session"]["output"] += sum(outs)
        limits = next((c["limits"] for c in reversed(calls) if c.get("limits")), None)
        if limits:
            u["limits"] = {"values": limits, "when": time.time()}
        u.pop("refused", None)
        if spec:
            self._set_access(self._provider_of(spec), spec["model"], "works")

    def provider_detail(self, key):
        """One provider's page. Cloud and server providers are asked for their live model list."""
        from querygenie import providers
        s = self.settings_get()
        conf = self._pconf(s, key)
        live, error = None, None
        if key not in ("evaluated", "legacy", "hf"):
            try:
                if key == "compat":
                    live = providers.list_models("compat", conf.get("base_url")) if conf.get("base_url") else None
                elif key == "ollama" or providers.key_saved(key):
                    live = providers.list_models(key)
            except providers.ProviderError as exc:
                error = str(exc)
        cloud = key in providers.CLOUD
        return {"key": key, "cloud": cloud, "key_saved": providers.key_saved("compat" if key == "compat" else key) if (cloud or key == "compat") else None,
                "base_url": conf.get("base_url"), "error": error, "models": self._provider_models(key, s, live),
                "effort_levels": providers.effort_levels(key), "can_add": key not in ("evaluated", "legacy")}

    def provider_toggle(self, key, model, on):
        """Show or hide a model in the picker under the question box."""
        s = self.settings_get()
        conf = self._pconf(s, key)
        discovered = key in ("legacy", "ollama") and model not in conf["custom"]
        if discovered:
            conf["hidden"] = [m for m in conf["hidden"] if m != model] + ([] if on else [model])
        else:
            conf["enabled"] = [m for m in conf["enabled"] if m != model] + ([model] if on else [])
        self._save_pconf(key, conf)
        return {"ok": True}

    def provider_add_model(self, key, model):
        model = (model or "").strip()
        if not model or key in ("evaluated", "legacy"):
            return {"error": "Type a model name."}
        conf = self._pconf(self.settings_get(), key)
        if model not in conf["custom"]:
            conf["custom"].append(model)
        self._save_pconf(key, conf)
        return {"ok": True}

    def provider_remove_model(self, key, model):
        conf = self._pconf(self.settings_get(), key)
        conf["custom"] = [m for m in conf["custom"] if m != model]
        conf["enabled"] = [m for m in conf["enabled"] if m != model]
        self._save_pconf(key, conf)
        return {"ok": True}

    def provider_set_url(self, key, url):
        if key != "compat":
            return {"error": "Only a server has an address."}
        conf = self._pconf(self.settings_get(), key)
        conf["base_url"] = (url or "").strip().rstrip("/") or None
        self._save_pconf(key, conf)
        return {"ok": True}

    def models_quick(self):
        """The picker under the question box: every model switched on, grouped by provider."""
        from querygenie import providers
        s = self.settings_get()
        groups = []
        for key, name, icon in self.LOCAL_PROVIDERS:
            live = None
            if key == "ollama":
                try:
                    live = providers.list_models("ollama")
                except providers.ProviderError:
                    live = []
            items = [m for m in self._provider_models(key, s, live) if m["on"] and m["available"]]
            if items:
                groups.append({"key": key, "name": name, "icon": icon, "cloud": False, "models": items})
        for key, meta in providers.CLOUD.items():
            if not providers.key_saved(key):
                continue
            items = [m for m in self._provider_models(key, s) if m["on"]]
            if items:
                groups.append({"key": key, "name": meta["name"].split(" (")[0], "icon": key, "cloud": True, "models": items})
        return {"current": self._engine_info(), "current_model": s["model"], "groups": groups}

    # ---------------------------------------------------------------- asking
    def _get_backend(self):
        s = self.settings_get()
        spec = s.get("engine")
        key = json.dumps(spec, sort_keys=True) if spec else "evaluated:" + s["model"]
        if self._backend_key != key:
            if self._backend is not None:
                self._backend.unload()                      # never hold two local models at once
                self._backend = None
            if spec:
                from querygenie import providers
                self._backend = providers.build(spec, self._legacy_paths())
            else:
                from querygenie.model import CodesSFTBackend
                self._backend = CodesSFTBackend(st.model_path(s["model"]), label=st.MODELS[s["model"]][1])
            self._backend_key = key
        return self._backend

    def _context(self, chat_id, k):
        """The last k questions of a chat (oldest first) with the SQL that answered them, stopping at a
        question asked as a new topic."""
        if not chat_id or k <= 0:
            return []
        con = self._db()
        rows = con.execute("SELECT question, result FROM history WHERE chat_id = ? ORDER BY created DESC, rowid DESC",
                           (chat_id,)).fetchall()
        con.close()
        out = []
        for q, res in rows:
            r = json.loads(res)
            sel = (r.get("candidates") or [{}])[r.get("selected", 0)] if r.get("candidates") else {}
            out.append({"question": q, "sql": sel.get("sql") if r.get("ran") else None,
                        "columns": r.get("columns") or [], "rows": (r.get("rows") or [])[:5],
                        "rows_total": r.get("rows_total", 0)})
            if len(out) >= k or r.get("context_break"):
                break
        return out[::-1]

    def _swap_followup(self, info, history, question):
        """'What about IT?' -> the previous question with the value swapped (querygenie/context.py)."""
        from querygenie.context import substitute
        from querygenie.pipeline import matched_contents_for, matched_contents_from_index
        try:
            if info.conn is not None:
                index = info.conn.build_index()
                return substitute(history, question, lambda t: matched_contents_from_index(index, t),
                                  lambda col: index.get(col, []))
            from querygenie.vendor.codes_db_utils import get_db_schema
            db_id = os.path.splitext(os.path.basename(info.path))[0]
            schema = get_db_schema(info.path, {db_id: info.comments} if info.comments else {}, db_id)

            def values_of(col):
                t, c = col.split(".", 1)
                con = sqlite3.connect(f"file:{info.path}?mode=ro", uri=True)
                try:
                    return [str(r[0]) for r in con.execute(f'SELECT DISTINCT "{c}" FROM "{t}" WHERE "{c}" IS NOT NULL LIMIT 500')]
                finally:
                    con.close()
            return substitute(history, question, lambda t: matched_contents_for(info.path, schema, t), values_of)
        except Exception:  # noqa: BLE001 - a rewrite that fails just means no rewrite
            return None

    def ask(self, db_id, question, mode=None, chat_id=None, fresh=False):
        """Answer one question. Without `chat_id` a new chat is started, titled by the question. In a chat,
        the last few questions are context for a follow-up unless `fresh` (a new topic)."""
        from querygenie.confidence import ConfidentRun
        info = self._catalog()[db_id]
        mode = mode or self.settings_get()["mode"]
        s_ = self.settings_get()
        # Context is for chat models only: CodeS was trained on single questions, and glued or rewritten
        # follow-ups made it answer the wrong question, so CodeS models answer every question on its own.
        turns = int(s_.get("context_turns", 3)) if s_.get("context_on", True) and self._engine_chat() else 0
        history = [] if fresh else self._context(chat_id, 1000 if turns < 0 else turns)
        rewritten = self._swap_followup(info, history, question) if history else None
        model_question, model_history = (rewritten, None) if rewritten else (question, history)
        from querygenie.providers import ProviderError
        with self._lock:                                   # one generation at a time
            try:
                backend = self._get_backend()
                how = "swap" if rewritten else None
                if history and turns < 0:
                    # "All that fit": keep the latest turns within about half the model's window,
                    # leaving the rest for the database description and the answer.
                    from querygenie import providers
                    from querygenie.context import fit_history
                    window = providers.context_window(self.settings_get().get("engine") or {})
                    history = fit_history(history, window // 2 if window else None, max_turns=200 if window else 20)
                    if not rewritten:
                        model_history = history
                share = self.settings_get().get("context_results", "local")
                backend.share_results = share == "all" or (share == "local" and not getattr(backend, "cloud", False))
                if info.conn is not None:
                    d = backend.decide_connected(info.conn, model_question, history=model_history or None)
                else:
                    d = backend.decide(info.path, model_question, info.comments, history=model_history or None)
                repairs = {}
                if self.settings_get().get("repair", True):
                    from querygenie.repair import repair_empty, self_correct
                    d, repairs = self_correct(backend, d)
                    chosen = d.candidates[d.selected]
                    if chosen.runs and not chosen.rows:          # no rows: did it miss a stored value?
                        from querygenie.context import linking_text
                        matched = self._matched_values(info, linking_text(history, question))
                        d, more = repair_empty(backend, d, matched)
                        repairs.update(more)
                self._record_usage(backend)
            except ProviderError as exc:
                self._record_usage(None, exc)
                raise RuntimeError(f"{self._engine_info()['label']}: {exc}") from exc
        run = ConfidentRun(question, d, mode)
        result = self._serialize(run, info)
        for i, r in repairs.items():
            result["candidates"][i]["repaired"] = r
        result["repaired"] = len(repairs)
        result["repaired_empty"] = sum(1 for r in repairs.values() if r.get("kind") == "empty")
        chosen = d.candidates[d.selected]
        if chosen.runs and not chosen.rows:                # still nothing: say which stored values it didn't use
            from querygenie.context import linking_text
            from querygenie.repair import unused_values
            hints = unused_values(chosen.sql, self._matched_values(info, linking_text(history, question)), 3)
            if hints:
                result["empty_hint"] = [{"column": c, "value": v} for c, v in hints]
        failures = list(getattr(backend, "failures", []) or [])
        if failures:            # refused or failed requests count as candidates that did not run
            result["failed_requests"] = {"count": len(failures), "reason": str(failures[0]).split(":")[0][:160]}
        result["engine"] = self._engine_info()
        from querygenie.context import linking_text
        result["unclear"] = self._unclear(info, linking_text(history, question))
        result["context_break"] = bool(fresh)
        if history:
            result["context"] = {"questions": [h["question"] for h in history], "rewritten": bool(rewritten), "how": how,
                                 "with_results": bool(getattr(backend, "share_results", False) and getattr(backend, "chat", False)),
                                 "asked_as": rewritten}
        chat_id = chat_id or self._new_chat(db_id, question)
        hid = self._save_history(db_id, question, result, chat_id)
        self._decisions[hid] = (d, info)
        result["id"], result["chat_id"] = hid, chat_id
        return result

    def _schema(self, info):
        if info.conn is not None:
            return info.conn.introspect()
        from querygenie.vendor.codes_db_utils import get_db_schema
        db_id = os.path.splitext(os.path.basename(info.path))[0]
        return get_db_schema(info.path, {db_id: info.comments} if info.comments else {}, db_id)

    def _matched_values(self, info, text):
        """The value retriever's matches ({"table.column": [values]}) for a question."""
        from querygenie.pipeline import matched_contents_for, matched_contents_from_index
        try:
            if info.conn is not None:
                return matched_contents_from_index(info.conn.build_index(), text)
            return matched_contents_for(info.path, self._schema(info), text)
        except Exception:  # noqa: BLE001
            return {}

    def _unclear(self, info, question):
        """None if the question names a table, column or stored value; otherwise the database's tables,
        so the interface can ask "all of what?" instead of presenting the model's guess as the answer."""
        from querygenie.mentions import is_unclear, schema_mentions
        from querygenie.pipeline import matched_contents_for, matched_contents_from_index
        try:
            if info.conn is not None:
                schema = info.conn.introspect()
                values = lambda: matched_contents_from_index(info.conn.build_index(), question)
            else:
                from querygenie.vendor.codes_db_utils import get_db_schema
                db_id = os.path.splitext(os.path.basename(info.path))[0]
                schema = get_db_schema(info.path, {db_id: info.comments} if info.comments else {}, db_id)
                values = lambda: matched_contents_for(info.path, schema, question)
            m = schema_mentions(schema, question)
            if is_unclear(m):                         # the value scan is the slower check: only if needed
                m = schema_mentions(schema, question, values())
            if not is_unclear(m):
                return None
            from querygenie.databases import tables_of
            return {"tables": [{"table": t, "rows": n, "columns": list(cols[:5]), "more": max(0, len(cols) - 5)}
                               for t, cols, n in tables_of(info)]}
        except Exception:  # noqa: BLE001 - a safeguard must never stop an answer
            return None

    def _serialize(self, run, info):
        d = run.decision
        interp = []
        for k, (i, n) in enumerate(d.interpretations()):
            c = d.candidates[i]
            interp.append({"letter": "ABC"[k], "index": i, "support": n, "rows_total": len(c.rows),
                           "preview": _rows(c.rows[:3]), "columns": list(c.columns)})
        from querygenie.pipeline import normalise_sql
        cands, first_of = [], {}
        for i, c in enumerate(d.candidates):
            key = normalise_sql(c.sql)
            item = {"sql": c.sql, "runs": c.runs, "error": c.error, "rows_total": len(c.rows),
                    "columns": list(c.columns), "preview": _rows(c.rows[:5]),
                    "same_as": first_of.get(key) if key else None,      # duplicate of an earlier candidate
                    "agrees": c.runs and c.result_hash == d.candidates[d.selected].result_hash and
                    d.candidates[d.selected].runs}
            if info.conn is not None:
                try:
                    item["sent_sql"] = info.conn.translate(c.sql)
                except Exception:  # noqa: BLE001
                    item["sent_sql"] = None
            first_of.setdefault(key, i)
            cands.append(item)
        chosen = d.candidates[d.selected]
        return {"question": run.question, "mode": run.mode, "answered": bool(run.answered),
                "agree": d.n_agree if chosen.runs else 0, "ran": chosen.runs,
                "beam_prob": round(d.beam_prob, 3), "confidence": round(d.confidence, 4),
                "selected": d.selected, "columns": list(chosen.columns), "rows": _rows(chosen.rows),
                "rows_total": len(chosen.rows), "chart": chart_spec(list(chosen.columns), chosen.rows),
                "interpretations": interp, "candidates": cands, "live": info.conn is not None,
                "distinct_queries": len({normalise_sql(c.sql) for c in d.candidates if c.sql}),
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
        from querygenie.pipeline import SqliteTarget
        info = self._catalog()[db_id]
        target = info.conn if info.conn is not None else SqliteTarget(info.path)
        ok, cols, rows, _h, err = target.signature(sql)
        if not ok:
            return {"error": err}
        return {"columns": list(cols), "rows": _rows(rows), "rows_total": len(rows),
                "chart": chart_spec(list(cols), rows)}

    # ---------------------------------------------------------------- chats & history
    # A chat is a thread of questions on one database; each question (a history row) belongs to one.
    # CodeS answers every question on its own: earlier turns are not given to the model as context.
    def _db(self):
        return sqlite3.connect(HISTORY_DB)

    def _init_history(self):
        con = self._db()
        con.execute("CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, db_id TEXT, question TEXT, "
                    "agree INTEGER, answered INTEGER, created TEXT, result TEXT)")
        con.execute("CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, db_id TEXT, title TEXT, "
                    "created TEXT, updated TEXT)")
        if "chat_id" not in [c[1] for c in con.execute("PRAGMA table_info(history)")]:
            # Questions asked before chats existed become one chat each.
            con.execute("ALTER TABLE history ADD COLUMN chat_id TEXT")
            con.execute("INSERT OR IGNORE INTO chats SELECT id, db_id, question, created, created FROM history")
            con.execute("UPDATE history SET chat_id = id")
        con.commit(); con.close()

    @staticmethod
    def _now():
        return dt.datetime.now().isoformat(timespec="seconds")

    def _new_chat(self, db_id, title):
        cid = uuid.uuid4().hex[:12]
        con = self._db()
        con.execute("INSERT INTO chats VALUES (?,?,?,?,?)", (cid, db_id, title[:200], self._now(), self._now()))
        con.commit(); con.close()
        return cid

    def _save_history(self, db_id, question, result, chat_id):
        hid = uuid.uuid4().hex[:12]
        con = self._db()
        con.execute("INSERT INTO history (id, db_id, question, agree, answered, created, result, chat_id) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (hid, db_id, question, result["agree"], int(result["answered"]), self._now(),
                     json.dumps(result), chat_id))
        con.execute("UPDATE chats SET updated = ? WHERE id = ?", (self._now(), chat_id))
        con.commit(); con.close()
        return hid

    def chats(self, db_id, query=None, limit=300):
        """Chats on one database, most recently used first, with their latest answer's confidence."""
        sql = ("SELECT c.id, c.title, c.created, c.updated, COUNT(h.id), "
               "(SELECT agree FROM history WHERE chat_id = c.id ORDER BY created DESC, rowid DESC LIMIT 1), "
               "(SELECT answered FROM history WHERE chat_id = c.id ORDER BY created DESC, rowid DESC LIMIT 1) "
               "FROM chats c LEFT JOIN history h ON h.chat_id = c.id WHERE c.db_id = ?")
        args = [db_id]
        if query:
            sql += " AND (c.title LIKE ? OR EXISTS (SELECT 1 FROM history WHERE chat_id = c.id AND question LIKE ?))"
            args += [f"%{query}%"] * 2
        con = self._db()
        rows = con.execute(sql + " GROUP BY c.id ORDER BY c.updated DESC LIMIT ?", args + [int(limit)]).fetchall()
        con.close()
        return [{"id": r[0], "title": r[1], "created": r[2], "updated": r[3], "questions": r[4],
                 "agree": r[5] or 0, "answered": bool(r[6])} for r in rows]

    def chat(self, chat_id):
        """Every question in a chat, oldest first, as full results."""
        con = self._db()
        head = con.execute("SELECT id, db_id, title, created, updated FROM chats WHERE id = ?", (chat_id,)).fetchone()
        rows = con.execute("SELECT id, result, created FROM history WHERE chat_id = ? ORDER BY created, rowid",
                           (chat_id,)).fetchall()
        con.close()
        if not head:
            return None
        turns = []
        for hid, result, created in rows:
            item = json.loads(result); item["id"], item["created"] = hid, created
            turns.append(item)
        return {"id": head[0], "db_id": head[1], "title": head[2], "created": head[3], "updated": head[4],
                "turns": turns}

    def chat_rename(self, chat_id, title):
        title = (title or "").strip()[:200]
        if title:
            con = self._db(); con.execute("UPDATE chats SET title = ? WHERE id = ?", (title, chat_id))
            con.commit(); con.close()
        return True

    def chat_delete(self, chat_id):
        con = self._db()
        for (hid,) in con.execute("SELECT id FROM history WHERE chat_id = ?", (chat_id,)).fetchall():
            self._decisions.pop(hid, None)
        con.execute("DELETE FROM history WHERE chat_id = ?", (chat_id,))
        con.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
        con.commit(); con.close()
        return True

    def history_counts(self):
        """Number of chats per database (shown in the sidebar)."""
        con = self._db()
        rows = con.execute("SELECT db_id, COUNT(*) FROM chats GROUP BY db_id").fetchall()
        con.close()
        return {db: n for db, n in rows}

    def history_item(self, hid):
        con = self._db()
        r = con.execute("SELECT result, created FROM history WHERE id = ?", (hid,)).fetchone()
        con.close()
        if not r:
            return None
        item = json.loads(r[0]); item["id"], item["created"] = hid, r[1]
        return item

    def history_delete(self, hid):
        """Remove one question from its chat (the chat goes too if it becomes empty)."""
        con = self._db()
        row = con.execute("SELECT chat_id FROM history WHERE id = ?", (hid,)).fetchone()
        con.execute("DELETE FROM history WHERE id = ?", (hid,))
        if row and not con.execute("SELECT 1 FROM history WHERE chat_id = ?", (row[0],)).fetchone():
            con.execute("DELETE FROM chats WHERE id = ?", (row[0],))
        con.commit(); con.close(); self._decisions.pop(hid, None)
        return True

    def history_clear(self):
        con = self._db(); con.execute("DELETE FROM history"); con.execute("DELETE FROM chats")
        con.commit(); con.close()
        self._decisions.clear()
        return True
