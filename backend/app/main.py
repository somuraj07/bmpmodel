from __future__ import annotations

import base64
import json
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.models.schemas import WeavingParams
from app.services.image_validator import validate_image, validate_weaving_params
from app.services.pipeline import process_image

load_dotenv()

app = FastAPI(
    title="Intelligent Textile Design Rasterization API",
    description="Convert images to production-ready BMP with weaving grid optimization",
    version="1.0.0",
)


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "bmp-rasterization"}


@app.post("/api/convert")
async def convert_image(
    file: UploadFile = File(...),
    hooks: Optional[int] = Form(None),
    reeds: Optional[int] = Form(None),
    height: Optional[float] = Form(None),
    shuttle: Optional[int] = Form(None),
    count: Optional[int] = Form(None),
    enable_correction: bool = Form(True),
    auto_size: bool = Form(True),
    enable_finishing: bool = Form(True),
    hd_output: bool = Form(True),
    hd_min_longest: int = Form(1920),
    pixel_clean: bool = Form(True),
    max_colors: int = Form(64),
    layout_mode: str = Form("saree_print"),
    block_strength: str = Form("hard"),
    ml_clarity: bool = Form(True),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    file_bytes = await file.read()

    try:
        meta = validate_image(file_bytes, file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    params = WeavingParams(
        hooks=hooks,
        reeds=reeds,
        height=height,
        shuttle=shuttle,
        count=count,
        enable_correction=enable_correction,
        auto_size=auto_size,
        enable_finishing=enable_finishing,
        hd_output=hd_output,
        hd_min_longest=hd_min_longest,
        pixel_clean=pixel_clean,
        max_colors=max_colors,
        layout_mode=layout_mode,
        block_strength=block_strength,
        ml_clarity=ml_clarity,
    )

    valid, msg = validate_weaving_params(hooks, reeds)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    try:
        result = process_image(file_bytes, params)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

    preview_b64 = base64.b64encode(result.preview_bytes).decode("ascii")

    return {
        "success": True,
        "source": {
            "filename": file.filename,
            "width": meta.width,
            "height": meta.height,
            "format": meta.format,
            "mode": meta.mode,
        },
        "metadata": result.metadata.model_dump(),
        "preview_base64": preview_b64,
        "bmp_size_bytes": len(result.bmp_bytes),
    }


@app.post("/api/convert/download")
async def convert_and_download(
    file: UploadFile = File(...),
    hooks: Optional[int] = Form(None),
    reeds: Optional[int] = Form(None),
    height: Optional[float] = Form(None),
    shuttle: Optional[int] = Form(None),
    count: Optional[int] = Form(None),
    enable_correction: bool = Form(True),
    auto_size: bool = Form(True),
    enable_finishing: bool = Form(True),
    hd_output: bool = Form(True),
    hd_min_longest: int = Form(1920),
    pixel_clean: bool = Form(True),
    max_colors: int = Form(64),
    layout_mode: str = Form("saree_print"),
    block_strength: str = Form("hard"),
    ml_clarity: bool = Form(True),
):
    file_bytes = await file.read()

    try:
        validate_image(file_bytes, file.filename or "upload")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    params = WeavingParams(
        hooks=hooks,
        reeds=reeds,
        height=height,
        shuttle=shuttle,
        count=count,
        enable_correction=enable_correction,
        auto_size=auto_size,
        enable_finishing=enable_finishing,
        hd_output=hd_output,
        hd_min_longest=hd_min_longest,
        pixel_clean=pixel_clean,
        max_colors=max_colors,
        layout_mode=layout_mode,
        block_strength=block_strength,
        ml_clarity=ml_clarity,
    )

    valid, msg = validate_weaving_params(hooks, reeds)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)

    try:
        result = process_image(file_bytes, params)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}") from exc

    stem = (file.filename or "output").rsplit(".", 1)[0]
    return Response(
        content=result.bmp_bytes,
        media_type="image/bmp",
        headers={
            "Content-Disposition": f'attachment; filename="{stem}.bmp"',
            "X-Processing-Metadata": json.dumps(result.metadata.model_dump()),
        },
    )
