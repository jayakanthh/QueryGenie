#!/usr/bin/env python3
"""
Build 4-bit MLX weights for a CodeS size so it runs fast + small on Apple Silicon.

CodeS ships as pytorch_model.bin (no safetensors), and mlx-lm needs safetensors,
so this first re-saves the HF model as fp16 safetensors, then quantizes to 4-bit MLX.

Usage:
    python scripts/convert_mlx.py 3b          # -> mlx_models/codes-3b-4bit
    python scripts/convert_mlx.py 1b
    python scripts/convert_mlx.py 7b          # heavy: see the RAM note below

RAM note: the re-save step loads the full model in fp16 (~2 GB per 1B params). 1B/3B
are fine on a 16 GB Mac; 7B (~14 GB) is very tight and 15B won't fit — build those on
a bigger machine (or Colab) and copy the small mlx_models/codes-*-4bit folder down.
The 4-bit model itself runs fine locally once built (7B 4-bit is ~4 GB).
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Convert a CodeS size to 4-bit MLX")
    ap.add_argument("size", choices=["1b", "3b", "7b", "15b"], help="CodeS scale")
    ap.add_argument("--variant", choices=["base", "spider", "bird"], default="base",
                    help="base = pre-trained; spider/bird = fine-tuned (SFT) checkpoints")
    ap.add_argument("--bits", type=int, default=4)
    ap.add_argument("--group-size", type=int, default=64)
    args = ap.parse_args()

    suffix = "" if args.variant == "base" else f"-{args.variant}"
    hf_id = f"seeklhy/codes-{args.size}{suffix}"
    tag = f"codes-{args.size}{suffix}"
    st_dir = os.path.join(REPO_ROOT, "mlx_models", f"_hf_{tag}_st")
    out_dir = os.path.join(REPO_ROOT, "mlx_models", f"{tag}-{args.bits}bit")

    if os.path.isdir(out_dir):
        print(f"[skip] {out_dir} already exists")
        return 0

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not os.path.exists(os.path.join(st_dir, "model.safetensors")) and \
       not os.path.exists(os.path.join(st_dir, "model.safetensors.index.json")):
        print(f"[1/2] re-saving {hf_id} as fp16 safetensors ...")
        model = AutoModelForCausalLM.from_pretrained(
            hf_id, torch_dtype=torch.float16, low_cpu_mem_usage=True)
        model.save_pretrained(st_dir, safe_serialization=True)
        AutoTokenizer.from_pretrained(hf_id).save_pretrained(st_dir)
        del model
    else:
        print(f"[1/2] safetensors already present in {st_dir}")

    print(f"[2/2] quantizing to {args.bits}-bit MLX ...")
    from mlx_lm import convert
    convert(hf_path=st_dir, mlx_path=out_dir, quantize=True,
            q_bits=args.bits, q_group_size=args.group_size)

    print(f"\ndone -> {os.path.relpath(out_dir, REPO_ROOT)}")
    print("You can delete the intermediate", os.path.relpath(st_dir, REPO_ROOT), "to save disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
