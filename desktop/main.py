"""
QueryGenie desktop app — entry point.

    python desktop/main.py            # from source
    dist/QueryGenie.app / QueryGenie.exe   # packaged (see desktop/build.md)

Opens a native window (WKWebView on macOS, Edge WebView2 on Windows) showing desktop/ui and
exposes desktop/api.Api to it. User data — model weights, sample databases, uploads, history,
settings — lives in the per-user app-data folder (setup_tasks.app_dir()), never in the bundle.
"""
from __future__ import annotations

import os
import sys

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))     # PyInstaller bundle root
SRC = os.path.join(HERE, "src") if getattr(sys, "frozen", False) else os.path.join(os.path.dirname(HERE), "src")
UI = os.path.join(HERE, "ui")
sys.path[:0] = [HERE, SRC]

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


def main():
    import webview
    from api import Api

    api = Api()
    window = webview.create_window(
        "QueryGenie", url=os.path.join(UI, "index.html"), js_api=api,
        width=1280, height=820, min_size=(980, 640), background_color="#f5f5f7", text_select=True)
    webview.start(debug=bool(os.environ.get("QG_DEBUG")), private_mode=False, http_server=True,
                  storage_path=os.path.join(st.app_dir(), "webview"))
    return window


if __name__ == "__main__":
    main()
