import type { NextConfig } from "next";

// The browser only talks to Next.js; /api/* is proxied to FastAPI (same origin, no CORS).
// BACKEND_URL is server-side only — never expose backend settings through NEXT_PUBLIC_* variables.
const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
