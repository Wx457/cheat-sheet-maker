import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // 根路径在路由层重定向到编辑器：不渲染 "/" segment，
  // 避免 page 里 redirect() 抛 NEXT_REDIRECT 导致 cacheComponents 的 instant 校验失败
  async redirects() {
    return [{ source: '/', destination: '/editor', permanent: false }]
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
