# BMP Mode — Intelligent Textile Design Rasterization

Convert PNG, JPEG, or any supported image to production-ready **24-bit BMP** with full clarity and accuracy.

## Features

- **Direct conversion** — lossless BMP at original resolution (no quality loss)
- **Weaving grid mapping** — map artwork to Hooks × Reeds discrete grid
- **Feature preservation** — protects thin lines before grid conversion
- **Pattern correction** — auto-repairs broken lines, gaps, and isolated pixels
- **Color reconstruction** — restores colors from original RGB source

## Quick Start

### 1. Backend (Python/FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Usage

1. **Upload** any image (PNG, JPEG, BMP, GIF, TIFF, WebP)
2. **Optional:** enable weaving grid and set Hooks, Reeds, Shuttle/Pick
3. **Convert** to preview the BMP output
4. **Download** the final `.bmp` file

### Direct Mode (default)

Without weaving parameters, the app performs a **lossless 24-bit BMP export** at the original image dimensions — no compression, no quality degradation.

### Weaving Grid Mode

When Hooks and Reeds are set, the pipeline runs:

```
Upload → RGB Preservation → Grayscale Analysis → Feature Preservation
→ Grid Mapping → Pattern Correction → Feature Restoration
→ Color Reconstruction → BMP Export
```

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/convert` | POST | Convert image, returns JSON + preview |
| `/api/convert/download` | POST | Convert and download BMP file |

Form fields: `file`, `hooks`, `reeds`, `shuttle`, `count`, `enable_correction`

## Architecture

Based on the Intelligent Textile Design Rasterization specification:

- **Backend:** Python, FastAPI, Pillow, OpenCV, NumPy
- **Frontend:** Next.js, React, TypeScript
- **Processing:** Deterministic, version-controlled image pipeline

## Supported Formats

Input: JPEG, PNG, BMP, GIF, TIFF, WebP (max 50 MB)  
Output: 24-bit uncompressed BMP
