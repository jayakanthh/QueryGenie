# PyInstaller spec for the QueryGenie desktop app (macOS .app and Windows .exe).
#   macOS:   pyinstaller desktop/QueryGenie.spec --noconfirm   ->  dist/QueryGenie.app
#   Windows: pyinstaller desktop\QueryGenie.spec --noconfirm   ->  dist\QueryGenie\QueryGenie.exe
# The model weights are NOT bundled: the app downloads them on first launch (desktop/setup_tasks.py).
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC, DESK, VENDOR = os.path.join(ROOT, "src"), os.path.join(ROOT, "desktop"), os.path.join(ROOT, "src", "vendor")

engine_modules = ["codes_prompt", "model", "engine", "databases", "connectors", "charts", "database",
                  "build_sample_db", "codes_db_utils", "codes_bridge", "api", "setup_tasks"]

datas = [
    (os.path.join(DESK, "ui"), "ui"),
    (os.path.join(ROOT, "results", "abstention_operating_points.json"), "results"),
    (os.path.join(ROOT, "LICENSE"), "."), (os.path.join(ROOT, "NOTICE"), "."),
]
datas += collect_data_files("transformers", include_py_files=False)
for pkg in ["transformers", "tokenizers", "huggingface_hub", "safetensors", "torch", "tqdm", "regex",
            "requests", "packaging", "filelock", "numpy", "pyyaml", "sqlglot", "sqlalchemy"]:
    try:
        datas += copy_metadata(pkg)
    except Exception:
        pass

hiddenimports = engine_modules + collect_submodules("sqlglot.dialects") + [
    "sqlalchemy.dialects.postgresql", "sqlalchemy.dialects.mysql", "sqlalchemy.dialects.sqlite",
    "psycopg", "pymysql", "rapidfuzz", "func_timeout", "webview",
]

a = Analysis(
    [os.path.join(DESK, "main.py")],
    pathex=[DESK, SRC, VENDOR],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["gradio", "matplotlib", "scipy", "pytest", "IPython", "tkinter", "mlx", "mlx_lm", "llama_cpp",
              "torchvision", "torchaudio", "plotly", "pandas.tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="QueryGenie", console=False,
          icon=os.path.join(DESK, "assets", "QueryGenie.icns" if sys.platform == "darwin" else "QueryGenie.ico")
          if os.path.exists(os.path.join(DESK, "assets")) else None)
coll = COLLECT(exe, a.binaries, a.datas, name="QueryGenie")

if sys.platform == "darwin":
    app = BUNDLE(coll, name="QueryGenie.app", bundle_identifier="edu.klu.team21.querygenie",
                 icon=os.path.join(DESK, "assets", "QueryGenie.icns") if os.path.exists(os.path.join(DESK, "assets", "QueryGenie.icns")) else None,
                 info_plist={"CFBundleShortVersionString": "1.0.0", "NSHighResolutionCapable": True,
                             "LSMinimumSystemVersion": "12.0", "NSRequiresAquaSystemAppearance": False})
