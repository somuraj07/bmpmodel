const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  outputFileTracingRoot: path.join(__dirname),
  // Optional local proxy only in development.
  // Production calls NEXT_PUBLIC_API_BASE_URL directly (avoids Vercel timeout).
  async rewrites() {
    if (process.env.NODE_ENV === "production") {
      return [];
    }
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
