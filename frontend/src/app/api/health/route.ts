export async function GET() {
  const backend = (process.env.BACKEND_URL || "http://localhost:8000").replace(/\/+$/, "");
  try {
    const res = await fetch(`${backend}/api/health`, { cache: "no-store" });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch {
    return Response.json({ status: "error", service: "bmp-rasterization" }, { status: 503 });
  }
}
