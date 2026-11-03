/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export — produces a fully static `out/` that hosts anywhere.
  output: "export",
  // Emit `route/index.html` (not `route.html`) so a hard refresh / direct URL
  // resolves on dumb static hosts (Apache/LiteSpeed) without server config.
  trailingSlash: true,
  images: {
    // Required for static export: no Next.js image optimization server at runtime.
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "picsum.photos",
        pathname: "/**",
      },
      {
        protocol: "https",
        hostname: "fastly.picsum.photos",
        pathname: "/**",
      },
    ],
  },
};

export default nextConfig;
