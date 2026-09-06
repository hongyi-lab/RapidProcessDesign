/** @type {import('next').NextConfig} */
const publicDemo = process.env.NEXT_PUBLIC_RAPID_PUBLIC_DEMO === "true";
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.NEXT_DIST_DIR || ".next",
  ...(publicDemo ? { output: "standalone" } : {}),
  async rewrites() {
    if (!publicDemo) return [];
    const api = process.env.RAPID_API_PROXY_URL || "http://127.0.0.1:8900";
    return [
      { source: "/api/rapid-design/:path*", destination: `${api}/api/rapid-design/:path*` },
      { source: "/health", destination: `${api}/health` },
    ];
  },
};

export default nextConfig;
