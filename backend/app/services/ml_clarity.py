from __future__ import annotations

import urllib.request
from pathlib import Path

import cv2
import numpy as np

# Lightweight FSRCNN models (OpenCV DNN Super-Resolution).
# Downloaded once into backend/app/weights/.
MODEL_DIR = Path(__file__).resolve().parents[1] / "weights"
MODEL_URLS = {
    2: "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x2.pb",
    3: "https://github.com/Saafke/FSRCNN_Tensorflow/raw/master/models/FSRCNN_x3.pb",
}

_MAX_OUTPUT_PIXELS = 12_000_000
_sr_cache: dict[int, object] = {}


def _ensure_model(scale: int) -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    path = MODEL_DIR / f"FSRCNN_x{scale}.pb"
    if path.exists() and path.stat().st_size > 10_000:
        return path
    url = MODEL_URLS[scale]
    try:
        urllib.request.urlretrieve(url, path)
    except Exception:
        import subprocess

        subprocess.run(["curl", "-L", "--fail", "-o", str(path), url], check=True)
    return path


def _get_superres(scale: int):
    if scale in _sr_cache:
        return _sr_cache[scale]
    if not hasattr(cv2, "dnn_superres"):
        return None
    model_path = _ensure_model(scale)
    sr = cv2.dnn_superres.DnnSuperResImpl_create()
    sr.readModel(str(model_path))
    sr.setModel("fsrcnn", scale)
    _sr_cache[scale] = sr
    return sr


def source_needs_ml_clarity(rgb: np.ndarray) -> tuple[bool, float, int]:
    """
    Decide if the original is too small or too soft for a crisp BMP.
    Returns (needs_ml, laplacian_sharpness, suggested_scale).
    """
    h, w = rgb.shape[:2]
    longest = max(h, w)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    if longest < 720:
        return True, sharpness, 3
    if longest < 1400:
        return True, sharpness, 2
    if sharpness < 90.0 and longest < 2200:
        return True, sharpness, 2
    return False, sharpness, 1


def apply_ml_super_resolution(rgb: np.ndarray, scale: int) -> np.ndarray:
    """
    FSRCNN neural upscale. Falls back to original image if the model
    cannot be loaded or the output would be too large.
    """
    if scale <= 1:
        return rgb
    h, w = rgb.shape[:2]
    if h * w * (scale ** 2) > _MAX_OUTPUT_PIXELS:
        return rgb

    sr = _get_superres(scale)
    if sr is None:
        return rgb

    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    up = sr.upsample(bgr)
    return cv2.cvtColor(up, cv2.COLOR_BGR2RGB)


def enhance_with_ml(rgb: np.ndarray) -> tuple[np.ndarray, bool, int]:
    """
    Run ML clarity recovery when the source is not HD / not sharp.
    Returns (image, ml_applied, scale_used).
    """
    needs, _, scale = source_needs_ml_clarity(rgb)
    if not needs:
        return rgb, False, 1
    try:
        enhanced = apply_ml_super_resolution(rgb, scale)
        applied = enhanced.shape[0] != rgb.shape[0] or enhanced.shape[1] != rgb.shape[1]
        return enhanced, applied, scale if applied else 1
    except Exception:
        return rgb, False, 1
