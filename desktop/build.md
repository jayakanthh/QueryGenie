# Building the QueryGenie desktop app

The app is packaged with [PyInstaller](https://pyinstaller.org) from `desktop/QueryGenie.spec`.
Only the core (`querygenie/`) and the desktop code (`desktop/`) go into the bundle — `legacy/` and
`research/` are never imported. The model weights are **not** bundled: the setup assistant downloads
them on first launch into the user's app-data folder.

## macOS (Apple Silicon)

```bash
source .venv/bin/activate
pip install -r requirements.txt
pyinstaller desktop/QueryGenie.spec --noconfirm
open dist/QueryGenie.app
```

Result: `dist/QueryGenie.app`, about 875 MB (most of it PyTorch). The build is not signed or
notarised, so the first time macOS may refuse to open it: right-click the app → **Open** → **Open**.

## Windows 10 / 11

```powershell
py -3.13 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pyinstaller desktop\QueryGenie.spec --noconfirm
dist\QueryGenie\QueryGenie.exe
```

Result: the folder `dist\QueryGenie\` (ship the whole folder). Notes:

- The window uses Microsoft Edge WebView2, which is built into Windows 11 and current Windows 10.
- `pip install torch` gives the CPU build: it works everywhere but a question takes noticeably longer
  than on a GPU or Apple Silicon. For an NVIDIA GPU install the CUDA build of PyTorch first
  (see pytorch.org) and then build.
- The Windows build has not yet been tested by the team — TBD.

## Checking a build without clicking through it

```bash
QG_SELFTEST=1 dist/QueryGenie.app/Contents/MacOS/QueryGenie        # macOS
set QG_SELFTEST=1 && dist\QueryGenie\QueryGenie.exe               # Windows
```

With the model already installed (run the app once), this answers one sample question with the
bundled code and prints a JSON line such as `{"ok": true, "agree": 2, "sql": "...", "rows": [...]}`,
then exits. It leaves no chat behind.

## Things that have bitten us

- **`multiprocessing.freeze_support()`** must stay at the top of `desktop/main.py`. Libraries start
  helper processes (the multiprocessing resource tracker); in a frozen app each helper re-runs the
  executable, and without this call it starts the whole app again — a second window, or a runaway
  chain of model loads that can freeze the computer.
- **Port for the window's content.** pywebview serves the interface on a fixed local port when the
  window keeps its storage. `desktop/main.py` uses port 42017 and falls back to any free port, so a
  second copy of the app (or another pywebview app) cannot stop it from starting.
- **Memory.** Each running copy of the app (or of `desktop/devserver.py`) holds its own copy of the
  model once a question has been asked — about 2–4.5 GB. Close other copies before testing on a
  16 GB machine.
- A PyInstaller warning about `transformers.AutoTokenizer` being missing is harmless (transformers
  loads it lazily); the self-test above confirms the model loads.

## Models in the packaged build

The bundle includes everything for the evaluated model, Ollama, OpenAI-style services, Gemini and
Claude (`anthropic` SDK), and `keyring` for storing API keys in the OS keychain. MLX and llama.cpp
are **not** bundled, so the earlier prototype's MLX / GGUF models appear in Settings as "needs a
from-source install"; run `python desktop/main.py` after `pip install -r requirements-apple.txt` to
use them. `QG_SELFTEST=models` prints the model catalogue without loading a model.

## Where the app keeps its data

| | macOS | Windows |
|---|---|---|
| Models, sample databases, added files | `~/Library/Application Support/QueryGenie/` | `%APPDATA%\QueryGenie\` |
| Chats and settings | `history.sqlite`, `settings.json` in the same folder | same |

Deleting that folder resets the app to first launch.
