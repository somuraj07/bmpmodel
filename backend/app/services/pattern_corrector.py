from __future__ import annotations

import cv2
import numpy as np


def correct_pattern(grayscale_grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Detect and repair broken lines, gaps, and isolated pixels on the weaving grid.
    Returns corrected grayscale grid and a change map.
    """
    original = grayscale_grid.copy()
    corrected = grayscale_grid.copy()

    # Binarize for structural analysis
    _, binary = cv2.threshold(corrected, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Close small gaps in lines (morphological closing)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)

    # Remove isolated single pixels (salt noise)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    cleaned = closed.copy()
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area == 1:
            cleaned[labels == i] = 0

    # Bridge thin breaks using dilation + erosion (opening inverse)
    bridge_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    bridged = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, bridge_kernel, iterations=1)

    # Restore grayscale values: dark regions stay dark, light stay light
    threshold = int(np.median(grayscale_grid))
    corrected[bridged > 127] = max(threshold + 30, 200)
    corrected[bridged <= 127] = min(threshold - 30, 55)

    change_map = (corrected.astype(np.int16) - original.astype(np.int16)).astype(np.int8)
    return corrected, change_map


def restore_features(
    corrected: np.ndarray,
    expansion_mask: np.ndarray,
    original_grayscale: np.ndarray,
) -> np.ndarray:
    """Selectively restore original structure in non-expanded areas."""
    if expansion_mask.shape != corrected.shape:
        mask = cv2.resize(
            expansion_mask,
            (corrected.shape[1], corrected.shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )
        orig = cv2.resize(
            original_grayscale,
            (corrected.shape[1], corrected.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    else:
        mask = expansion_mask
        orig = original_grayscale

    restored = corrected.copy()
    non_expanded = mask == 0
    restored[non_expanded] = orig[non_expanded]
    return restored
