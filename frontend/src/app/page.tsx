"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const HOOKS_OPTIONS = [240, 480, 720, 960];
const REEDS_OPTIONS = [50, 52, 54, 56, 58, 60, 64, 66, 68, 70, 72, 78, 80, 90, 92, 100, 104, 110, 120, 144, 160];
const ZOOM_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64];
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api";

function MinusIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M4 9h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 4v10M4 9h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function nearestZoomIndex(width: number, height: number) {
  // ~8–12 screen pixels per BMP pixel, like zooming mill files in Preview.
  const longest = Math.max(width, height);
  let target = longest <= 800 ? 12 : longest <= 1400 ? 8 : 4;
  while (width * target * height * target > 14_000_000 && target > 1) {
    target -= 1;
  }
  let best = 0;
  for (let i = 0; i < ZOOM_STEPS.length; i++) {
    if (ZOOM_STEPS[i] <= target) best = i;
  }
  return Math.max(best, 0);
}

function drawPixelPerfect(
  canvas: HTMLCanvasElement,
  source: HTMLCanvasElement,
  scale: number,
  showGrid: boolean,
) {
  const sw = source.width;
  const sh = source.height;
  const dw = sw * scale;
  const dh = sh * scale;
  canvas.width = dw;
  canvas.height = dh;
  canvas.style.width = `${dw}px`;
  canvas.style.height = `${dh}px`;
  const dctx = canvas.getContext("2d", { alpha: false });
  if (!dctx) return;
  dctx.imageSmoothingEnabled = false;
  (dctx as CanvasRenderingContext2D & { webkitImageSmoothingEnabled?: boolean }).webkitImageSmoothingEnabled = false;
  dctx.drawImage(source, 0, 0, dw, dh);

  if (showGrid && scale >= 4) {
    dctx.strokeStyle = "rgba(0, 0, 0, 0.28)";
    dctx.lineWidth = 1;
    dctx.beginPath();
    for (let x = 0; x <= sw; x++) {
      const px = x * scale + 0.5;
      dctx.moveTo(px, 0);
      dctx.lineTo(px, dh);
    }
    for (let y = 0; y <= sh; y++) {
      const py = y * scale + 0.5;
      dctx.moveTo(0, py);
      dctx.lineTo(dw, py);
    }
    dctx.stroke();
  }
}

function PixelZoomPreview({ src }: { src: string; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [zoomIndex, setZoomIndex] = useState(6);
  const [naturalSize, setNaturalSize] = useState({ w: 0, h: 0 });
  const [hdMode, setHdMode] = useState(true);
  const [showGrid, setShowGrid] = useState(false);

  const zoom = ZOOM_STEPS[zoomIndex];

  const renderZoom = useCallback((scale: number, grid: boolean) => {
    const canvas = canvasRef.current;
    const source = sourceCanvasRef.current;
    if (!canvas || !source) return;
    drawPixelPerfect(canvas, source, scale, grid);
    setNaturalSize({ w: source.width, h: source.height });
  }, []);

  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      const offscreen = document.createElement("canvas");
      offscreen.width = img.naturalWidth;
      offscreen.height = img.naturalHeight;
      const ctx = offscreen.getContext("2d", { willReadFrequently: true });
      if (!ctx) return;
      ctx.imageSmoothingEnabled = false;
      ctx.drawImage(img, 0, 0);
      sourceCanvasRef.current = offscreen;
      const auto = nearestZoomIndex(offscreen.width, offscreen.height);
      setZoomIndex(auto);
      renderZoom(ZOOM_STEPS[auto], showGrid);
    };
    img.src = src;
  }, [src, renderZoom, showGrid]);

  useEffect(() => {
    if (!sourceCanvasRef.current) return;
    renderZoom(zoom, showGrid);
  }, [zoom, showGrid, hdMode, renderZoom]);

  const zoomOut = () => setZoomIndex((i) => Math.max(0, i - 1));
  const zoomIn = () => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1));
  const resetZoom = () => {
    const srcCanvas = sourceCanvasRef.current;
    if (!srcCanvas) {
      setZoomIndex(6);
      return;
    }
    setZoomIndex(nearestZoomIndex(srcCanvas.width, srcCanvas.height));
  };

  return (
    <div className="pixelPreview">
      <div className="previewToolbar">
        <button
          type="button"
          className={`hdBadge ${hdMode ? "hdBadgeActive" : ""}`}
          onClick={() => setHdMode((on) => !on)}
          title="HD pixel view (no blur)"
        >
          HD
        </button>
        <button
          type="button"
          className={`hdBadge ${showGrid ? "hdBadgeActive" : ""}`}
          onClick={() => setShowGrid((on) => !on)}
          title="Show pixel grid overlay"
        >
          Grid
        </button>
        <div className="zoomControls">
          <button
            type="button"
            className="zoomBtn"
            onClick={zoomOut}
            disabled={zoomIndex <= 0}
            aria-label="Zoom out"
            title="Zoom out"
          >
            <MinusIcon />
          </button>
          <span className="zoomLabel">{zoom}×</span>
          <button
            type="button"
            className="zoomBtn"
            onClick={zoomIn}
            disabled={zoomIndex >= ZOOM_STEPS.length - 1}
            aria-label="Zoom in"
            title="Zoom in"
          >
            <PlusIcon />
          </button>
        </div>
        <button type="button" className="resetZoomBtn" onClick={resetZoom} title="Reset zoom">
          Reset
        </button>
        {naturalSize.w > 0 && (
          <span className="zoomHint">
            {naturalSize.w}×{naturalSize.h} px → {naturalSize.w * zoom}×{naturalSize.h * zoom} px
          </span>
        )}
      </div>
      <div
        className={`previewScroll ${hdMode ? "previewScrollHd" : ""} ${showGrid ? "previewScrollGrid" : ""}`}
      >
        <canvas ref={canvasRef} className="previewCanvas" />
      </div>
    </div>
  );
}

interface ConversionResult {
  preview_base64: string;
  metadata: {
    original_width: number;
    original_height: number;
    output_width: number;
    output_height: number;
    bit_depth: number;
    grid_applied: boolean;
    correction_applied: boolean;
    auto_sized: boolean;
    finishing_applied: boolean;
    hd_applied: boolean;
    hd_scale: number;
    pixel_clean_applied: boolean;
    palette_colors: number;
    layout_mode: string;
    ml_applied?: boolean;
    ml_scale?: number;
    analysis_applied?: boolean;
    is_raw_photo?: boolean;
    estimated_design_colors?: number;
    design_cropped?: boolean;
    grid?: {
      width: number;
      height: number;
      hooks: number;
      reeds: number;
      aspect_ratio: number;
      physical_ratio?: number;
    };
  };
  source: {
    filename: string;
    width: number;
    height: number;
    format: string;
  };
  bmp_size_bytes: number;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<ConversionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useGrid, setUseGrid] = useState(false);
  const [hooks, setHooks] = useState(240);
  const [reeds, setReeds] = useState(68);
  const [shuttle, setShuttle] = useState(3);
  const [enableCorrection, setEnableCorrection] = useState(true);
  const [autoSize, setAutoSize] = useState(true);
  const [hdOutput, setHdOutput] = useState(false);
  const [hdMinLongest, setHdMinLongest] = useState(1920);
  const [pixelClean, setPixelClean] = useState(true);
  const [maxColors, setMaxColors] = useState(64);
  const [layoutMode, setLayoutMode] = useState<"color" | "bw" | "pixel_art" | "saree_print">("saree_print");
  const [blockStrength, setBlockStrength] = useState<"soft" | "medium" | "hard" | "extreme">("hard");
  const [mlClarity, setMlClarity] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const parseResponseBody = async (res: Response) => {
    const contentType = res.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      try {
        return await res.json();
      } catch {
        return null;
      }
    }
    try {
      return await res.text();
    } catch {
      return null;
    }
  };

  const extractErrorMessage = (body: unknown, fallback: string) => {
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail.trim()) return detail;
    }
    if (typeof body === "string" && body.trim()) {
      return body.slice(0, 220);
    }
    return fallback;
  };

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;
    setFile(selected);
    setResult(null);
    setError(null);
    setPreviewUrl(URL.createObjectURL(selected));
  }, []);

  const buildFormData = useCallback(() => {
    const fd = new FormData();
    if (!file) throw new Error("No file selected");
    fd.append("file", file);
    if (useGrid) {
      fd.append("hooks", String(hooks));
      fd.append("reeds", String(reeds));
      fd.append("shuttle", String(shuttle));
      fd.append("enable_correction", String(enableCorrection));
    }
    fd.append("auto_size", String(autoSize));
    fd.append("hd_output", String(hdOutput));
    fd.append("hd_min_longest", String(hdMinLongest));
    fd.append("pixel_clean", String(pixelClean));
    fd.append("max_colors", String(maxColors));
    fd.append("layout_mode", layoutMode);
    fd.append("block_strength", blockStrength);
    fd.append("ml_clarity", String(mlClarity));
    return fd;
  }, [file, useGrid, hooks, reeds, shuttle, enableCorrection, autoSize, hdOutput, hdMinLongest, pixelClean, maxColors, layoutMode, blockStrength, mlClarity]);

  const handleConvert = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE_URL}/convert`, { method: "POST", body: buildFormData() });
      const body = await parseResponseBody(res);
      if (!res.ok) {
        throw new Error(extractErrorMessage(body, "Conversion failed"));
      }
      if (!body || typeof body !== "object") {
        throw new Error("Invalid response from server");
      }
      setResult(body as ConversionResult);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Conversion failed");
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE_URL}/convert/download`, { method: "POST", body: buildFormData() });
      if (!res.ok) {
        const body = await parseResponseBody(res);
        throw new Error(extractErrorMessage(body, "Download failed"));
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name.replace(/\.[^.]+$/, "") + ".bmp";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container">
      <header className="header">
        <h1>BMP Mode</h1>
        <p>Convert PNG, JPEG, or any image to production-ready BMP — lossless, grid-aware, without breaking lines.</p>
      </header>

      <main className="main">
        <section className="panel">
          <h2>1. Upload Design</h2>
          <div
            className="dropzone"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = e.dataTransfer.files[0];
              if (dropped) {
                setFile(dropped);
                setPreviewUrl(URL.createObjectURL(dropped));
                setResult(null);
                setError(null);
              }
            }}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              hidden
            />
            {file ? (
              <div className="fileInfo">
                <span className="fileName">{file.name}</span>
                <span className="fileMeta">{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            ) : (
              <p>Drop image here or click to browse<br /><span>PNG, JPEG, BMP, GIF, TIFF, WebP</span></p>
            )}
          </div>
        </section>

        <section className="panel">
          <h2>2. Output Quality</h2>
          <div className="params">
            <div className="field layoutModeField">
              <label>Layout mode</label>
              <select value={layoutMode} onChange={(e) => setLayoutMode(e.target.value as "color" | "bw" | "pixel_art" | "saree_print")}>
                <option value="saree_print">Saree machine print (indexed BMP)</option>
                <option value="pixel_art">Pixel Art layout</option>
                <option value="color">Color photo BMP</option>
                <option value="bw">Black &amp; White layout</option>
              </select>
              {layoutMode === "saree_print" && (
                <>
                  <p className="hint">Chunky mill pixels: solid inks, hard squares, no blur — like the left reference. Use 4× blocks.</p>
                  <div className="field" style={{ marginTop: "8px" }}>
                    <label>Pixel block size</label>
                    <select value={blockStrength} onChange={(e) => setBlockStrength(e.target.value as "soft" | "medium" | "hard" | "extreme")}>
                      <option value="soft">2× squares</option>
                      <option value="medium">3× squares</option>
                      <option value="hard">4× squares (recommended)</option>
                      <option value="extreme">6× squares</option>
                    </select>
                  </div>
                </>
              )}
              {layoutMode === "bw" && (
                <p className="hint">Best for sharp pixels — outputs strict black/white only.</p>
              )}
              {layoutMode === "pixel_art" && (
                <>
                  <p className="hint">Matches production BMPs: 8–16 solid weaving colors, hard pixel blocks.</p>
                  <div className="field" style={{ marginTop: "8px" }}>
                    <label>Pixel Block Strength</label>
                    <select value={blockStrength} onChange={(e) => setBlockStrength(e.target.value as "soft" | "medium" | "hard" | "extreme")}>
                      <option value="soft">Soft (fine detail, small blocks)</option>
                      <option value="medium">Medium</option>
                      <option value="hard">Hard (recommended — large solid blocks)</option>
                      <option value="extreme">Extreme (biggest blocks, max clarity)</option>
                    </select>
                  </div>
                </>
              )}
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={mlClarity}
                onChange={(e) => setMlClarity(e.target.checked)}
              />
              ML clarity recovery (FSRCNN — if original is not HD / not sharp)
            </label>
            <label className="toggle">
              <input
                type="checkbox"
                checked={hdOutput}
                onChange={(e) => setHdOutput(e.target.checked)}
              />
              HD pixel output (auto upscale, sharp pixels)
            </label>
            {hdOutput && (
              <div className="field">
                <label>HD target (longest side px)</label>
                <select value={hdMinLongest} onChange={(e) => setHdMinLongest(Number(e.target.value))}>
                  <option value={1280}>1280 px</option>
                  <option value={1920}>1920 px (Full HD)</option>
                  <option value={2560}>2560 px (2K)</option>
                  <option value={3840}>3840 px (4K)</option>
                </select>
              </div>
            )}
            <label className="toggle">
              <input
                type="checkbox"
                checked={pixelClean}
                onChange={(e) => setPixelClean(e.target.checked)}
                disabled={layoutMode === "bw" || layoutMode === "pixel_art" || layoutMode === "saree_print"}
              />
              Full pixel color clarity (solid colors, no mixed pixels)
            </label>
            {pixelClean && layoutMode !== "bw" && layoutMode !== "pixel_art" && layoutMode !== "saree_print" && (
              <div className="field">
                <label>Max solid colors</label>
                <select value={maxColors} onChange={(e) => setMaxColors(Number(e.target.value))}>
                  <option value={8}>8 colors</option>
                  <option value={16}>16 colors</option>
                  <option value={32}>32 colors</option>
                  <option value={64}>64 colors (recommended)</option>
                  <option value={128}>128 colors</option>
                </select>
              </div>
            )}
            <label className="toggle">
              <input
                type="checkbox"
                checked={autoSize}
                onChange={(e) => setAutoSize(e.target.checked)}
              />
              Auto-size to original dimensions (before HD upscale)
            </label>
          </div>
        </section>

        <section className="panel">
          <h2>3. Weaving Parameters</h2>
          <label className="toggle">
            <input type="checkbox" checked={useGrid} onChange={(e) => setUseGrid(e.target.checked)} />
            Apply weaving grid mapping (Hooks × Reeds)
          </label>

          {useGrid && (
            <div className="params">
              <div className="field">
                <label>Hooks</label>
                <select value={hooks} onChange={(e) => setHooks(Number(e.target.value))}>
                  {HOOKS_OPTIONS.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Reeds</label>
                <select value={reeds} onChange={(e) => setReeds(Number(e.target.value))}>
                  {REEDS_OPTIONS.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Shuttle / Pick</label>
                <select value={shuttle} onChange={(e) => setShuttle(Number(e.target.value))}>
                  {[1, 2, 3, 4, 5].map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </div>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={enableCorrection}
                  onChange={(e) => setEnableCorrection(e.target.checked)}
                />
                Auto-correct broken lines &amp; gaps
              </label>
              <div className="ratio">
                Ratio: {(hooks / reeds).toFixed(3)} (Hooks ÷ Reeds)
              </div>
            </div>
          )}

          {!useGrid && (
            <p className="hint">
              Direct mode: lossless BMP with HD pixel upscaling and sharp edges by default.
            </p>
          )}
        </section>

        <section className="panel">
          <h2>4. Convert &amp; Download</h2>
          <div className="actions">
            <button
              className="primaryBtn"
              onClick={handleConvert}
              disabled={!file || loading}
            >
              {loading ? "Processing…" : "Convert to BMP"}
            </button>
            {result && (
              <button className="secondaryBtn" onClick={handleDownload} disabled={loading}>
                Download BMP
              </button>
            )}
          </div>
          {error && <p className="error">{error}</p>}
        </section>

        <section className="previewSection">
          <div className="previewCol">
            <h3>Original</h3>
            {previewUrl ? (
              <img src={previewUrl} alt="Original" className="previewImg" />
            ) : (
              <div className="placeholder">No image uploaded</div>
            )}
          </div>
          <div className="previewCol">
            <h3>BMP Output Preview</h3>
            {result ? (
              <>
                <PixelZoomPreview
                  src={`data:image/png;base64,${result.preview_base64}`}
                  alt="BMP preview"
                />
                <div className="meta">
                  <div><strong>Output:</strong> {result.metadata.output_width} × {result.metadata.output_height} px</div>
                  <div><strong>Bit depth:</strong> {result.metadata.bit_depth}-bit</div>
                  <div><strong>Grid applied:</strong> {result.metadata.grid_applied ? "Yes" : "No"}</div>
                  <div><strong>Correction:</strong> {result.metadata.correction_applied ? "Yes" : "No"}</div>
                  <div><strong>Auto-size:</strong> {result.metadata.auto_sized ? "Yes" : "No"}</div>
                  <div><strong>HD upscale:</strong> {result.metadata.hd_applied ? `${result.metadata.hd_scale}×` : "No (already HD)"}</div>
                  <div><strong>Layout mode:</strong> {result.metadata.layout_mode === "bw" ? "Black & White" : result.metadata.layout_mode === "pixel_art" ? "Pixel Art" : result.metadata.layout_mode === "saree_print" ? "Saree machine print" : "Color"}</div>
                  <div><strong>Pixel color clarity:</strong> {result.metadata.pixel_clean_applied ? `Yes (${result.metadata.palette_colors} solid colors)` : "No"}</div>
                  <div><strong>ML clarity:</strong> {result.metadata.ml_applied ? `Yes (FSRCNN ${result.metadata.ml_scale}×)` : "No"}</div>
                  <div><strong>Raw photo analysis:</strong> {result.metadata.is_raw_photo ? `Yes → ${result.metadata.estimated_design_colors} design colors${result.metadata.design_cropped ? ", cropped" : ""}` : "No (already a design)"}</div>
                  <div><strong>BMP size:</strong> {(result.bmp_size_bytes / 1024).toFixed(1)} KB</div>
                </div>
              </>
            ) : (
              <div className="placeholder">Convert to see preview</div>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
