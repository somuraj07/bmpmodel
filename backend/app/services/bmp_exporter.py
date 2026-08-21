from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


def export_bmp(rgb: np.ndarray, bit_depth: int = 24, indexed: bool = False) -> bytes:
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("BMP export requires an RGB image array.")

    if not indexed:
        img = Image.fromarray(rgb, mode="RGB")
        buffer = BytesIO()
        img.save(buffer, format="BMP")
        return buffer.getvalue()

    palette, inverse = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    n = int(palette.shape[0])
    index = inverse.reshape(rgb.shape[:2]).astype(np.uint8)
    pal_img = Image.fromarray(index, mode="P")
    pal_bytes = bytearray(768)
    for i, color in enumerate(palette[:256]):
        pal_bytes[i * 3 : i * 3 + 3] = bytes(int(c) for c in color)
    pal_img.putpalette(bytes(pal_bytes))
    buffer = BytesIO()
    pal_img.save(buffer, format="BMP")
    return buffer.getvalue()
    if rgb.dtype != np.uint8:
        rgb = np.clip(rgb, 0, 255).astype(np.uint8)

    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("BMP export requires an RGB image array.")

    img = Image.fromarray(rgb, mode="RGB")
    if indexed:
        unique = int(np.unique(rgb.reshape(-1, 3), axis=0).shape[0])
        unique = min(256, max(2, unique))
        img = img.quantize(colors=unique, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buffer = BytesIO()
    img.save(buffer, format="BMP")
    return buffer.getvalue()


def export_preview_png(rgb: np.ndarray, scale: int = 1) -> bytes:
    """Lossless PNG preview — no optimization, no compression artifacts."""
    if scale > 1:
        h, w = rgb.shape[:2]
        img = Image.fromarray(rgb, mode="RGB")
        img = img.resize((w * scale, h * scale), Image.NEAREST)
    else:
        img = Image.fromarray(rgb, mode="RGB")

    buffer = BytesIO()
    img.save(buffer, format="PNG", compress_level=0, optimize=False)
    return buffer.getvalue()
