import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "Timelly Studio",
  description: "IDE-style textile design rasterization — convert images to production-ready BMP",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

const healthBootScript = `
(function () {
  function urls() {
    var host = window.location.hostname;
    if (host === "localhost" || host === "127.0.0.1") {
      return ["http://127.0.0.1:8000/api/health", "/api/health"];
    }
    var raw = ${JSON.stringify(process.env.NEXT_PUBLIC_API_BASE_URL || "")}.replace(/\\/+$/, "");
    if (!raw) return ["/api/health"];
    var base = raw.endsWith("/api") ? raw : raw + "/api";
    return [base + "/health"];
  }

  function apply(status) {
    document.querySelectorAll(".ideBackendStatus").forEach(function (el) {
      el.classList.remove("ideBackendStatus--checking", "ideBackendStatus--warming", "ideBackendStatus--connected", "ideBackendStatus--disconnected");
      el.classList.add("ideBackendStatus--" + status);
    });
    document.querySelectorAll(".ideBackendText--full").forEach(function (el) {
      el.textContent = status === "connected" ? "Backend Connected" : status === "disconnected" ? "Backend Offline — click to retry" : "Connecting…";
    });
    document.querySelectorAll(".ideBackendText--short").forEach(function (el) {
      el.textContent = status === "connected" ? "Online" : status === "disconnected" ? "Offline" : "…";
    });
    document.querySelectorAll(".ideStatusText").forEach(function (el) {
      el.textContent = status === "connected" ? "Online" : status === "disconnected" ? "Offline" : "…";
    });
    window.__BACKEND_STATUS__ = status;
  }

  function ping() {
    var list = urls();
    var i = 0;
    function next() {
      if (i >= list.length) {
        apply("disconnected");
        return;
      }
      fetch(list[i++], { cache: "no-store" })
        .then(function (res) {
          if (!res.ok) { next(); return; }
          return res.json().catch(function () { return null; }).then(function (data) {
            if ((data && data.status === "ok") || res.ok) apply("connected");
            else next();
          });
        })
        .catch(next);
    }
    apply("checking");
    next();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ping);
  } else {
    ping();
  }
  window.setInterval(ping, 30000);
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href="/styles.css" />
      </head>
      <body>
        {children}
        <script dangerouslySetInnerHTML={{ __html: healthBootScript }} />
      </body>
    </html>
  );
}
