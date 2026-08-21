from __future__ import annotations

import cv2
import numpy as np


def reconstruct_colors(
    original_rgb: np.ndarray,
    corrected_grayscale: np.ndarray,
) -> np.ndarray:
    """
    Reconstruct final RGB from original source using nearest-neighbor sampling.
    Avoids blending so each grid pixel stays a solid source color.
    """
    gh, gw = corrected_grayscale.shape[:2]
    oh, ow = original_rgb.shape[:2]

    if (gh, gw) == (oh, ow):
        return original_rgb.copy()

    return cv2.resize(original_rgb, (gw, gh), interpolation=cv2.INTER_NEAREST)
