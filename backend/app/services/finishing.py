from __future__ import annotations

import math

import cv2
import numpy as np

# HD target: upscale so longest side reaches this (pixel-perfect, integer scale)
HD_MIN_LONGEST = 1920
HD_MAX_SCALE = 8


def calculate_hd_dimensions(
    width: int,
    height: int,
    min_longest: int = HD_MIN_LONGEST,
    max_scale: int = HD_MAX_SCALE,
) -> tuple[int, int, int]:
    """
    Compute HD output size using integer nearest-neighbor scale.
    Returns (out_width, out_height, scale_factor).
    """
    longest = max(width, height)
    if longest >= min_longest:
        return width, height, 1

    scale = min(max_scale, max(2, math.ceil(min_longest / longest)))
    return width * scale, height * scale, scale


def resize_nearest(image: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
    if image.shape[1] == target_width and image.shape[0] == target_height:
        return image
    return cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_NEAREST)


def resize_to_original_if_needed(
    image: np.ndarray,
    target_width: int,
    target_height: int,
) -> np.ndarray:
    return resize_nearest(image, target_width, target_height)


def upscale_to_hd(image: np.ndarray, min_longest: int = HD_MIN_LONGEST) -> tuple[np.ndarray, int]:
    h, w = image.shape[:2]
    out_w, out_h, scale = calculate_hd_dimensions(w, h, min_longest=min_longest)
    if scale == 1:
        return image, 1
    return resize_nearest(image, out_w, out_h), scale


def apply_hd_pixel_clarity(image: np.ndarray) -> np.ndarray:
    """
    Pixel-sharp clarity pass for textile BMP — no blur filters.
    Uses edge-preserving sharpening and slight contrast boost on luminance only.
    """
    # Laplacian-style sharpening kernel (preserves hard pixel edges)
    sharpen_kernel = np.array(
        [[0, -1, 0], [-1, 5, -1], [0, -1, 0]],
        dtype=np.float32,
    )
    sharpened = cv2.filter2D(image, -1, sharpen_kernel)

    # Boost local contrast on L channel only (no chroma smearing)
    lab = cv2.cvtColor(sharpened, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    # Linear stretch on luminance for clearer pixel separation
    l_float = l_channel.astype(np.float32)
    lo, hi = np.percentile(l_float, 1), np.percentile(l_float, 99)
    if hi > lo:
        l_stretched = np.clip((l_float - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    else:
        l_stretched = l_channel

    enhanced = cv2.merge((l_stretched, a_channel, b_channel))
    result = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)
    return np.clip(result, 0, 255).astype(np.uint8)


def enhance_source_clarity(image: np.ndarray) -> np.ndarray:
    """
    Recover clarity from low-quality sources before pixel quantization.
    Keeps geometry intact while improving local contrast and edge visibility.
    """
    if image.size == 0:
        return image

    # Preserve edges while reducing compression noise.
    denoised = cv2.bilateralFilter(image, d=5, sigmaColor=35, sigmaSpace=35)

    # Improve local luminance contrast (helps flat/muddy inputs).
    lab = cv2.cvtColor(denoised, cv2.COLOR_RGB2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_boost = clahe.apply(l_channel)
    contrast_img = cv2.cvtColor(cv2.merge((l_boost, a_channel, b_channel)), cv2.COLOR_LAB2RGB)

    # Mild unsharp mask for edge clarity without halo artifacts.
    blur = cv2.GaussianBlur(contrast_img, (0, 0), sigmaX=1.0, sigmaY=1.0)
    sharpened = cv2.addWeighted(contrast_img, 1.25, blur, -0.25, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def apply_finishing(image: np.ndarray) -> np.ndarray:
    """Alias for HD pixel clarity (replaces old blur-based finishing)."""
    return apply_hd_pixel_clarity(image)
