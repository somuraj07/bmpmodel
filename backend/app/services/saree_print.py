from __future__ import annotations

import cv2
import numpy as np


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def _delta_e(a: np.ndarray, b: np.ndarray) -> float:
    dL = (float(a[0]) - float(b[0])) * (100.0 / 255.0)
    da = float(a[1]) - float(b[1])
    db = float(a[2]) - float(b[2])
    return float(np.sqrt(dL * dL + da * da + db * db))


def _chroma(lab: np.ndarray) -> float:
    return float(np.hypot(float(lab[1]) - 128.0, float(lab[2]) - 128.0))


def _hue(lab: np.ndarray) -> float:
    return float(np.arctan2(float(lab[2]) - 128.0, float(lab[1]) - 128.0))


def _hue_diff(a: np.ndarray, b: np.ndarray) -> float:
    d = abs(_hue(a) - _hue(b))
    return float(min(d, 2 * np.pi - d))


def _kmeans_lab(lab: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray, float]:
    samples = lab.reshape(-1, 3)
    k = max(2, min(int(k), max(2, samples.shape[0] - 1)))
    # Keep fit set small — free Render is ~512MB and times out ~100s.
    max_fit = 40_000
    if samples.shape[0] > max_fit:
        rng = np.random.default_rng(5)
        fit = samples[rng.choice(samples.shape[0], max_fit, replace=False)]
    else:
        fit = samples
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.4)
    compactness, _, centers = cv2.kmeans(
        fit, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    # Chunked assign — avoids one huge (N x K) temp array.
    labels = np.empty(samples.shape[0], dtype=np.int32)
    step = 50_000
    centers_f = centers.astype(np.float32)
    for i in range(0, samples.shape[0], step):
        chunk = samples[i : i + step]
        diffs = chunk[:, None, :] - centers_f[None, :, :]
        labels[i : i + step] = np.argmin(np.sum(diffs * diffs, axis=2), axis=1)
    return centers_f, labels.reshape(lab.shape[:2]), float(compactness)


def _best_k(lab: np.ndarray, chroma_frac: float) -> int:
    # Fast heuristic — no multi-k elbow (that alone can take minutes on free tier).
    if chroma_frac >= 0.35:
        return 10
    if chroma_frac >= 0.20:
        return 8
    if chroma_frac >= 0.08:
        return 5
    return 4


def estimate_print_colors(rgb: np.ndarray) -> int:
    h, w = rgb.shape[:2]
    scale = max(h, w)
    if scale > 400:
        f = 400 / scale
        rgb = cv2.resize(rgb, (max(8, int(w * f)), max(8, int(h * f))), interpolation=cv2.INTER_AREA)
    denoise = cv2.medianBlur(rgb, 3)
    lab = _to_lab(denoise)
    chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
    return _best_k(lab, float(np.mean(chroma > 16)))


def _agglomerative_merge(
    centers: np.ndarray,
    labels: np.ndarray,
    *,
    max_de: float,
    max_dl: float,
    same_hue_de: float,
    same_hue_dl: float,
) -> np.ndarray:
    pal = [c.copy() for c in centers]
    n = len(pal)
    counts = np.bincount(labels.ravel(), minlength=n).astype(np.float64)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    while True:
        roots = sorted({find(i) for i in range(n) if counts[find(i)] > 0})
        best = None
        for ai, a in enumerate(roots):
            for b in roots[ai + 1 :]:
                de = _delta_e(pal[a], pal[b])
                dL = abs(float(pal[a][0]) - float(pal[b][0]))
                chroma_ok = _chroma(pal[a]) >= 12 and _chroma(pal[b]) >= 12
                hue_close = chroma_ok and _hue_diff(pal[a], pal[b]) < 0.40
                if hue_close:
                    if de > same_hue_de or dL > same_hue_dl:
                        continue
                else:
                    if de > max_de or dL > max_dl:
                        continue
                    if chroma_ok and _hue_diff(pal[a], pal[b]) > 0.55:
                        continue
                if best is None or de < best[0]:
                    best = (de, a, b)
        if best is None:
            break
        _, a, b = best
        total = counts[a] + counts[b]
        pal[a] = (pal[a] * counts[a] + pal[b] * counts[b]) / max(1.0, total)
        counts[a] = total
        counts[b] = 0
        parent[b] = a

    roots = []
    seen = set()
    for i in range(n):
        r = find(i)
        if r not in seen and counts[r] > 0:
            seen.add(r)
            roots.append(pal[r])
    return np.stack(roots, axis=0) if roots else centers


def _snap_neutral_mids(palette: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    chromas = np.array([_chroma(c) for c in palette])
    L = palette[:, 0]
    lights = [i for i in range(len(palette)) if L[i] >= 200 and chromas[i] < 16]
    darks = [i for i in range(len(palette)) if L[i] <= 95 and chromas[i] < 28]
    mids = [i for i in range(len(palette)) if 95 < L[i] < 200 and chromas[i] < 16]
    if not (lights and darks and mids):
        return palette, labels
    light_i, dark_i = lights[0], darks[0]
    thresh = (float(L[light_i]) + float(L[dark_i])) * 0.5
    new_labels = labels.copy()
    keep = np.ones(len(palette), dtype=bool)
    for i in mids:
        target = light_i if float(L[i]) >= thresh else dark_i
        new_labels[new_labels == i] = target
        keep[i] = False
    # compact ids
    mapping = np.full(len(palette), -1, dtype=np.int32)
    new_pal = []
    for old in range(len(palette)):
        if not keep[old]:
            continue
        mapping[old] = len(new_pal)
        new_pal.append(palette[old])
    for i in mids:
        mapping[i] = mapping[light_i if float(L[i]) >= thresh else dark_i]
    # labels currently still old ids for kept colors
    remapped = mapping[new_labels]
    return np.stack(new_pal, axis=0), remapped


def _recover_accents(lab: np.ndarray, palette: np.ndarray, labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
    assigned_chroma = np.array([_chroma(c) for c in palette], dtype=np.float32)
    pixel_assigned = assigned_chroma[labels]
    leftover = (chroma > 22) & (chroma > pixel_assigned + 10)
    if int(np.count_nonzero(leftover)) < max(24, int(lab.shape[0] * lab.shape[1] * 0.0025)):
        return palette, labels
    samples = lab[leftover]
    k = 1 if samples.shape[0] < 400 else 2
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.3)
    _, _, centers = cv2.kmeans(
        samples.reshape(-1, 3), k, None, criteria, 6, cv2.KMEANS_PP_CENTERS
    )
    new_pal = np.concatenate([palette, centers.astype(np.float32)], axis=0)
    diffs = lab.reshape(-1, 3)[:, None, :] - new_pal[None, :, :]
    new_labels = np.argmin(np.sum(diffs * diffs, axis=2), axis=1).reshape(lab.shape[:2])
    # Only allow leftover pixels to take the new accent inks.
    accent_ids = np.arange(len(palette), len(new_pal))
    allowed = leftover | np.isin(new_labels, np.arange(len(palette)))
    new_labels = np.where(np.isin(new_labels, accent_ids) & leftover, new_labels, labels)
    # Drop unused accents.
    used = np.unique(new_labels)
    mapping = {int(old): i for i, old in enumerate(used)}
    compact = np.vectorize(mapping.get)(new_labels)
    return new_pal[used], compact.astype(np.int32)


def _flatten_palette_rgb(palette_rgb: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat_mean = float(np.mean(hsv[:, :, 1]))
    val_mean = float(np.mean(hsv[:, :, 2]))
    out = palette_rgb.copy()
    brightness = out.astype(np.int16).sum(axis=1)
    light_i = int(np.argmax(brightness))
    light = out[light_i]
    spread = int(light.max()) - int(light.min())
    if int(light.min()) >= 210 and spread <= 50:
        out[light_i] = [255, 255, 255]
    elif int(light.min()) >= 245 and spread <= 12:
        out[light_i] = [255, 255, 255]
    elif val_mean >= 130 and sat_mean <= 80 and int(light.min()) >= 200 and spread <= 40:
        out[light_i] = [255, 255, 255]
    return out


def _majority_filter(labels: np.ndarray, passes: int = 1) -> np.ndarray:
    out = labels.astype(np.int32)
    h, w = out.shape
    n = int(out.max()) + 1
    for _ in range(passes):
        votes = np.zeros((h, w, n), dtype=np.uint16)
        rows = np.arange(h)[:, None]
        cols = np.arange(w)[None, :]
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                np.add.at(votes, (rows, cols, np.roll(np.roll(out, dy, 0), dx, 1)), 1)
        out = np.argmax(votes, axis=2).astype(np.int32)
    return out


def _prune_tiny_inks(
    palette: np.ndarray, labels: np.ndarray, min_frac: float = 0.002
) -> tuple[np.ndarray, np.ndarray]:
    n = len(palette)
    counts = np.bincount(labels.ravel(), minlength=n)
    total = max(1, int(labels.size))
    keep = []
    for i in range(n):
        if counts[i] >= max(40, int(total * min_frac)) or _chroma(palette[i]) >= 22:
            keep.append(i)
    if len(keep) == n or not keep:
        return palette, labels
    keep_arr = np.array(keep, dtype=np.int32)
    new_pal = palette[keep_arr]
    diffs = palette[:, None, :] - new_pal[None, :, :]
    remap = np.argmin(np.sum(diffs * diffs, axis=2), axis=1)
    return new_pal, remap[labels]


def _remove_specks(labels: np.ndarray, palette: np.ndarray | None = None) -> np.ndarray:
    up = np.roll(labels, -1, 0)
    dn = np.roll(labels, 1, 0)
    lt = np.roll(labels, 1, 1)
    rt = np.roll(labels, -1, 1)
    same = (
        (up == labels).astype(np.int32)
        + (dn == labels).astype(np.int32)
        + (lt == labels).astype(np.int32)
        + (rt == labels).astype(np.int32)
    )
    isolated = same == 0
    if np.any(isolated):
        neigh = np.stack([up, dn, lt, rt], axis=2)
        h, w = labels.shape
        n = int(labels.max()) + 1
        votes = np.zeros((h, w, n), dtype=np.int32)
        rows = np.arange(h)[:, None]
        cols = np.arange(w)[None, :]
        for i in range(4):
            np.add.at(votes, (rows, cols, neigh[:, :, i]), 1)
        majority = np.argmax(votes, axis=2).astype(np.int32)
        labels = np.where(isolated, majority, labels)

    cleaned = labels.copy()
    n = int(labels.max()) + 1
    for color in range(n):
        mask = (labels == color).astype(np.uint8)
        num, cc, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
        for cid in range(1, num):
            area = int(stats[cid, cv2.CC_STAT_AREA])
            chroma = _chroma(palette[color]) if palette is not None else 0.0
            limit = 4 if chroma >= 18 else 14
            if area > limit:
                continue
            ys, xs = np.where(cc == cid)
            if ys.size == 0:
                continue
            y0, y1 = max(0, ys.min() - 1), min(labels.shape[0], ys.max() + 2)
            x0, x1 = max(0, xs.min() - 1), min(labels.shape[1], xs.max() + 2)
            neighborhood = labels[y0:y1, x0:x1]
            border = neighborhood[cc[y0:y1, x0:x1] != cid]
            if border.size == 0:
                continue
            vals, cnts = np.unique(border, return_counts=True)
            cleaned[cc == cid] = int(vals[np.argmax(cnts)])
    return cleaned


def _relabel_to_palette(lab: np.ndarray, palette_lab: np.ndarray) -> np.ndarray:
    samples = lab.reshape(-1, 3)
    labels = np.empty(samples.shape[0], dtype=np.int32)
    step = 50_000
    pal = palette_lab.astype(np.float32)
    for i in range(0, samples.shape[0], step):
        chunk = samples[i : i + step]
        diffs = chunk[:, None, :] - pal[None, :, :]
        labels[i : i + step] = np.argmin(np.sum(diffs * diffs, axis=2), axis=1)
    return labels.reshape(lab.shape[:2])


def _collapse_uniform_blocks(rgb: np.ndarray) -> np.ndarray:
    """If the file is already NN-upscaled pixel art, recover 1 pixel per block."""
    h, w = rgb.shape[:2]
    # Skip on large photos — reshape+scan is expensive and rarely helps.
    if h * w > 900_000:
        return rgb
    for n in (8, 6, 4, 3, 2):
        if h % n or w % n:
            continue
        blocks = rgb.reshape(h // n, n, w // n, n, 3)
        # Sample check first
        ys = min(40, h // n)
        xs = min(40, w // n)
        sample = blocks[:ys, :, :xs, :, :]
        if float(np.all(sample == sample[:, :1, :, :1, :], axis=(1, 3)).mean()) < 0.90:
            continue
        frac = float(np.all(blocks == blocks[:, :1, :, :1, :], axis=(1, 3)).mean())
        if frac >= 0.90:
            return blocks[:, 0, :, 0].copy()
    return rgb


def _fast_unique_count(rgb: np.ndarray) -> int:
    flat = rgb.reshape(-1, 3)
    if flat.shape[0] > 80_000:
        rng = np.random.default_rng(3)
        flat = flat[rng.choice(flat.shape[0], 80_000, replace=False)]
    return int(np.unique(flat, axis=0).shape[0])


_PIXEL_CELL = {"soft": 2, "medium": 3, "hard": 4, "extreme": 6}


def to_saree_print_layout(
    rgb: np.ndarray,
    block_strength: str = "hard",
    color_count: int | None = None,
) -> tuple[np.ndarray, int]:
    """
    Mill BMP look: coarse grid → solid inks → nearest-neighbor squares.
    Tuned for free-tier hosts (fast, low memory).
    """
    rgb = _collapse_uniform_blocks(rgb)
    unique = _fast_unique_count(rgb)
    if unique <= 24:
        return rgb, unique

    cell = int(_PIXEL_CELL.get(block_strength, 4))
    h, w = rgb.shape[:2]
    # Cap working resolution so k-means stays under free Render limits.
    longest = max(h, w)
    if longest > 1400:
        f = 1400 / longest
        rgb = cv2.resize(
            rgb,
            (max(8, int(w * f)), max(8, int(h * f))),
            interpolation=cv2.INTER_AREA,
        )
        h, w = rgb.shape[:2]

    sw = max(8, w // cell)
    sh = max(8, h // cell)
    small = cv2.resize(rgb, (sw, sh), interpolation=cv2.INTER_AREA)

    lab = _to_lab(small)
    chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
    chroma_frac = float(np.mean(chroma > 16))
    k = int(color_count) if color_count else _best_k(lab, chroma_frac)
    k = int(np.clip(k, 3, 12))

    start_k = min(10, max(k, 8 if chroma_frac >= 0.25 else k))
    centers, labels, _ = _kmeans_lab(lab, start_k)
    merged_lab = _agglomerative_merge(
        centers,
        labels,
        max_de=10.5,
        max_dl=16,
        same_hue_de=18.0,
        same_hue_dl=36.0,
    )
    labels = _relabel_to_palette(lab, merged_lab)
    merged_lab, labels = _snap_neutral_mids(merged_lab, labels)
    merged_lab, labels = _prune_tiny_inks(merged_lab, labels, min_frac=0.001)

    palette_bgr = cv2.cvtColor(
        np.clip(merged_lab, 0, 255).astype(np.uint8).reshape(-1, 1, 3),
        cv2.COLOR_LAB2BGR,
    )
    palette_rgb = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3)
    palette_rgb = _flatten_palette_rgb(palette_rgb, small)
    small_q = palette_rgb[labels]

    out = cv2.resize(small_q, (sw * cell, sh * cell), interpolation=cv2.INTER_NEAREST)
    actual = int(np.unique(out.reshape(-1, 3), axis=0).shape[0])
    return out, actual
