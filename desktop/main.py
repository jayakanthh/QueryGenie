"""
QueryGenie desktop app — entry point.

    python desktop/main.py            # from source
    dist/QueryGenie.app / QueryGenie.exe   # packaged (see desktop/build.md)

Opens a native window (WKWebView on macOS, Edge WebView2 on Windows) showing desktop/ui and
exposes desktop/api.Api to it. User data — model weights, sample databases, uploads, history,
settings — lives in the per-user app-data folder (setup_tasks.app_dir()), never in the bundle.
"""
from __future__ import annotations

import multiprocessing
import os
import sys

# Must run before anything else. In a packaged build, libraries that start helper processes
# (e.g. multiprocessing's resource tracker) re-launch this executable; without this call each
# helper would start the whole app again - a second window, or a runaway chain of model loads.
if __name__ == "__main__":
    multiprocessing.freeze_support()

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))     # PyInstaller bundle root
ROOT = HERE if getattr(sys, "frozen", False) else os.path.dirname(HERE)          # where querygenie/ lives
UI = os.path.join(HERE, "ui")
sys.path[:0] = [HERE, ROOT]

import setup_tasks as st  # noqa: E402

# Point the engine at writable per-user folders before it is imported.
os.environ.setdefault("QG_SAMPLE_DIR", os.path.join(st.data_dir(), "samples"))
os.environ.setdefault("QG_UPLOADS_DIR", os.path.join(st.data_dir(), "uploads"))
os.environ.setdefault("QG_SPIDER_DIR", st.spider_dir())
os.environ.setdefault("HF_HOME", os.path.join(st.app_dir(), "hf-cache"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("QG_OPERATING_POINTS", os.path.join(HERE, "results", "abstention_operating_points.json")
                      if getattr(sys, "frozen", False) else
                      os.path.join(os.path.dirname(HERE), "results", "abstention_operating_points.json"))


PREFERRED_PORT = 42017   # a fixed port keeps the window's own storage (last database, chat, view) between launches


def ui_port() -> int:
    """pywebview serves the UI on a fixed local port when storage is kept (42001 by default), so a
    second copy of the app, or any other pywebview app, used to stop it from starting. Use our own
    port, or any free one if that is taken (the window then just forgets its last view)."""
    import socket

    for port in (PREFERRED_PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    return 0


def main():
    import webview
    from api import Api

    api = Api()
    window = webview.create_window(
        "QueryGenie", url=os.path.join(UI, "index.html"), js_api=api,
        width=1280, height=820, min_size=(980, 640), background_color="#f5f5f7", text_select=True)
    webview.start(debug=bool(os.environ.get("QG_DEBUG")), private_mode=False, http_server=True,
                  http_port=ui_port(), storage_path=os.path.join(st.app_dir(), "webview"))
    return window


def selftest() -> int:
    """QG_SELFTEST=1: answer one sample question with the installed model, print a summary and exit.
    Used to check a packaged build end to end (bundled code, model loading, SQL execution)."""
    import json
    from api import Api

    api = Api()
    boot = api.boot()
    if boot["setup_needed"]:
        print(json.dumps({"ok": False, "error": "model not installed; run the app once to set up"}))
        return 1
    db = next(d for d in api.databases() if d["examples"])
    res = api.ask(db["id"], db["examples"][0])
    api.chat_delete(res["chat_id"])                      # leave no trace in the user's chats
    print(json.dumps({"ok": True, "db": db["id"], "question": db["examples"][0], "agree": res["agree"],
                      "answered": res["answered"], "sql": res["candidates"][res["selected"]]["sql"],
                      "rows": res["rows"][:3]}))
    return 0


if __name__ == "__main__":
    if os.environ.get("QG_SELFTEST"):
        sys.exit(selftest())
    main()
