import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the workspace root to this app (a stray parent lockfile was being inferred).
  turbopack: { root: __dirname },
  // Standalone output for a small Docker image on Railway.
  output: "standalone",
};

export default nextConfig;
