"""
Build every logo asset from the two originals in desktop/assets/brand/source/:

    logo.png             the Q mark
    logo with text.png   the mark with the "QueryGenie" wordmark

Outputs (all regenerable - run from the repository root):
    desktop/assets/brand/logo-mark.png            cleaned and trimmed mark
    desktop/assets/brand/logo-wordmark.png        cleaned and trimmed wordmark (for light backgrounds)
    desktop/assets/brand/logo-wordmark-dark.png   same with "Query" in light ink (for dark backgrounds)
    desktop/ui/brand/*.png                        small copies used by the app's interface
    desktop/assets/icon-1024.png, QueryGenie.icns, QueryGenie.ico   the app icon

    python desktop/assets/brand/make_brand_assets.py
"""
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "source")
ASSETS = os.path.dirname(HERE)
UI = os.path.join(os.path.dirname(ASSETS), "ui", "brand")
DARK_INK = (242, 242, 245)          # --ink in dark mode
TEXT_SPLIT_X = 600                  # in the original wordmark, the text starts right of this column


def clean(img: Image.Image, pad: int = 8):
    """Drop the nearly invisible specks left by background removal, then trim to the artwork.
    Returns the image and the x offset of the crop (to map positions from the original)."""
    a = np.array(img.convert("RGBA"))
    a[a[..., 3] < 24] = 0
    out = Image.fromarray(a)
    l, t, r, b = out.getbbox()
    left = max(0, l - pad)
    return out.crop((left, max(0, t - pad), min(out.width, r + pad), min(out.height, b + pad))), left


def dark_variant(word: Image.Image, split_x: int) -> Image.Image:
    """Recolour the navy "Query" to light ink; the mark and the blue "Genie" stay as they are."""
    a = np.array(word).astype(np.int32)
    rgb, alpha = a[..., :3], a[..., 3]
    navy = (rgb[..., 0] < 70) & (rgb[..., 1] < 80) & (rgb[..., 2] < 120) & (alpha > 0)
    navy[:, :split_x] = False
    a[navy, 0], a[navy, 1], a[navy, 2] = DARK_INK
    return Image.fromarray(a.astype(np.uint8))


def fit_height(img: Image.Image, h: int) -> Image.Image:
    return img.resize((round(img.width * h / img.height), h), Image.LANCZOS)


def fit_box(img: Image.Image, s: int) -> Image.Image:
    k = s / max(img.size)
    return img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)


def app_icon(mark: Image.Image) -> Image.Image:
    """macOS-style icon: the mark on a white rounded tile (824 px tile on a 1024 canvas) with a soft shadow."""
    S, T = 1024, 824
    off = (S - T) // 2
    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((off, off + 12, off + T, off + T + 12), radius=185, fill=(0, 17, 68, 70))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = np.linspace(255, 238, T).astype(np.uint8)                     # white to a faint cool grey
    fill = np.dstack([np.repeat(grad[:, None], T, 1)] * 3 + [np.full((T, T), 255, np.uint8)])
    fill[..., 2] = np.minimum(255, fill[..., 2].astype(int) + 6).astype(np.uint8)
    mask = Image.new("L", (T, T), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, T - 1, T - 1), radius=185, fill=255)
    tile.paste(Image.fromarray(fill, "RGBA"), (off, off), mask)
    canvas.alpha_composite(tile)
    m = fit_box(mark, round(T * 0.72))
    canvas.alpha_composite(m, (off + (T - m.width) // 2, off + (T - m.height) // 2 + 6))
    return canvas


def main():
    os.makedirs(UI, exist_ok=True)
    mark, _ = clean(Image.open(os.path.join(SRC, "logo.png")))
    word, left = clean(Image.open(os.path.join(SRC, "logo with text.png")))
    word_dark = dark_variant(word, TEXT_SPLIT_X - left)

    mark.save(os.path.join(HERE, "logo-mark.png"), optimize=True)
    word.save(os.path.join(HERE, "logo-wordmark.png"), optimize=True)
    word_dark.save(os.path.join(HERE, "logo-wordmark-dark.png"), optimize=True)

    # Interface copies at 2x the size they are shown at.
    fit_box(mark, 160).save(os.path.join(UI, "mark.png"), optimize=True)
    fit_height(word, 112).save(os.path.join(UI, "wordmark.png"), optimize=True)
    fit_height(word_dark, 112).save(os.path.join(UI, "wordmark-dark.png"), optimize=True)

    icon = app_icon(mark)
    icon.save(os.path.join(ASSETS, "icon-1024.png"), optimize=True)
    icon.save(os.path.join(ASSETS, "QueryGenie.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    if shutil.which("iconutil"):                                           # macOS only
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, "QueryGenie.iconset")
            os.makedirs(iconset)
            for s in (16, 32, 128, 256, 512):
                icon.resize((s, s), Image.LANCZOS).save(os.path.join(iconset, f"icon_{s}x{s}.png"))
                icon.resize((s * 2, s * 2), Image.LANCZOS).save(os.path.join(iconset, f"icon_{s}x{s}@2x.png"))
            subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ASSETS, "QueryGenie.icns")], check=True)
    print("brand assets written")


if __name__ == "__main__":
    main()
