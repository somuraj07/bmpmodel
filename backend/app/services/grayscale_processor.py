from __future__ import annotations

import numpy as np


def rgb_to_grayscale(rgb: np.ndarray) -> np.ndarray:
    """Convert RGB to luminance grayscale using ITU-R BT.601 weights."""
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    return (0.299 * r + 0.587 * g + 0.114 * b).astype(np.uint8)
