from __future__ import annotations

import cv2
import numpy as np


def _as_palette(palette: np.ndarray) -> np.ndarray:
    pal = np.asarray(palette, dtype=np.uint8)
    if pal.size == 0:
        return np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8)
    return pal.reshape(-1, 3)


def _rgb_to_lab(rgb_flat: np.ndarray) -> np.ndarray:
    img = rgb_flat.reshape(-1, 1, 3).astype(np.uint8)
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return lab.reshape(-1, 3).astype(np.float32)


def _assign_nearest_lab(pixels_flat: np.ndarray, palette: np.ndarray) -> np.ndarray:
    palette = _as_palette(palette)
    pix_lab = _rgb_to_lab(pixels_flat)
    pal_lab = _rgb_to_lab(palette)
    diffs = pix_lab[:, None, :] - pal_lab[None, :, :]
    dist = np.sum(diffs * diffs, axis=2)
    return np.argmin(dist, axis=1).astype(np.int32)


def _build_palette_kmeans(
    rgb_flat: np.ndarray,
    k: int,
    max_samples: int = 100_000,
    attempts: int = 10,
    max_iter: int = 100,
) -> np.ndarray:
    samples = rgb_flat.astype(np.float32)
    if samples.shape[0] > max_samples:
        rng = np.random.default_rng(42)
        idx = rng.choice(samples.shape[0], max_samples, replace=False)
        samples = samples[idx]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, max_iter, 0.1)
    _, _, centers = cv2.kmeans(samples, k, None, criteria, attempts, cv2.KMEANS_PP_CENTERS)
    return np.clip(np.round(centers), 0, 255).astype(np.uint8)


def _snap_palette_endpoints(palette: np.ndarray) -> np.ndarray:
    """
    Collapse near-white / near-black / near-neutral edge shades so zoomed pixels
    look like crisp blocks instead of soft anti-aliased fringes.
    """
    pal = _as_palette(palette).copy()
    for i, color in enumerate(pal):
        cmin = int(color.min())
        cmax = int(color.max())
        spread = cmax - cmin

        if cmax >= 240 and spread <= 28:
            pal[i] = np.array([255, 255, 255], dtype=np.uint8)
        elif cmax <= 28:
            pal[i] = np.array([0, 0, 0], dtype=np.uint8)
        elif spread <= 18:
            mean = int(np.round(np.mean(color) / 16.0) * 16)
            mean = max(0, min(255, mean))
            pal[i] = np.array([mean, mean, mean], dtype=np.uint8)
    return pal


def _edge_mask(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    return edges > 0


def _majority_smooth_non_edge(labels: np.ndarray, protected: np.ndarray, passes: int = 2) -> np.ndarray:
    """
    Smooth noisy fill regions while preserving real outlines.
    Only non-edge pixels are updated, and only when they disagree with most
    of their 8-neighbourhood.
    """
    h, w = labels.shape
    n_labels = int(labels.max()) + 1

    for _ in range(passes):
        padded = np.pad(labels, 1, mode="edge")
        neighbours = np.empty((h, w, 9), dtype=np.int32)
        idx = 0
        for dy in range(3):
            for dx in range(3):
                neighbours[:, :, idx] = padded[dy : dy + h, dx : dx + w]
                idx += 1

        current = labels[:, :, None]
        same_count = np.sum(neighbours == current, axis=2)
        update_mask = (same_count <= 3) & (~protected)
        if not np.any(update_mask):
            break

        votes = np.zeros((h, w, n_labels), dtype=np.int32)
        rows = np.arange(h)[:, None]
        cols = np.arange(w)[None, :]
        for i in range(9):
            np.add.at(votes, (rows, cols, neighbours[:, :, i]), 1)
        majority = np.argmax(votes, axis=2).astype(np.int32)
        labels = np.where(update_mask, majority, labels)

    return labels


def quantize_to_solid_pixels(
    rgb: np.ndarray,
    max_colors: int = 32,
    block_size: int = 1,  # kept for API compat, not used
    strict: bool = False,
) -> tuple[np.ndarray, int]:
    """
    Minimal, design-preserving solid-pixel pipeline:
      1. Tiny JPEG denoise only (snap channels to nearest multiple of 8)
         — removes half-tone noise without touching actual design pixels
      2. K-means palette in LAB space
      3. Assign every pixel to nearest palette color
      4. Remove true single-pixel isolated specks only (4-connectivity)
         — does NOT snap or merge clusters of 2+ pixels

    This keeps the design 100% intact while making every pixel solid.
    """
    h, w = rgb.shape[:2]

    edge_mask = _edge_mask(rgb)
    edge_density = float(np.mean(edge_mask))

    # Weaving BMP style: keep a small solid palette like production files (7–16 colors).
    if strict:
        step = 16
        adaptive_max_colors = max_colors
        max_samples = 200_000
        attempts = 14
        max_iter = 120
    elif edge_density > 0.18:
        step = 8
        adaptive_max_colors = max(max_colors, 128)
        max_samples = 300_000
        attempts = 16
        max_iter = 140
    elif edge_density > 0.10:
        step = 8
        adaptive_max_colors = max(max_colors, 96)
        max_samples = 200_000
        attempts = 14
        max_iter = 120
    else:
        step = 16
        adaptive_max_colors = max_colors
        max_samples = 100_000
        attempts = 10
        max_iter = 100

    # Step 1: denoise before palette fitting.
    denoised = ((rgb.astype(np.uint16) + step // 2) // step * step).clip(0, 255).astype(np.uint8)

    # Step 2: build palette from all pixels
    flat = denoised.reshape(-1, 3)
    n_unique = int(np.unique(flat, axis=0).shape[0])
    k = min(adaptive_max_colors, n_unique)
    if k < 2:
        k = 2

    palette = _build_palette_kmeans(
        flat,
        k,
        max_samples=max_samples,
        attempts=attempts,
        max_iter=max_iter,
    )
    palette = _snap_palette_endpoints(palette)
    palette = _as_palette(palette)

    # Step 3: assign every pixel to nearest palette color in LAB
    labels = _assign_nearest_lab(flat, palette).reshape(h, w)

    # Step 4: multi-pass edge-fringe removal for razor-sharp pixel borders.
    # Pass type A (8 passes): kill pixels matching NONE of 4 direct neighbours.
    # Pass type B (4 passes): kill pixels matching only 1 of 4 neighbours.
    # Together these eliminate all anti-alias transition pixels at edges.
    n_pal = int(labels.max()) + 1
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]

    def _majority_of_neighbours(lbl):
        up = np.roll(lbl, -1, axis=0)
        dn = np.roll(lbl,  1, axis=0)
        lt = np.roll(lbl,  1, axis=1)
        rt = np.roll(lbl, -1, axis=1)
        neighbours = np.stack([up, dn, lt, rt], axis=2)
        same = (up == lbl).astype(np.int32) + (dn == lbl).astype(np.int32) + \
               (lt == lbl).astype(np.int32) + (rt == lbl).astype(np.int32)
        n = int(lbl.max()) + 1
        votes = np.zeros((h, w, n), dtype=np.int32)
        for i in range(4):
            np.add.at(votes, (rows, cols, neighbours[:, :, i]), 1)
        majority = np.argmax(votes, axis=2).astype(np.int32)
        return same, majority

    protected = edge_mask

    # Type A: match 0 of 4 neighbours → definitely a fringe pixel
    for _ in range(8):
        same, majority = _majority_of_neighbours(labels)
        mask = (same == 0) & (~protected)
        if not np.any(mask):
            break
        labels = np.where(mask, majority, labels)

    # Type B: match only 1 of 4 neighbours → likely a 1-pixel-wide fringe
    for _ in range(4):
        same, majority = _majority_of_neighbours(labels)
        mask = (same <= 1) & (~protected)
        if not np.any(mask):
            break
        labels = np.where(mask, majority, labels)

    # Step 5: flatten noisy fill areas in large/detailed designs while
    # preserving true edges. This gives cleaner solid pixel blocks.
    if edge_density > 0.10:
        labels = _majority_smooth_non_edge(labels, protected=protected, passes=3)

    result = palette[labels]
    actual_colors = int(np.unique(result.reshape(-1, 3), axis=0).shape[0])
    return result, actual_colors


def clean_pixels(
    rgb: np.ndarray,
    max_colors: int = 32,
) -> tuple[np.ndarray, int]:
    return quantize_to_solid_pixels(rgb, max_colors=max_colors)
