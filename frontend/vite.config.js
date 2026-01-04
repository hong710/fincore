import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  root: ".",
  base: "/static/app/",
  build: {
    outDir: "../backend/static/app",
    manifest: true,
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, "src/main.js"),
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
  },
  css: {
    postcss: "./postcss.config.js",
  },
});
