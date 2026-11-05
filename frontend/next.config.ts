import type { NextConfig } from "next";
import { wgslTurbopackRule } from "@vgpu/wgsl/next";

// .wgsl shaders are prepared at build time by the vgpu loader, so the browser
// never ships the WGSL parser. Both bundlers are configured: Next 15 builds
// with webpack by default, and `--turbopack` uses the turbopack rule.
// PostHog reverse proxy: the browser talks to /cyrelay on our domain and
// Next.js forwards it, so ad blockers that block posthog.com don't drop events.
// The asset host is the ingestion host with "-assets" (us.i -> us-assets.i).
const posthogHost = process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "";
const posthogAssets = posthogHost.replace(/^https:\/\/(\w+)\.i\./, "https://$1-assets.i.");

const nextConfig: NextConfig = {
  // PostHog's API paths end in a slash; don't redirect them.
  skipTrailingSlashRedirect: true,
  async rewrites() {
    if (!posthogHost) return [];
    return [
      { source: "/cyrelay/static/:path*", destination: `${posthogAssets}/static/:path*` },
      { source: "/cyrelay/array/:path*", destination: `${posthogAssets}/array/:path*` },
      { source: "/cyrelay/:path*", destination: `${posthogHost}/:path*` },
    ];
  },
  turbopack: {
    rules: {
      "*.wgsl": wgslTurbopackRule({ minify: true }),
    },
  },
  webpack(config) {
    config.module ??= {};
    config.module.rules ??= [];
    config.module.rules.push({
      test: /\.wgsl$/,
      loader: "@vgpu/wgsl/loader-webpack",
      options: { minify: true },
    });
    return config;
  },
};

export default nextConfig;
