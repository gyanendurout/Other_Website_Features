/** @type {import('next').NextConfig} */
const nextConfig = {
  // node:sqlite is loaded through createRequire at runtime, so webpack never
  // tries to bundle it and no externals config is needed.
  reactStrictMode: true,
};

export default nextConfig;
