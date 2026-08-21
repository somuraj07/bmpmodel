from __future__ import annotations

from app.models.schemas import GridDimensions, WeavingParams

# Shuttle → Count mapping from architecture spec (configurable defaults)
SHUTTLE_COUNT_MAP: dict[int, int] = {
    1: 60,
    2: 57,
    3: 54,
    4: 46,
    5: 41,
}


def resolve_count(params: WeavingParams) -> int | None:
    if params.count is not None:
        return params.count
    if params.shuttle is not None:
        return SHUTTLE_COUNT_MAP.get(params.shuttle)
    return None


def calculate_grid(
    params: WeavingParams,
    source_width: int,
    source_height: int,
) -> GridDimensions:
    hooks = params.hooks or source_width
    reeds = params.reeds or source_height

    physical_ratio = hooks / reeds if reeds else 1.0

    # Grid dimensions: hooks along width, reeds along height
    grid_width = int(hooks)
    grid_height = int(reeds)

    aspect = grid_width / grid_height if grid_height else 1.0

    return GridDimensions(
        width=grid_width,
        height=grid_height,
        hooks=grid_width,
        reeds=grid_height,
        aspect_ratio=aspect,
        physical_ratio=physical_ratio,
    )
