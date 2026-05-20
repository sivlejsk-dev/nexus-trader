import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Produces a self-contained server.js in .next/standalone — used by the
  // production Dockerfile to avoid shipping node_modules in the final image.
  output: "standalone",

  async rewrites() {
    const backend = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
