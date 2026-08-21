from __future__ import annotations

from io import BytesIO

import numpy as np
from PIL import Image


def decode_to_rgb(file_bytes: bytes) -> np.ndarray:
    """Decode any supported image into a uint8 RGB numpy array (H, W, 3)."""
    with Image.open(BytesIO(file_bytes)) as img:
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            rgb = background
        elif img.mode == "P":
            rgb = img.convert("RGBA")
            background = Image.new("RGB", rgb.size, (255, 255, 255))
            background.paste(rgb, mask=rgb.split()[3])
            rgb = background
        elif img.mode != "RGB":
            rgb = img.convert("RGB")
        else:
            rgb = img

        return np.asarray(rgb, dtype=np.uint8)
