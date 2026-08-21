from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Tuple

from PIL import Image, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "BMP", "GIF", "TIFF", "WEBP"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@dataclass
class ImageMetadata:
    width: int
    height: int
    format: str
    mode: str
    has_alpha: bool


def validate_image(file_bytes: bytes, filename: str) -> ImageMetadata:
    if len(file_bytes) == 0:
        raise ValueError("Uploaded file is empty.")
    if len(file_bytes) > MAX_FILE_SIZE:
        raise ValueError(f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB.")

    try:
        with Image.open(BytesIO(file_bytes)) as img:
            img.verify()
    except UnidentifiedImageError as exc:
        raise ValueError(f"Unsupported or corrupted image file: {filename}") from exc

    with Image.open(BytesIO(file_bytes)) as img:
        fmt = (img.format or "UNKNOWN").upper()
        if fmt not in ALLOWED_FORMATS:
            raise ValueError(f"Unsupported format '{fmt}'. Allowed: {', '.join(sorted(ALLOWED_FORMATS))}")

        width, height = img.size
        if width < 1 or height < 1:
            raise ValueError("Image has invalid dimensions.")

        return ImageMetadata(
            width=width,
            height=height,
            format=fmt,
            mode=img.mode,
            has_alpha=img.mode in ("RGBA", "LA", "PA"),
        )


def validate_weaving_params(hooks: int | None, reeds: int | None) -> Tuple[bool, str]:
    if hooks is None and reeds is None:
        return True, "direct"
    if hooks is None or reeds is None:
        return False, "Both hooks and reeds must be provided for grid mapping."
    if hooks < 1 or reeds < 1:
        return False, "Hooks and reeds must be positive integers."
    return True, "grid"
