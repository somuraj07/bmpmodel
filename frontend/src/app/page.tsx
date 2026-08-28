"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const HOOKS_OPTIONS = [240, 480, 720, 960];
const REEDS_OPTIONS = [50, 52, 54, 56, 58, 60, 64, 66, 68, 70, 72, 78, 80, 90, 92, 100, 104, 110, 120, 144, 160];
const ZOOM_STEPS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 48, 64];

function resolveApiBaseUrl(): string {
  // Same-origin proxy in local dev — avoids CORS and direct-port issues.
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return "/api";
    }
  }
  const raw = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api").trim().replace(/\/+$/, "");
  if (raw.endsWith("/api")) return raw;
  return `${raw}/api`;
}

function getApiBaseUrl(): string {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return "/api";
    }
  }
  return resolveApiBaseUrl();
}

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

function ZoomableImage({ src, alt }: { src: string; alt: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sourceCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const [zoomIndex, setZoomIndex] = useState(4);
  const [naturalSize, setNaturalSize] = useState({ w: 0, h: 0 });
  const zoom = ZOOM_STEPS[zoomIndex];

  const renderZoom = useCallback((scale: number) => {
    const canvas = canvasRef.current;
    const source = sourceCanvasRef.current;
    if (!canvas || !source) return;
    drawPixelPerfect(canvas, source, scale, false);
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
      renderZoom(ZOOM_STEPS[auto]);
    };
    img.src = src;
  }, [src, renderZoom]);

  useEffect(() => {
    if (!sourceCanvasRef.current) return;
    renderZoom(zoom);
  }, [zoom, renderZoom]);

  return (
    <div className="pixelPreview">
      <div className="previewToolbar">
        <div className="zoomControls">
          <button type="button" className="zoomBtn" onClick={() => setZoomIndex((i) => Math.max(0, i - 1))} disabled={zoomIndex <= 0} aria-label="Zoom out">
            <MinusIcon />
          </button>
          <span className="zoomLabel">{zoom}×</span>
          <button type="button" className="zoomBtn" onClick={() => setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1))} disabled={zoomIndex >= ZOOM_STEPS.length - 1} aria-label="Zoom in">
            <PlusIcon />
          </button>
        </div>
        <button type="button" className="resetZoomBtn" onClick={() => {
          const s = sourceCanvasRef.current;
          if (s) setZoomIndex(nearestZoomIndex(s.width, s.height));
        }}>Fit</button>
        {naturalSize.w > 0 && (
          <span className="zoomHint">{naturalSize.w}×{naturalSize.h} px</span>
        )}
      </div>
      <div className="previewScroll previewScrollHd">
        <canvas ref={canvasRef} className="previewCanvas" />
      </div>
    </div>
  );
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

interface BwPreviewVariant {
  id: string;
  name: string;
  description: string;
  sharpness: number;
  preview_base64: string;
  width: number;
  height: number;
  recommended: boolean;
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
    bw_variant?: string | null;
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
  const [bwPickerEnabled, setBwPickerEnabled] = useState(true);
  const [bwVariants, setBwVariants] = useState<BwPreviewVariant[]>([]);
  const [selectedBwVariant, setSelectedBwVariant] = useState<string | null>(null);
  const [bwLoading, setBwLoading] = useState(false);
  const [activeMenu, setActiveMenu] = useState<"upload" | "bw" | "output" | "weave" | "export">("upload");
  const [activeViewport, setActiveViewport] = useState<"source" | "bw" | "output">("source");
  const [backendStatus, setBackendStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const healthAbortRef = useRef<AbortController | null>(null);

  const checkBackend = useCallback(async () => {
    healthAbortRef.current?.abort();
    const controller = new AbortController();
    healthAbortRef.current = controller;
    const timeout = setTimeout(() => controller.abort(), 6000);
    try {
      const res = await fetch("/api/health", {
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timeout);
      setBackendStatus(res.ok ? "connected" : "disconnected");
    } catch {
      clearTimeout(timeout);
      setBackendStatus("disconnected");
    }
  }, []);

  useEffect(() => {
    checkBackend();
    const timer = setInterval(checkBackend, 15000);
    return () => {
      clearInterval(timer);
      healthAbortRef.current?.abort();
    };
  }, [checkBackend]);

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
    setBwVariants([]);
    setSelectedBwVariant(null);
    setPreviewUrl(URL.createObjectURL(selected));
  }, []);

  const fetchBwPreviews = useCallback(async (uploaded: File) => {
    setBwLoading(true);
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", uploaded);
      const res = await fetch(`${getApiBaseUrl()}/bw-preview`, { method: "POST", body: fd });
      const body = await parseResponseBody(res);
      if (!res.ok) {
        throw new Error(extractErrorMessage(body, "B&W preview failed"));
      }
      const variants = (body as { variants: BwPreviewVariant[] }).variants;
      setBwVariants(variants);
      const recommended = variants.find((v) => v.recommended);
      setSelectedBwVariant(recommended?.id ?? variants[0]?.id ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "B&W preview failed");
      setBwVariants([]);
      setSelectedBwVariant(null);
    } finally {
      setBwLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!file || !bwPickerEnabled) {
      setBwVariants([]);
      setSelectedBwVariant(null);
      return;
    }
    fetchBwPreviews(file);
  }, [file, bwPickerEnabled, fetchBwPreviews]);

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
    if (bwPickerEnabled && selectedBwVariant) {
      fd.append("bw_variant", selectedBwVariant);
    }
    return fd;
  }, [file, useGrid, hooks, reeds, shuttle, enableCorrection, autoSize, hdOutput, hdMinLongest, pixelClean, maxColors, layoutMode, blockStrength, mlClarity, bwPickerEnabled, selectedBwVariant]);

  const handleConvert = async () => {
    if (!file) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${getApiBaseUrl()}/convert`, { method: "POST", body: buildFormData() });
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
      const res = await fetch(`${getApiBaseUrl()}/convert/download`, { method: "POST", body: buildFormData() });
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

  const selectedBw = bwVariants.find((v) => v.id === selectedBwVariant);
  const menuItems = [
    { id: "upload" as const, label: "Upload", shortcut: "⌘1" },
    { id: "bw" as const, label: "B&W", shortcut: "⌘2" },
    { id: "output" as const, label: "Output", shortcut: "⌘3" },
    { id: "weave" as const, label: "Weaving", shortcut: "⌘4" },
    { id: "export" as const, label: "Export", shortcut: "⌘5" },
  ];

  return (
    <div className="ideShell">
      {/* Title bar */}
      <header className="ideTitlebar">
        <div className="ideTitlebarLeft">
          <div className="ideLogo">B</div>
          <span className="ideAppName">Timelly Studio</span>
        </div>
        <button
          type="button"
          className={`ideBackendStatus ideBackendStatus--${backendStatus}`}
          onClick={() => {
            setBackendStatus("checking");
            checkBackend();
          }}
          title="Click to retry connection"
        >
          <span className="ideBackendDot" />
          <span className="ideBackendText ideBackendText--full">
            {backendStatus === "checking" && "Connecting…"}
            {backendStatus === "connected" && "Backend Connected"}
            {backendStatus === "disconnected" && "Backend Offline — click to retry"}
          </span>
          <span className="ideBackendText ideBackendText--short">
            {backendStatus === "checking" && "…"}
            {backendStatus === "connected" && "Online"}
            {backendStatus === "disconnected" && "Offline"}
          </span>
        </button>
        <div className="ideTitlebarRight">
            <button className="ideTitleBtn ideTitleBtnPrimary" onClick={handleConvert} disabled={!file || loading || (bwPickerEnabled && !selectedBwVariant)}>
            <span className="ideBtnTextFull">{loading ? "Processing…" : "Convert"}</span>
            <span className="ideBtnTextShort">{loading ? "…" : "Go"}</span>
          </button>
          {result && (
            <button className="ideTitleBtn" onClick={handleDownload} disabled={loading}>
              <span className="ideBtnTextFull">Download BMP</span>
              <span className="ideBtnTextShort">Save</span>
            </button>
          )}
        </div>
      </header>

      {/* Menu bar */}
      <nav className="ideMenubar">
        {menuItems.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`ideMenuItem ${activeMenu === item.id ? "ideMenuItemActive" : ""}`}
            onClick={() => setActiveMenu(item.id)}
          >
            {item.label}
            <span className="ideMenuShortcut">{item.shortcut}</span>
          </button>
        ))}
      </nav>

      {error && (
        <div className="ideErrorBanner">{error}</div>
      )}

      {/* Editor body */}
      <div className="ideBody">
        {/* Left settings panel */}
        <aside className="ideSidebar">
          <div className="ideSidebarHeader">
            <span className="ideSidebarTitle">{menuItems.find((m) => m.id === activeMenu)?.label}</span>
            <span className="ideSidebarSubtitle">Settings</span>
          </div>
          <div className="ideSidebarContent">

            {activeMenu === "upload" && (
              <div className="idePanel">
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
                      setBwVariants([]);
                      setSelectedBwVariant(null);
                    }
                  }}
                >
                  <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} hidden />
                  {file ? (
                    <div className="fileInfo">
                      <span className="fileName">{file.name}</span>
                      <span className="fileMeta">{(file.size / 1024).toFixed(1)} KB</span>
                    </div>
                  ) : (
                    <>
                      <div className="dropzoneIcon">
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 16V4m0 0L8 8m4-4 4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" /></svg>
                      </div>
                      <p>Drop or click to upload<br /><span>PNG, JPEG, BMP, WebP…</span></p>
                    </>
                  )}
                </div>
              </div>
            )}

            {activeMenu === "bw" && (
              <div className="idePanel">
                <label className="toggle">
                  <input type="checkbox" checked={bwPickerEnabled} onChange={(e) => { setBwPickerEnabled(e.target.checked); setResult(null); }} />
                  <span className="toggleSwitch" />
                  <span className="toggleLabel"><strong>B&amp;W picker</strong>Generate 7 clarity variants</span>
                </label>
                {bwPickerEnabled && file && bwLoading && (
                  <div className="loadingPulse"><div className="loadingDots"><span /><span /><span /></div>Generating…</div>
                )}
                {bwPickerEnabled && !file && <p className="hint">Upload an image first.</p>}
                {bwPickerEnabled && file && !bwLoading && (
                  <button type="button" className="secondaryBtn" style={{ width: "100%", marginTop: "0.5rem" }} onClick={() => file && fetchBwPreviews(file)} disabled={bwLoading}>
                    Regenerate variants
                  </button>
                )}
              </div>
            )}

            {activeMenu === "output" && (
              <div className="idePanel">
                <div className="params">
                  <div className="field layoutModeField">
                    <label>Layout mode</label>
                    <select value={layoutMode} onChange={(e) => setLayoutMode(e.target.value as "color" | "bw" | "pixel_art" | "saree_print")}>
                      <option value="saree_print">Saree machine print</option>
                      <option value="pixel_art">Pixel Art</option>
                      <option value="color">Color photo</option>
                      <option value="bw">Black &amp; White</option>
                    </select>
                  </div>
                  {(layoutMode === "saree_print" || layoutMode === "pixel_art") && (
                    <div className="field">
                      <label>Block strength</label>
                      <select value={blockStrength} onChange={(e) => setBlockStrength(e.target.value as "soft" | "medium" | "hard" | "extreme")}>
                        <option value="soft">Soft 2×</option>
                        <option value="medium">Medium 3×</option>
                        <option value="hard">Hard 4×</option>
                        <option value="extreme">Extreme 6×</option>
                      </select>
                    </div>
                  )}
                  <label className="toggle">
                    <input type="checkbox" checked={mlClarity} onChange={(e) => setMlClarity(e.target.checked)} />
                    <span className="toggleSwitch" />
                    <span className="toggleLabel"><strong>ML clarity</strong>FSRCNN recovery</span>
                  </label>
                  <label className="toggle">
                    <input type="checkbox" checked={hdOutput} onChange={(e) => setHdOutput(e.target.checked)} />
                    <span className="toggleSwitch" />
                    <span className="toggleLabel"><strong>HD output</strong>Auto upscale</span>
                  </label>
                  {hdOutput && (
                    <div className="field">
                      <label>HD target</label>
                      <select value={hdMinLongest} onChange={(e) => setHdMinLongest(Number(e.target.value))}>
                        <option value={1280}>1280 px</option>
                        <option value={1920}>1920 px</option>
                        <option value={2560}>2560 px</option>
                        <option value={3840}>3840 px</option>
                      </select>
                    </div>
                  )}
                  <label className="toggle">
                    <input type="checkbox" checked={pixelClean} onChange={(e) => setPixelClean(e.target.checked)} disabled={layoutMode === "bw" || layoutMode === "pixel_art" || layoutMode === "saree_print"} />
                    <span className="toggleSwitch" />
                    <span className="toggleLabel"><strong>Pixel clarity</strong>Solid colors</span>
                  </label>
                  {pixelClean && layoutMode !== "bw" && layoutMode !== "pixel_art" && layoutMode !== "saree_print" && (
                    <div className="field">
                      <label>Max colors</label>
                      <select value={maxColors} onChange={(e) => setMaxColors(Number(e.target.value))}>
                        <option value={8}>8</option><option value={16}>16</option>
                        <option value={32}>32</option><option value={64}>64</option><option value={128}>128</option>
                      </select>
                    </div>
                  )}
                  <label className="toggle">
                    <input type="checkbox" checked={autoSize} onChange={(e) => setAutoSize(e.target.checked)} />
                    <span className="toggleSwitch" />
                    <span className="toggleLabel"><strong>Auto-size</strong>Match source dims</span>
                  </label>
                </div>
              </div>
            )}

            {activeMenu === "weave" && (
              <div className="idePanel">
                <label className="toggle">
                  <input type="checkbox" checked={useGrid} onChange={(e) => setUseGrid(e.target.checked)} />
                  <span className="toggleSwitch" />
                  <span className="toggleLabel"><strong>Weaving grid</strong>Hooks × Reeds</span>
                </label>
                {useGrid && (
                  <div className="params">
                    <div className="field"><label>Hooks</label>
                      <select value={hooks} onChange={(e) => setHooks(Number(e.target.value))}>{HOOKS_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}</select>
                    </div>
                    <div className="field"><label>Reeds</label>
                      <select value={reeds} onChange={(e) => setReeds(Number(e.target.value))}>{REEDS_OPTIONS.map((v) => <option key={v} value={v}>{v}</option>)}</select>
                    </div>
                    <div className="field"><label>Shuttle</label>
                      <select value={shuttle} onChange={(e) => setShuttle(Number(e.target.value))}>{[1,2,3,4,5].map((v) => <option key={v} value={v}>{v}</option>)}</select>
                    </div>
                    <label className="toggle">
                      <input type="checkbox" checked={enableCorrection} onChange={(e) => setEnableCorrection(e.target.checked)} />
                      <span className="toggleSwitch" />
                      <span className="toggleLabel"><strong>Auto-correct</strong>Fix broken lines</span>
                    </label>
                    <div className="ratio">Ratio: {(hooks / reeds).toFixed(3)}</div>
                  </div>
                )}
                {!useGrid && <p className="hint">Direct mode — no grid mapping.</p>}
              </div>
            )}

            {activeMenu === "export" && (
              <div className="idePanel">
                <p className="hint" style={{ marginBottom: "1rem" }}>Convert your selected B&amp;W variant to a production BMP file.</p>
                <button className="primaryBtn" style={{ width: "100%" }} onClick={handleConvert} disabled={!file || loading || (bwPickerEnabled && !selectedBwVariant)}>
                  {loading ? "Processing…" : "Convert to BMP"}
                </button>
                {result && (
                  <button className="secondaryBtn" style={{ width: "100%", marginTop: "0.5rem" }} onClick={handleDownload} disabled={loading}>
                    Download BMP
                  </button>
                )}
                {error && <p className="error">{error}</p>}
              </div>
            )}

          </div>
        </aside>

        {/* Center canvas */}
        <main className="ideCanvas">
          {/* Viewport tabs */}
          <div className="ideViewportTabs">
            <button type="button" className={`ideViewportTab ${activeViewport === "source" ? "ideViewportTabActive" : ""}`} onClick={() => setActiveViewport("source")}>
              Source
            </button>
            <button type="button" className={`ideViewportTab ${activeViewport === "bw" ? "ideViewportTabActive" : ""}`} onClick={() => setActiveViewport("bw")} disabled={!bwPickerEnabled || !selectedBw}>
              <span className="ideTabTextFull">B&amp;W Selected</span>
              <span className="ideTabTextShort">B&amp;W</span>
            </button>
            <button type="button" className={`ideViewportTab ${activeViewport === "output" ? "ideViewportTabActive" : ""}`} onClick={() => setActiveViewport("output")} disabled={!result}>
              <span className="ideTabTextFull">BMP Output</span>
              <span className="ideTabTextShort">Output</span>
            </button>
          </div>

          {/* Canvas area */}
          <div className="ideCanvasArea">
            {activeViewport === "source" && (
              previewUrl ? (
                <ZoomableImage src={previewUrl} alt="Source" />
              ) : (
                <div className="ideCanvasEmpty">
                  <div className="ideCanvasEmptyIcon">⊞</div>
                  <p>No source image</p>
                  <button className="secondaryBtn" onClick={() => { setActiveMenu("upload"); fileInputRef.current?.click(); }}>Upload design</button>
                </div>
              )
            )}

            {activeViewport === "bw" && selectedBw && (
              <ZoomableImage src={`data:image/png;base64,${selectedBw.preview_base64}`} alt={selectedBw.name} />
            )}

            {activeViewport === "bw" && !selectedBw && (
              <div className="ideCanvasEmpty"><p>Select a B&amp;W variant below</p></div>
            )}

            {activeViewport === "output" && result && (
              <PixelZoomPreview src={`data:image/png;base64,${result.preview_base64}`} alt="BMP output" />
            )}

            {activeViewport === "output" && !result && (
              <div className="ideCanvasEmpty"><p>Convert to see BMP output</p></div>
            )}
          </div>

          {/* B&W thumbnail strip */}
          {bwPickerEnabled && bwVariants.length > 0 && (
            <div className="ideBwStrip">
              <div className="ideBwStripLabel">B&amp;W Variants — click to select</div>
              <div className="bwPickerGrid" role="listbox">
                {bwVariants.map((variant) => {
                  const isSelected = selectedBwVariant === variant.id;
                  return (
                    <button
                      key={variant.id}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      className={`bwOption ${isSelected ? "bwOptionSelected" : ""}`}
                      onClick={() => { setSelectedBwVariant(variant.id); setActiveViewport("bw"); setResult(null); }}
                    >
                      <div className="bwOptionFrame">
                        <img src={`data:image/png;base64,${variant.preview_base64}`} alt={variant.name} className="bwOptionImg" />
                        {isSelected && <span className="bwSelectedMark">✓</span>}
                      </div>
                      <div className="bwOptionTitle">{variant.name}</div>
                      <div className="bwOptionMeta">{variant.sharpness.toFixed(0)}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </main>

        {/* Right properties panel */}
        <aside className="ideProps">
          <div className="ideSidebarHeader">
            <span className="ideSidebarTitle">Properties</span>
          </div>
          <div className="idePropsContent">
            <div className="meta">
              <div><strong>File</strong><span>{file?.name ?? "—"}</span></div>
              <div><strong>B&amp;W</strong><span>{selectedBw?.name ?? "—"}</span></div>
              <div><strong>Layout</strong><span>{layoutMode.replace("_", " ")}</span></div>
              <div><strong>Grid</strong><span>{useGrid ? `${hooks}×${reeds}` : "Off"}</span></div>
              {result && (
                <>
                  <div><strong>Output</strong><span>{result.metadata.output_width}×{result.metadata.output_height}</span></div>
                  <div><strong>Colors</strong><span>{result.metadata.palette_colors}</span></div>
                  <div><strong>Size</strong><span>{(result.bmp_size_bytes / 1024).toFixed(1)} KB</span></div>
                </>
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* Status bar */}
      <footer className="ideStatusbar">
        <span className={`ideStatusItem ideStatusItem--${backendStatus}`}>
          <span className="ideBackendDot" />
          <span className="ideStatusText">{backendStatus === "connected" ? "Online" : backendStatus === "disconnected" ? "Offline" : "…"}</span>
        </span>
        <span className="ideStatusSep">|</span>
        <span className="ideStatusItem ideStatusItem--file">{file ? file.name : "No file"}</span>
        <span className="ideStatusSep ideStatusSep--mid">|</span>
        <span className="ideStatusItem ideStatusItem--bw">{selectedBw ? selectedBw.name : "No B&W"}</span>
        <span className="ideStatusSep ideStatusSep--mid">|</span>
        <span className="ideStatusItem">{result ? "Ready" : "Pending"}</span>
      </footer>
    </div>
  );
}
