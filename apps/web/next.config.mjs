/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The repo root is two levels up; tell Next so it does not guess wrong in the monorepo.
  outputFileTracingRoot: new URL('../../', import.meta.url).pathname,
};

export default nextConfig;
