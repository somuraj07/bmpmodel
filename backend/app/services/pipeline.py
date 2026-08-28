from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.models.schemas import GridDimensions, ProcessingMetadata, WeavingParams
from app.services.bmp_exporter import export_bmp, export_preview_png
from app.services.color_reconstructor import reconstruct_colors
from app.services.design_analyzer import analyze_and_prepare
from app.services.feature_preserver import preserve_features
from app.services.finishing import (
    enhance_source_clarity,
    resize_to_original_if_needed,
    upscale_to_hd,
)
from app.services.grayscale_processor import rgb_to_grayscale
from app.services.grid_mapper import map_to_grid
from app.services.image_decoder import decode_to_rgb
from app.services.pattern_corrector import correct_pattern, restore_features
from app.services.ml_clarity import enhance_with_ml
from app.services.pixel_cleaner import clean_pixels, quantize_to_solid_pixels
from app.services.saree_print import to_saree_print_layout
from app.services.bw_preview import apply_bw_variant


@dataclass
class ProcessingResult:
    bmp_bytes: bytes
    preview_bytes: bytes
    metadata: ProcessingMetadata
    corrected_grayscale: np.ndarray | None = None


def to_black_white_layout(rgb: np.ndarray) -> np.ndarray:
    """
    Convert to strict 2-color black/white with edge-preserving cleanup.
    """
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Close tiny holes and reconnect thin breaks.
    kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)
    # Remove isolated speckles.
    bw = cv2.medianBlur(bw, 3)
    return cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)


# Production weaving BMPs in the reference set use ~7–16 solid colors.
_BLOCK_STRENGTH_COLORS = {"soft": 16, "medium": 12, "hard": 10, "extreme": 8}

def to_pixel_art_layout(rgb: np.ndarray, max_colors: int, block_strength: str = "hard") -> tuple[np.ndarray, int]:
    """
    Weaving BMP style: limited solid palette, hard pixel blocks, no grain.
    """
    hsv_orig = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    is_monochrome = float(np.mean(hsv_orig[:, :, 1])) < 20

    target_colors = min(max_colors, _BLOCK_STRENGTH_COLORS.get(block_strength, 10))
    result, actual_colors = quantize_to_solid_pixels(
        rgb, max_colors=target_colors, strict=True
    )

    if is_monochrome:
        gray = cv2.cvtColor(result, cv2.COLOR_RGB2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=1)
        result = cv2.cvtColor(bw, cv2.COLOR_GRAY2RGB)
        actual_colors = 2

    return result, actual_colors


def process_image(
    file_bytes: bytes,
    params: WeavingParams | None = None,
) -> ProcessingResult:
    import gc

    params = params or WeavingParams()
    original_rgb = decode_to_rgb(file_bytes)
    orig_h, orig_w = original_rgb.shape[:2]

    # Cap decode size early — free hosts OOM/timeout on multi‑MP photos.
    longest = max(orig_h, orig_w)
    if longest > 1600:
        f = 1600 / longest
        original_rgb = cv2.resize(
            original_rgb,
            (max(8, int(orig_w * f)), max(8, int(orig_h * f))),
            interpolation=cv2.INTER_AREA,
        )

    use_grid = params.hooks is not None and params.reeds is not None
    auto_sized = False
    finishing_applied = False
    hd_applied = False
    hd_scale = 1
    pixel_clean_applied = False
    palette_colors = 0
    ml_applied = False
    ml_scale = 1
    analysis_applied = False
    is_raw_photo = False
    estimated_design_colors = 0
    design_cropped = False

    if use_grid:
        grid = calculate_grid(params, orig_w, orig_h)
        grayscale = rgb_to_grayscale(original_rgb)

        expanded, mask = preserve_features(grayscale, grid.width, grid.height)
        raw_grid = map_to_grid(expanded, grid.width, grid.height)

        if params.enable_correction:
            corrected_gray, _ = correct_pattern(raw_grid)
            final_gray = restore_features(corrected_gray, mask, map_to_grid(grayscale, grid.width, grid.height))
            correction_applied = True
        else:
            final_gray = raw_grid
            correction_applied = False

        final_rgb = reconstruct_colors(original_rgb, final_gray)
        if params.auto_size:
            final_rgb = resize_to_original_if_needed(final_rgb, orig_w, orig_h)
            auto_sized = True
        grid_applied = True
    else:
        final_rgb = original_rgb
        grid = None
        grid_applied = False
        correction_applied = False
        final_gray = None

    # Analyze raw photos/scans and extract a weaving-style design automatically.
    final_rgb, analysis = analyze_and_prepare(final_rgb)
    analysis_applied = True
    is_raw_photo = analysis.is_raw_photo
    estimated_design_colors = analysis.estimated_design_colors
    design_cropped = analysis.cropped
    layout_mode = params.layout_mode
    if is_raw_photo and layout_mode == "color":
        layout_mode = "saree_print"

    bw_variant_applied: str | None = None
    if params.bw_variant:
        final_rgb = apply_bw_variant(final_rgb, params.bw_variant)
        bw_variant_applied = params.bw_variant
        is_raw_photo = False
        finishing_applied = True

    # Recover clarity from low-quality source inputs before layout quantization.
    if params.ml_clarity and layout_mode != "saree_print" and not bw_variant_applied:
        final_rgb, ml_applied, ml_scale = enhance_with_ml(final_rgb)
        if ml_applied:
            finishing_applied = True
    # CLAHE/unsharp adds extra shades — skip it for weaving pixel-art BMPs.
    if params.enable_finishing and layout_mode not in ("pixel_art", "saree_print") and not bw_variant_applied:
        final_rgb = enhance_source_clarity(final_rgb)
        finishing_applied = True

    if layout_mode == "saree_print":
        final_rgb, palette_colors = to_saree_print_layout(final_rgb, params.block_strength)
        pixel_clean_applied = True
        finishing_applied = True
    elif layout_mode == "bw":
        if not bw_variant_applied:
            final_rgb = to_black_white_layout(final_rgb)
        palette_colors = 2
        pixel_clean_applied = True
    elif layout_mode == "pixel_art":
        max_colors = params.max_colors
        if is_raw_photo:
            max_colors = min(max_colors, max(8, estimated_design_colors))
        final_rgb, palette_colors = to_pixel_art_layout(final_rgb, max_colors, params.block_strength)
        pixel_clean_applied = True
    elif params.pixel_clean:
        final_rgb, palette_colors = clean_pixels(final_rgb, max_colors=params.max_colors)
        pixel_clean_applied = True

    # Keep saree print at original pixel size (reference BMPs match the JPEG size).
    if params.hd_output and layout_mode != "saree_print":
        final_rgb, hd_scale = upscale_to_hd(final_rgb, min_longest=params.hd_min_longest)
        hd_applied = hd_scale > 1

    output_h, output_w = final_rgb.shape[:2]
    indexed = layout_mode in ("saree_print", "pixel_art", "bw")
    bmp_bytes = export_bmp(final_rgb, indexed=indexed)
    preview_bytes = export_preview_png(final_rgb, scale=1)

    metadata = ProcessingMetadata(
        original_width=orig_w,
        original_height=orig_h,
        output_width=output_w,
        output_height=output_h,
        mode="P" if indexed else "RGB",
        bit_depth=8 if indexed else 24,
        grid_applied=grid_applied,
        correction_applied=correction_applied,
        auto_sized=auto_sized or not use_grid,
        finishing_applied=finishing_applied,
        hd_applied=hd_applied,
        hd_scale=hd_scale,
        pixel_clean_applied=pixel_clean_applied,
        palette_colors=palette_colors,
        layout_mode=layout_mode,
        ml_applied=ml_applied,
        ml_scale=ml_scale,
        analysis_applied=analysis_applied,
        is_raw_photo=is_raw_photo,
        estimated_design_colors=estimated_design_colors,
        design_cropped=design_cropped,
        grid=grid,
        bw_variant=bw_variant_applied,
    )

    result = ProcessingResult(
        bmp_bytes=bmp_bytes,
        preview_bytes=preview_bytes,
        metadata=metadata,
        corrected_grayscale=final_gray,
    )
    gc.collect()
    return result
