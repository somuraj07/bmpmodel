from __future__ import annotations

import base64
from dataclasses import dataclass

import cv2
import numpy as np

from app.services.bmp_exporter import export_preview_png


@dataclass(frozen=True)
class BwVariantSpec:
    id: str
    name: str
    description: str


BW_VARIANTS: tuple[BwVariantSpec, ...] = (
    BwVariantSpec("otsu", "Auto balance", "Otsu threshold — good general-purpose clarity."),
    BwVariantSpec("adaptive", "Local contrast", "Adaptive threshold — handles uneven lighting."),
    BwVariantSpec("sharp", "Sharp outlines", "Edge sharpened before threshold — crisp linework."),
    BwVariantSpec("detail", "Fine detail", "CLAHE boost — preserves small motifs and dots."),
    BwVariantSpec("clean", "Smooth fills", "Denoised + closed gaps — clean solid regions."),
    BwVariantSpec("bold", "Strong contrast", "High-contrast fixed threshold — bold shapes."),
    BwVariantSpec("dither", "Halftone dither", "Ordered dither — textile-style shading."),
)


def _sharpness(bw: np.ndarray) -> float:
    gray = bw if bw.ndim == 2 else cv2.cvtColor(bw, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _to_rgb(bw: np.ndarray) -> np.ndarray:
    if bw.ndim == 3:
        return bw
    return np.stack([bw, bw, bw], axis=-1)


def _otsu(gray: np.ndarray) -> np.ndarray:
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return bw


def _apply_variant_gray(rgb: np.ndarray, variant_id: str) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    if variant_id == "otsu":
        return _otsu(gray)

    if variant_id == "adaptive":
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        block = max(11, (min(gray.shape) // 40) | 1)
        return cv2.adaptiveThreshold(
            blur,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block,
            4,
        )

    if variant_id == "sharp":
        blur = cv2.GaussianBlur(gray, (0, 0), 1.2)
        sharp = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)
        return _otsu(np.clip(sharp, 0, 255).astype(np.uint8))

    if variant_id == "detail":
        clahe = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8))
        boosted = clahe.apply(gray)
        return _otsu(boosted)

    if variant_id == "clean":
        denoised = cv2.medianBlur(gray, 3)
        bw = _otsu(denoised)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        return cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)

    if variant_id == "bold":
        _, bw = cv2.threshold(gray, 145, 255, cv2.THRESH_BINARY)
        return bw

    if variant_id == "dither":
        norm = gray.astype(np.float32) / 255.0
        bayer = np.array(
            [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]],
            dtype=np.float32,
        ) / 16.0
        tiled = np.tile(bayer, (gray.shape[0] // 4 + 1, gray.shape[1] // 4 + 1))
        tiled = tiled[: gray.shape[0], : gray.shape[1]]
        return (norm > tiled).astype(np.uint8) * 255

    raise ValueError(f"Unknown B&W variant: {variant_id}")


def apply_bw_variant(rgb: np.ndarray, variant_id: str) -> np.ndarray:
    """Convert RGB to strict black/white using the selected preview method."""
    valid = {v.id for v in BW_VARIANTS}
    if variant_id not in valid:
        raise ValueError(f"Unknown B&W variant: {variant_id}")
    bw = _apply_variant_gray(rgb, variant_id)
    return _to_rgb(bw)


def _maybe_downscale(rgb: np.ndarray, max_longest: int = 1200) -> np.ndarray:
    h, w = rgb.shape[:2]
    longest = max(h, w)
    if longest <= max_longest:
        return rgb
    f = max_longest / longest
    return cv2.resize(
        rgb,
        (max(8, int(w * f)), max(8, int(h * f))),
        interpolation=cv2.INTER_AREA,
    )


def generate_bw_previews(rgb: np.ndarray) -> list[dict]:
    """Return 7 B&W preview options with clarity scores for user selection."""
    work = _maybe_downscale(rgb)
    previews: list[dict] = []
    for spec in BW_VARIANTS:
        bw_rgb = apply_bw_variant(work, spec.id)
        sharp = _sharpness(bw_rgb)
        png = export_preview_png(bw_rgb, scale=1)
        previews.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "sharpness": round(sharp, 1),
                "preview_base64": base64.b64encode(png).decode("ascii"),
                "width": int(bw_rgb.shape[1]),
                "height": int(bw_rgb.shape[0]),
            }
        )
    previews.sort(key=lambda p: p["sharpness"], reverse=True)
    # Dither looks sharp in Laplacian but is noisy for mill BMP — recommend a clean variant.
    clean_pool = [p for p in previews if p["id"] != "dither"]
    best_id = clean_pool[0]["id"] if clean_pool else (previews[0]["id"] if previews else None)
    for item in previews:
        item["recommended"] = item["id"] == best_id
    return previews
