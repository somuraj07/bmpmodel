from __future__ import annotations

import cv2
import numpy as np

from app.services.pixel_cleaner import quantize_to_solid_pixels


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
    min_colors: int = 2,
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
        if len(roots) <= max(2, int(min_colors)):
            break
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


def _edge_mask(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    edges = cv2.dilate(edges, kernel, iterations=1)
    return edges > 0


def _outline_mask(rgb: np.ndarray) -> np.ndarray:
    """Very dark linework only — not broad Canny edges."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    lab = _to_lab(rgb)
    return (lab[:, :, 0] < 40) & (gray < 90)


def _snap_denoise(rgb: np.ndarray, step: int = 8) -> np.ndarray:
    return ((rgb.astype(np.uint16) + step // 2) // step * step).clip(0, 255).astype(np.uint8)


def _lock_outline_ink(
    labels: np.ndarray, palette_lab: np.ndarray, outline_mask: np.ndarray
) -> np.ndarray:
    if not np.any(outline_mask):
        return labels
    dark_i = int(np.argmin(palette_lab[:, 0]))
    out = labels.copy()
    out[outline_mask] = dark_i
    return out


def _smooth_fill_labels(
    labels: np.ndarray, protected: np.ndarray, passes: int = 2
) -> np.ndarray:
    """Smooth noisy fill only — never bleed color across outlines."""
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
        same_count = np.sum(neighbours == labels[:, :, None], axis=2)
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


def _remove_fringe_labels(labels: np.ndarray, protected: np.ndarray) -> np.ndarray:
    """Remove anti-alias fringe pixels that cause color overlap at borders."""
    h, w = labels.shape
    rows = np.arange(h)[:, None]
    cols = np.arange(w)[None, :]

    def _neighbour_majority(lbl: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        up = np.roll(lbl, -1, axis=0)
        dn = np.roll(lbl, 1, axis=0)
        lt = np.roll(lbl, 1, axis=1)
        rt = np.roll(lbl, -1, axis=1)
        neighbours = np.stack([up, dn, lt, rt], axis=2)
        same = (
            (up == lbl).astype(np.int32)
            + (dn == lbl).astype(np.int32)
            + (lt == lbl).astype(np.int32)
            + (rt == lbl).astype(np.int32)
        )
        n = int(lbl.max()) + 1
        votes = np.zeros((h, w, n), dtype=np.int32)
        for i in range(4):
            np.add.at(votes, (rows, cols, neighbours[:, :, i]), 1)
        return same, np.argmax(votes, axis=2).astype(np.int32)

    for _ in range(6):
        same, majority = _neighbour_majority(labels)
        mask = (same == 0) & (~protected)
        if not np.any(mask):
            break
        labels = np.where(mask, majority, labels)
    for _ in range(3):
        same, majority = _neighbour_majority(labels)
        mask = (same <= 1) & (~protected)
        if not np.any(mask):
            break
        labels = np.where(mask, majority, labels)
    return labels


def _estimate_ink_count(rgb: np.ndarray, lab: np.ndarray, chroma_frac: float) -> int:
    unique = _fast_unique_count(rgb)
    base = _best_k(lab, chroma_frac)
    if unique > 20_000:
        return max(base, 14)
    if unique > 5_000:
        return max(base, 12)
    return base


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


def _sharpness(rgb: np.ndarray) -> float:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _is_grayscale_dither(rgb: np.ndarray, unique: int) -> bool:
    """Detect anti-aliased B/W dither patterns (reference BMP style)."""
    if unique > 64:
        return False
    flat = rgb.reshape(-1, 3)
    if flat.shape[0] > 40_000:
        rng = np.random.default_rng(1)
        flat = flat[rng.choice(flat.shape[0], 40_000, replace=False)]
    if not (np.all(flat[:, 0] == flat[:, 1]) and np.all(flat[:, 1] == flat[:, 2])):
        return False
    return _sharpness(rgb) > 500


def _snap_binary_dither(rgb: np.ndarray) -> np.ndarray:
    """Convert gray anti-alias pixels to pure black/white, keeping dither layout."""
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    bw = np.where(gray >= 128, 255, 0).astype(np.uint8)
    return np.stack([bw, bw, bw], axis=-1)


def _is_weaving_ready(rgb: np.ndarray, unique: int) -> bool:
    """True when the source is already a sharp weaving/BMP-style design."""
    sharp = _sharpness(rgb)
    if unique <= 20:
        return True
    if unique <= 64 and sharp > 500:
        return True
    if unique <= 128 and sharp > 5000:
        return True
    return False


def _pack_rgb(pixels: np.ndarray) -> np.ndarray:
    p = pixels.astype(np.uint32)
    return p[:, 0] * 65536 + p[:, 1] * 256 + p[:, 2]


def _unpack_rgb(packed: int) -> np.ndarray:
    return np.array([(packed >> 16) & 255, (packed >> 8) & 255, packed & 255], dtype=np.uint8)


def _block_mode_downscale(rgb: np.ndarray, sw: int, sh: int) -> np.ndarray:
    """Majority-color downscale — keeps stippling/hatching sharp (no blur)."""
    h, w = rgb.shape[:2]
    bh = max(1, h // sh)
    bw = max(1, w // sw)
    trim_h, trim_w = sh * bh, sw * bw
    blocks = rgb[:trim_h, :trim_w].reshape(sh, bh, sw, bw, 3)
    out = np.zeros((sh, sw, 3), dtype=np.uint8)
    for y in range(sh):
        for x in range(sw):
            packed = _pack_rgb(blocks[y, :, x, :, :].reshape(-1, 3))
            vals, counts = np.unique(packed, return_counts=True)
            out[y, x] = _unpack_rgb(int(vals[np.argmax(counts)]))
    return out


def _labels_to_rgb(labels: np.ndarray, palette_lab: np.ndarray, ref_rgb: np.ndarray) -> np.ndarray:
    palette_bgr = cv2.cvtColor(
        np.clip(palette_lab, 0, 255).astype(np.uint8).reshape(-1, 1, 3),
        cv2.COLOR_LAB2BGR,
    )
    palette_rgb = cv2.cvtColor(palette_bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3)
    palette_rgb = _flatten_palette_rgb(palette_rgb, ref_rgb)
    return palette_rgb[labels]


def _quantize_colorful_design(
    rgb: np.ndarray,
    *,
    target_k: int,
) -> tuple[np.ndarray, int]:
    """Edge-aware solid inks for multi-color kalamkari / block-print art."""
    work = _snap_denoise(rgb, step=8)
    k = int(np.clip(target_k, 4, 16))
    out, _ = quantize_to_solid_pixels(work, max_colors=k, strict=True)
    outline = _outline_mask(work)
    if np.any(outline):
        uniq = np.unique(out.reshape(-1, 3), axis=0)
        dark = uniq[np.argmin(uniq.astype(np.int32).sum(axis=1))]
        out = out.copy()
        out[outline] = dark
    actual = int(np.unique(out.reshape(-1, 3), axis=0).shape[0])
    return out, actual


def _quantize_to_inks(
    rgb: np.ndarray,
    *,
    target_k: int,
    preserve_detail: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build limited solid-ink palette and per-pixel labels at full working resolution."""
    step = 8 if preserve_detail else 16
    work = _snap_denoise(rgb, step=step)
    lab = _to_lab(work)
    outline = _outline_mask(work)
    edge_protect = outline
    chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
    chroma_frac = float(np.mean(chroma > 16))
    k = int(np.clip(target_k, 3, 16))

    start_k = min(16, max(k, 12 if chroma_frac >= 0.25 else k))
    centers, labels, _ = _kmeans_lab(lab, start_k)

    if preserve_detail:
        merge_de, merge_dl = 7.5, 10.0
        same_hue_de, same_hue_dl = 6.0, 10.0
        min_frac = 0.0004
    else:
        merge_de, merge_dl = 10.5, 16.0
        same_hue_de, same_hue_dl = 12.0, 20.0
        min_frac = 0.001

    merged_lab = _agglomerative_merge(
        centers,
        labels,
        max_de=merge_de,
        max_dl=merge_dl,
        same_hue_de=same_hue_de,
        same_hue_dl=same_hue_dl,
        min_colors=k,
    )
    labels = _relabel_to_palette(lab, merged_lab)
    if k < 12:
        merged_lab, labels = _snap_neutral_mids(merged_lab, labels)
    labels = _lock_outline_ink(labels, merged_lab, outline)
    labels = _remove_fringe_labels(labels, edge_protect)
    labels = _smooth_fill_labels(labels, edge_protect, passes=2)
    if not preserve_detail:
        merged_lab, labels = _recover_accents(lab, merged_lab, labels)
        labels = _majority_filter(labels, passes=1)
    merged_lab, labels = _prune_tiny_inks(merged_lab, labels, min_frac=min_frac)
    labels = _remove_specks(labels, merged_lab)
    labels = _lock_outline_ink(labels, merged_lab, outline)
    return merged_lab, labels, lab


_PIXEL_CELL = {"soft": 2, "medium": 3, "hard": 4, "extreme": 6}


def to_saree_print_layout(
    rgb: np.ndarray,
    block_strength: str = "hard",
    color_count: int | None = None,
) -> tuple[np.ndarray, int]:
    """
    Mill BMP look: solid inks, sharp pixel blocks, preserved stippling/hatching.
    """
    orig_h, orig_w = rgb.shape[:2]
    rgb = _collapse_uniform_blocks(rgb)
    unique = _fast_unique_count(rgb)

    if _is_weaving_ready(rgb, unique):
        if _is_grayscale_dither(rgb, unique):
            out = _snap_binary_dither(rgb)
            return out, 2

        if unique <= 16:
            return rgb, unique

        lab = _to_lab(rgb)
        chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
        chroma_frac = float(np.mean(chroma > 16))
        k = int(color_count) if color_count else _estimate_ink_count(rgb, lab, chroma_frac)
        k = int(np.clip(k, 3, 16))
        if unique > 5000:
            return _quantize_colorful_design(rgb, target_k=k)
        merged_lab, labels, _ = _quantize_to_inks(rgb, target_k=k, preserve_detail=True)
        out = _labels_to_rgb(labels, merged_lab, rgb)
        actual = int(np.unique(out.reshape(-1, 3), axis=0).shape[0])
        return out, actual

    cell = int(_PIXEL_CELL.get(block_strength, 4))
    h, w = rgb.shape[:2]
    longest = max(h, w)

    # Native-resolution scans: quantize in place — do not blur stippling first.
    if longest <= 1600:
        lab = _to_lab(rgb)
        chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
        chroma_frac = float(np.mean(chroma > 16))
        k = int(color_count) if color_count else _estimate_ink_count(rgb, lab, chroma_frac)
        k = int(np.clip(k, 4, 16))
        if unique > 5000:
            return _quantize_colorful_design(rgb, target_k=k)
        merged_lab, labels, _ = _quantize_to_inks(rgb, target_k=k, preserve_detail=True)
        out = _labels_to_rgb(labels, merged_lab, rgb)
        actual = int(np.unique(out.reshape(-1, 3), axis=0).shape[0])
        return out, actual

    # Very large photos: coarse grid with block-mode downscale (not INTER_AREA).
    if longest > 2000:
        f = 2000 / longest
        rgb = cv2.resize(
            rgb,
            (max(8, int(w * f)), max(8, int(h * f))),
            interpolation=cv2.INTER_AREA,
        )
        h, w = rgb.shape[:2]

    sw = max(8, w // cell)
    sh = max(8, h // cell)
    small = _block_mode_downscale(rgb, sw, sh)

    lab = _to_lab(small)
    chroma = np.hypot(lab[:, :, 1] - 128.0, lab[:, :, 2] - 128.0)
    chroma_frac = float(np.mean(chroma > 16))
    k = int(color_count) if color_count else _estimate_ink_count(small, lab, chroma_frac)
    k = int(np.clip(k, 4, 16))
    merged_lab, labels, _ = _quantize_to_inks(small, target_k=k, preserve_detail=True)
    small_q = _labels_to_rgb(labels, merged_lab, small)

    out = cv2.resize(small_q, (orig_w, orig_h), interpolation=cv2.INTER_NEAREST)
    actual = int(np.unique(out.reshape(-1, 3), axis=0).shape[0])
    return out, actual
