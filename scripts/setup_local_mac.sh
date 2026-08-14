#!/usr/bin/env bash
# QueryGenie — local setup for Apple Silicon (M-series) macOS
#
# Sets up a virtual environment capable of running the Tier 1 smoke test
# (CodeS-1B inference via the MPS backend) and all local development work.
#
# NOTE: this is intentionally NOT the anchor paper's exact environment.
# The CodeS repository pins CUDA-specific packages (pytorch-cuda 11.7,
# bitsandbytes, deepspeed) that cannot run on Apple Silicon. Faithful
# Tier 2 reproduction runs must be performed on a CUDA machine or Colab.
# Every deviation here must be recorded in the reproducibility report.
#
# Usage:  bash scripts/setup_local_mac.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT_ROOT/.venv"

echo "=============================================="
echo " QueryGenie — local environment setup (macOS) "
echo "=============================================="
echo

# ---------------------------------------------------------------- checks
echo "[1/5] Checking system..."
ARCH="$(uname -m)"
echo "      architecture : $ARCH"
if [[ "$ARCH" != "arm64" ]]; then
  echo "      WARNING: not Apple Silicon. MPS acceleration will be unavailable;"
  echo "               inference will fall back to CPU and be considerably slower."
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 not found. Install it from https://www.python.org or via Homebrew."
  exit 1
fi
PYV="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "      python       : $PYV"

FREE_GB="$(df -g "$PROJECT_ROOT" | awk 'NR==2 {print $4}')"
echo "      free disk    : ${FREE_GB} GB"
if [[ "${FREE_GB:-0}" -lt 10 ]]; then
  echo "      WARNING: less than 10 GB free. The CodeS-1B weights are roughly 2-3 GB."
fi
echo

# ---------------------------------------------------------------- venv
echo "[2/5] Creating virtual environment at .venv ..."
if [[ -d "$VENV" ]]; then
  echo "      already exists — reusing"
else
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip --quiet
echo "      done"
echo

# ---------------------------------------------------------------- deps
echo "[3/5] Installing dependencies (this may take a few minutes)..."
pip install --quiet \
  torch \
  transformers \
  accelerate \
  sentencepiece \
  sqlparse \
  datasets \
  pandas \
  tqdm \
  jupyter \
  ipykernel
echo "      done"
echo

# ---------------------------------------------------------------- verify
echo "[4/5] Verifying PyTorch and the MPS backend..."
python - <<'PY'
import torch, platform
print(f"      torch            : {torch.__version__}")
print(f"      platform         : {platform.platform()}")
mps = torch.backends.mps.is_available()
print(f"      MPS available    : {mps}")
if mps:
    print("      -> GPU acceleration enabled (Apple Silicon)")
else:
    print("      -> falling back to CPU; expect slower inference")
PY
echo

# ---------------------------------------------------------------- kernel
echo "[5/5] Registering Jupyter kernel 'querygenie' ..."
python -m ipykernel install --user --name querygenie --display-name "QueryGenie (local)" >/dev/null 2>&1
echo "      done"
echo

echo "=============================================="
echo " Setup complete."
echo
echo " Next steps:"
echo "   source .venv/bin/activate"
echo "   python scripts/smoke_test.py"
echo
echo " The first run downloads the CodeS-1B weights (~2-3 GB)."
echo "=============================================="
