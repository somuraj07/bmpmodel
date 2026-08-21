from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.services.saree_print import estimate_print_colors


@dataclass
class DesignAnalysis:
    is_raw_photo: bool
    unique_colors: int
    estimated_design_colors: int
    cropped: bool
    bbox: tuple[int, int, int, int]  # x, y, w, h


def _unique_color_count(rgb: np.ndarray) -> int:
    flat = rgb.reshape(-1, 3)
    if flat.shape[0] > 250_000:
        rng = np.random.default_rng(7)
        flat = flat[rng.choice(flat.shape[0], 250_000, replace=False)]
    return int(np.unique(flat, axis=0).shape[0])


def _paper_mask(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    return (val > 230) & (sat < 28)


def _crop_design(rgb: np.ndarray) -> tuple[np.ndarray, bool, tuple[int, int, int, int]]:
    h, w = rgb.shape[:2]
    paper = _paper_mask(rgb)
    bbox = (0, 0, w, h)
    margin = max(6, min(h, w) // 20)
    border = np.concatenate(
        [
            paper[:margin, :].ravel(),
            paper[-margin:, :].ravel(),
            paper[:, :margin].ravel(),
            paper[:, -margin:].ravel(),
        ]
    )
    interior = paper[margin : h - margin, margin : w - margin]
    if interior.size == 0:
        return rgb, False, bbox
    # Only crop when the FRAME is paper, not when white is part of the motif.
    if float(np.mean(border)) < 0.45 or float(np.mean(interior)) > 0.35:
        return rgb, False, bbox

    design = (~paper).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    design = cv2.morphologyEx(design, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(design, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return rgb, False, bbox

    contour = max(contours, key=cv2.contourArea)
    x, y, bw, bh = cv2.boundingRect(contour)
    if bw * bh < 0.18 * h * w:
        return rgb, False, bbox

    pad_x = max(2, int(round(bw * 0.02)))
    pad_y = max(2, int(round(bh * 0.02)))
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(w, x + bw + pad_x)
    y1 = min(h, y + bh + pad_y)
    return rgb[y0:y1, x0:x1], True, (x0, y0, x1 - x0, y1 - y0)


def _estimate_design_colors(rgb: np.ndarray, cap: int = 16) -> int:
    """
    Count colors that occupy a meaningful area after coarse quantization.
    This matches weaving BMPs (typically 7–16 shuttle colors).
    """
    step = 32
    coarse = ((rgb.astype(np.uint16) + step // 2) // step * step).clip(0, 255).astype(np.uint8)
    flat = coarse.reshape(-1, 3)
    colors, counts = np.unique(flat, axis=0, return_counts=True)
    keep = counts >= max(8, int(flat.shape[0] * 0.004))
    n = int(np.count_nonzero(keep))
    return int(np.clip(n, 6, cap))


def analyze_and_prepare(rgb: np.ndarray) -> tuple[np.ndarray, DesignAnalysis]:
    """
    Inspect a raw photo/scan and prepare it as a weaving design:
    crop paper background, flatten photo grain, estimate shuttle palette size.
    """
    unique = _unique_color_count(rgb)
    cropped_rgb, cropped, bbox = _crop_design(rgb)
    gray = cv2.cvtColor(cropped_rgb, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    is_raw = unique > 2500 or sharpness < 80.0

    prepared = cropped_rgb
    # Do not bilateral-smooth: it smears small ink accents (teal dots, leaf tips).

    estimated = estimate_print_colors(prepared)
    analysis = DesignAnalysis(
        is_raw_photo=is_raw,
        unique_colors=unique,
        estimated_design_colors=estimated,
        cropped=cropped,
        bbox=bbox,
    )
    return prepared, analysis
