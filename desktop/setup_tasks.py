"""
First-run setup for the QueryGenie desktop app: where things live, what the machine can do,
and downloading the model (and optional Spider sample databases) with progress.

Everything is stored per user:
  macOS    ~/Library/Application Support/QueryGenie/
  Windows  %APPDATA%\\QueryGenie\\
  Linux    ~/.local/share/QueryGenie/
"""
from __future__ import annotations

import ctypes
import os
import platform
import shutil
import sys
import threading
import time
import zipfile

APP = "QueryGenie"

MODELS = {
    # key: (Hugging Face repo, label, approximate download size in bytes)
    "codes-1b-spider": ("seeklhy/codes-1b-spider", "CodeS-1B (Spider)", 4_549_000_000),
    "codes-3b-spider": ("seeklhy/codes-3b-spider", "CodeS-3B (Spider)", 12_180_000_000),
}
# Config and tokenizer files; the weights are chosen per repo (safetensors when the repo has them,
# otherwise the official pytorch_model.bin) so only one copy of the weights is downloaded.
BASE_FILES = ["*.json", "*.txt", "*.model", "tokenizer*"]


def weight_patterns(siblings) -> list:
    names = [s.rfilename for s in siblings]
    return ["*.safetensors"] if any(n.endswith(".safetensors") for n in names) else ["*.bin"]


def app_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    path = os.path.join(base, APP)
    os.makedirs(path, exist_ok=True)
    return path


def models_dir() -> str:
    p = os.path.join(app_dir(), "models"); os.makedirs(p, exist_ok=True); return p


def data_dir() -> str:
    p = os.path.join(app_dir(), "data"); os.makedirs(p, exist_ok=True); return p


def model_path(key: str) -> str:
    return os.path.join(models_dir(), key)


def model_installed(key: str) -> bool:
    p = model_path(key)
    return os.path.exists(os.path.join(p, "config.json")) and any(
        f.endswith((".safetensors", ".bin")) for f in (os.listdir(p) if os.path.isdir(p) else []))


def spider_dir() -> str:
    return os.path.join(data_dir(), "spider_full", "spider_data")


def spider_installed() -> bool:
    return os.path.exists(os.path.join(spider_dir(), "dev.json"))


def _total_ram_gb() -> float | None:
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMORYSTATUSEX(); m.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return m.ullTotalPhys / 1e9
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (AttributeError, ValueError, OSError):
        return None


def hardware() -> dict:
    """What this machine can run the model on."""
    import torch
    if torch.cuda.is_available():
        accel, name = "cuda", torch.cuda.get_device_name(0)
    elif torch.backends.mps.is_available():
        accel, name = "mps", "Apple Silicon GPU (Metal)"
    else:
        accel, name = "cpu", "CPU only"
    free = shutil.disk_usage(app_dir()).free
    ram = _total_ram_gb()
    return {"os": {"darwin": "macOS", "win32": "Windows"}.get(sys.platform, platform.system()),
            "os_version": platform.mac_ver()[0] if sys.platform == "darwin" else platform.version(),
            "machine": platform.machine(), "accelerator": accel, "accelerator_name": name,
            "ram_gb": round(ram, 1) if ram else None, "free_disk_gb": round(free / 1e9, 1),
            "note": {"cuda": "Your NVIDIA graphics card will make answers fast — a few seconds each.",
                     "mps": "This Mac's Apple Silicon graphics will make answers fast — a few seconds each.",
                     "cpu": "No supported graphics card found. QueryGenie will run on the processor, so each "
                            "answer can take up to a minute."}[accel]}


class SetupJob:
    """Background download with a pollable progress snapshot."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"running": False, "phase": "idle", "message": "", "done_bytes": 0,
                      "total_bytes": 0, "finished": False, "error": None, "started": None}

    def snapshot(self):
        with self.lock:
            s = dict(self.state)
        if s["started"] and s["done_bytes"] and not s["finished"]:
            rate = s["done_bytes"] / max(1e-6, time.time() - s["started"])
            s["rate_mb_s"] = round(rate / 1e6, 1)
            if s["total_bytes"]:
                s["eta_s"] = int(max(0, s["total_bytes"] - s["done_bytes"]) / max(rate, 1))
        return s

    def _set(self, **kw):
        with self.lock:
            self.state.update(kw)

    def start(self, model_key="codes-1b-spider", with_spider=True):
        if self.state["running"]:
            return False
        self._set(running=True, finished=False, error=None, phase="checking", message="Checking this computer",
                  done_bytes=0, total_bytes=0, started=time.time())
        threading.Thread(target=self._run, args=(model_key, with_spider), daemon=True).start()
        return True

    def _run(self, model_key, with_spider):
        try:
            repo, label, size = MODELS[model_key]
            if not model_installed(model_key):
                if size and shutil.disk_usage(app_dir()).free < size * 1.15:
                    raise RuntimeError(f"Not enough free disk space: {label} needs about {size/1e9:.1f} GB.")
                self._download_model(repo, label, model_key)
            if with_spider and not spider_installed():
                self._download_spider()
            self._set(phase="done", message="Ready", finished=True, running=False)
        except Exception as exc:  # noqa: BLE001 - shown to the user
            self._set(phase="error", error=str(exc).splitlines()[0][:400], running=False)

    def _download_model(self, repo, label, key):
        from huggingface_hub import HfApi, snapshot_download
        from tqdm.auto import tqdm
        import fnmatch

        info = HfApi().model_info(repo, files_metadata=True)
        patterns = BASE_FILES + weight_patterns(info.siblings)
        files = [s for s in info.siblings if any(fnmatch.fnmatch(s.rfilename, p) for p in patterns)]
        total = sum(s.size or 0 for s in files)
        self._set(phase="model", message=f"Downloading {label}", total_bytes=total, done_bytes=0,
                  started=time.time())
        job = self

        class Progress(tqdm):          # huggingface_hub reports bytes through tqdm
            def update(self, n=1):
                if getattr(self, "unit", "") == "B" and n:
                    with job.lock:
                        job.state["done_bytes"] = min(job.state["total_bytes"], job.state["done_bytes"] + n)
                return super().update(n)

        snapshot_download(repo, local_dir=model_path(key), allow_patterns=patterns, tqdm_class=Progress)
        self._set(done_bytes=total)

    def _download_spider(self):
        from huggingface_hub import hf_hub_download
        self._set(phase="spider", message="Downloading sample databases (Spider, from Hugging Face)",
                  done_bytes=0, total_bytes=0, started=time.time())
        dest = os.path.join(data_dir(), "spider_full")
        z = hf_hub_download("HAL-9001/spider-databases", "spider_data.zip", repo_type="dataset", local_dir=dest)
        self._set(message="Unpacking sample databases")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        os.remove(z)
