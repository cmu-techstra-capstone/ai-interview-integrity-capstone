import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const root = path.dirname(fileURLToPath(import.meta.url));

/**
 * Two Vite builds keep the content script a single IIFE (Chrome-friendly)
 * while the service worker stays a small ES module with no React.
 */
export default defineConfig(({ mode }) => {
  const isBackground = mode === "background";
  const isHarness = mode === "harness";

  if (isBackground) {
    return {
      publicDir: false,
      build: {
        outDir: "dist",
        emptyOutDir: false,
        sourcemap: false,
        minify: true,
        lib: {
          entry: path.resolve(root, "src/background/service-worker.ts"),
          formats: ["es"],
          fileName: () => "background.js",
        },
        rollupOptions: {
          output: {
            inlineDynamicImports: true,
          },
        },
      },
    };
  }

  if (isHarness) {
    return {
      plugins: [react()],
      publicDir: false,
      define: {
        "process.env.NODE_ENV": JSON.stringify("production"),
      },
      build: {
        outDir: "dist",
        emptyOutDir: false,
        sourcemap: false,
        minify: true,
        lib: {
          entry: path.resolve(root, "src/harness/main.tsx"),
          name: "InterviewIntegrityLocalHarness",
          formats: ["iife"],
          fileName: () => "harness.js",
        },
        rollupOptions: {
          output: {
            inlineDynamicImports: true,
            assetFileNames: "assets/[name][extname]",
          },
        },
      },
    };
  }

  return {
    plugins: [react()],
    publicDir: false,
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
      sourcemap: false,
      minify: true,
      lib: {
        entry: path.resolve(root, "src/content/main.tsx"),
        name: "InterviewIntegrityMeetOverlay",
        formats: ["iife"],
        fileName: () => "content.js",
      },
      rollupOptions: {
        output: {
          inlineDynamicImports: true,
          assetFileNames: "assets/[name][extname]",
        },
      },
    },
  };
});
