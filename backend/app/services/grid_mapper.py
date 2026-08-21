from __future__ import annotations

import cv2
import numpy as np


def map_to_grid(
    image: np.ndarray,
    grid_width: int,
    grid_height: int,
) -> np.ndarray:
    """
    Grid-aware nearest-neighbor mapping to discrete weaving grid.
    Preserves sharp pixel boundaries — no interpolation blur.
    """
    return cv2.resize(
        image,
        (grid_width, grid_height),
        interpolation=cv2.INTER_NEAREST,
    )


def upscale_grid_to_display(
    grid_image: np.ndarray,
    display_width: int,
    display_height: int,
) -> np.ndarray:
    """Upscale grid for preview using nearest-neighbor (pixel-perfect)."""
    return cv2.resize(
        grid_image,
        (display_width, display_height),
        interpolation=cv2.INTER_NEAREST,
    )
