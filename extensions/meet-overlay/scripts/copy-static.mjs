import { cpSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const extRoot = join(scriptsDir, "..");
const dist = join(extRoot, "dist");

// Background worker (second Vite pass; does not empty dist).
await build({
  configFile: join(extRoot, "vite.config.ts"),
  mode: "background",
});

mkdirSync(join(dist, "icons"), { recursive: true });
cpSync(join(extRoot, "public", "icons"), join(dist, "icons"), { recursive: true });
cpSync(join(extRoot, "public", "api-config.json"), join(dist, "api-config.json"));

const manifest = {
  manifest_version: 3,
  name: "Interview Integrity — Meet Overlay",
  version: "0.2.0",
  description:
    "Floating Interview Integrity overlay for Google Meet. Demo simulation + localhost offline analysis — no Meet capture.",
  action: {
    default_title: "Open Interview Integrity overlay",
    default_icon: {
      16: "icons/icon-16.png",
      32: "icons/icon-32.png",
      48: "icons/icon-48.png",
      128: "icons/icon-128.png",
    },
  },
  icons: {
    16: "icons/icon-16.png",
    32: "icons/icon-32.png",
    48: "icons/icon-48.png",
    128: "icons/icon-128.png",
  },
  background: {
    service_worker: "background.js",
    type: "module",
  },
  content_scripts: [
    {
      matches: ["https://meet.google.com/*"],
      js: ["content.js"],
      run_at: "document_idle",
    },
  ],
  // Meet page injection + loopback-only local API. No microphone/tabCapture/desktopCapture.
  host_permissions: [
    "https://meet.google.com/*",
    "http://127.0.0.1:8765/*",
    "http://localhost:8765/*",
  ],
};

writeFileSync(join(dist, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");

for (const file of [
  "manifest.json",
  "content.js",
  "background.js",
  "api-config.json",
  "icons/icon-48.png",
]) {
  readFileSync(join(dist, file));
}

console.log("Extension static files copied → dist/");
