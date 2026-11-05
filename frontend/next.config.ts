import type { NextConfig } from "next";
import { wgslTurbopackRule } from "@vgpu/wgsl/next";

// .wgsl shaders are prepared at build time by the vgpu loader, so the browser
// never ships the WGSL parser. Both bundlers are configured: Next 15 builds
// with webpack by default, and `--turbopack` uses the turbopack rule.
const nextConfig: NextConfig = {
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
