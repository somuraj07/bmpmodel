export async function GET() {
  const raw =
    process.env.BACKEND_URL ||
    process.env.NEXT_PUBLIC_API_BASE_URL ||
    "http://localhost:8000";
  const backend = raw.replace(/\/api\/?$/, "").replace(/\/+$/, "");
  try {
    const res = await fetch(`${backend}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    const data = await res.json();
    return Response.json(data, { status: res.status });
  } catch {
    return Response.json({ status: "error", service: "bmp-rasterization" }, { status: 503 });
  }
}
