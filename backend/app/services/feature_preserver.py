from __future__ import annotations

import cv2
import numpy as np


def preserve_features(
    grayscale: np.ndarray,
    grid_width: int,
    grid_height: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Temporarily expand thin features before grid mapping.
    Returns expanded grayscale image and a binary expansion mask.
    """
    h, w = grayscale.shape
    scale = max(w / grid_width, h / grid_height, 1.0)
    kernel_size = max(1, int(round(scale * 0.5)))
    if kernel_size % 2 == 0:
        kernel_size += 1

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    _, binary = cv2.threshold(grayscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    dilated = cv2.dilate(binary, kernel, iterations=1)
    mask = (dilated != binary).astype(np.uint8) * 255

    expanded = grayscale.copy()
    expanded[mask > 0] = np.minimum(expanded[mask > 0] + 40, 255)

    return expanded, mask
