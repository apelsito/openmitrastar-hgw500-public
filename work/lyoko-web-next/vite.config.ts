import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

export default defineConfig({
  plugins: [preact()],
  base: "./",
  // Local demo API only. This proxy is not shipped in router static assets.
  server: { host: "127.0.0.1", proxy: { "/api/v1": "http://127.0.0.1:4180" } },
  preview: { host: "127.0.0.1", proxy: { "/api/v1": "http://127.0.0.1:4180" } },
  build: {
    target: "es2020",
    cssCodeSplit: true,
    sourcemap: false,
    assetsInlineLimit: 2048,
    reportCompressedSize: true,
    rollupOptions: {
      output: {
        entryFileNames: "assets/lyoko-[hash].js",
        chunkFileNames: "assets/chunk-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  }
});
