from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WeavingParams(BaseModel):
    hooks: Optional[int] = Field(None, ge=1, description="Weaving hooks count")
    reeds: Optional[int] = Field(None, ge=1, description="Reeds count")
    height: Optional[float] = Field(None, gt=0, description="Physical height/dimension")
    shuttle: Optional[int] = Field(None, ge=1, le=10, description="Shuttle/Pick level")
    count: Optional[int] = Field(None, ge=1, description="Textile count parameter")
    enable_correction: bool = Field(True, description="Apply pattern correction for broken lines")
    auto_size: bool = Field(
        True,
        description="Keep BMP output in original source dimensions by default.",
    )
    enable_finishing: bool = Field(
        True,
        description="Apply HD pixel clarity pass (sharp edges, no blur).",
    )
    hd_output: bool = Field(
        True,
        description="Auto upscale to HD with pixel-perfect nearest-neighbor.",
    )
    hd_min_longest: int = Field(
        1920,
        ge=480,
        le=8192,
        description="Target longest side in pixels for HD output.",
    )
    pixel_clean: bool = Field(
        True,
        description="Snap every pixel to a solid color (full pixel color clarity).",
    )
    max_colors: int = Field(
        64,
        ge=2,
        le=256,
        description="Maximum solid colors in the BMP palette.",
    )
    layout_mode: Literal["color", "bw", "pixel_art", "saree_print"] = Field(
        "saree_print",
        description="Final layout: color, black and white, pixel art, or saree machine print.",
    )
    block_strength: Literal["soft", "medium", "hard", "extreme"] = Field(
        "hard",
        description="Pixel block strength for pixel_art mode: soft(2), medium(4), hard(6), extreme(8).",
    )
    ml_clarity: bool = Field(
        True,
        description="Use FSRCNN super-resolution when the source is not HD or not sharp.",
    )
    bw_variant: Optional[str] = Field(
        None,
        description="Selected B&W preview variant id (from /bw-preview) applied before BMP layout.",
    )


class BwPreviewVariant(BaseModel):
    id: str
    name: str
    description: str
    sharpness: float
    preview_base64: str
    width: int
    height: int
    recommended: bool = False


class BwPreviewResponse(BaseModel):
    variants: list[BwPreviewVariant]
    source_width: int
    source_height: int


class GridDimensions(BaseModel):
    width: int
    height: int
    hooks: int
    reeds: int
    aspect_ratio: float
    physical_ratio: Optional[float] = None


class ProcessingMetadata(BaseModel):
    original_width: int
    original_height: int
    output_width: int
    output_height: int
    mode: str
    bit_depth: int
    grid_applied: bool
    correction_applied: bool
    auto_sized: bool
    finishing_applied: bool
    hd_applied: bool
    hd_scale: int
    pixel_clean_applied: bool
    palette_colors: int
    layout_mode: str
    ml_applied: bool = False
    ml_scale: int = 1
    analysis_applied: bool = False
    is_raw_photo: bool = False
    estimated_design_colors: int = 0
    design_cropped: bool = False
    grid: Optional[GridDimensions] = None
    bw_variant: Optional[str] = None
