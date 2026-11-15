import type { NextConfig } from "next";

// Where the optional /api/* rewrite forwards to (server-side only). The app itself calls the
// backend directly via NEXT_PUBLIC_API_URL; this just keeps relative /api links working.
const BACKEND_URL = (
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Self-contained server bundle (.next/standalone) for the Docker image used on Railway.
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
