import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const required = [
  "manifest.json",
  "content.js",
  "background.js",
  "harness.js",
  "harness.html",
  "api-config.json",
  "icons/icon-16.png",
  "icons/icon-48.png",
  "icons/icon-128.png",
];

let failed = false;
for (const rel of required) {
  const path = join(dist, rel);
  if (!existsSync(path)) {
    console.error("MISSING", rel);
    failed = true;
  }
}

const manifest = JSON.parse(readFileSync(join(dist, "manifest.json"), "utf8"));
if (manifest.manifest_version !== 3) {
  console.error("manifest_version must be 3");
  failed = true;
}
const matches = manifest.content_scripts?.[0]?.matches ?? [];
if (!matches.includes("https://meet.google.com/*")) {
  console.error("content_scripts must target https://meet.google.com/*");
  failed = true;
}
if (JSON.stringify(manifest).includes("tabCapture") || JSON.stringify(manifest).includes("desktopCapture")) {
  console.error("capture permissions must not be present");
  failed = true;
}

const allowedHostPerms = new Set([
  "https://meet.google.com/*",
  "http://127.0.0.1:8765/*",
  "http://localhost:8765/*",
]);
const perms = [...(manifest.permissions ?? []), ...(manifest.host_permissions ?? [])];
const unexpected = perms.filter((p) => !allowedHostPerms.has(p));
if (unexpected.length) {
  console.error("unexpected permissions:", unexpected);
  failed = true;
}
for (const need of allowedHostPerms) {
  if (!perms.includes(need)) {
    console.error("missing expected host permission:", need);
    failed = true;
  }
}

const content = readFileSync(join(dist, "content.js"), "utf8");
const background = readFileSync(join(dist, "background.js"), "utf8");
for (const needle of ["getUserMedia", "tabCapture", "desktopCapture", "webkitGetUserMedia"]) {
  if (content.includes(needle) || background.includes(needle)) {
    console.error(`bundle unexpectedly references ${needle}`);
    failed = true;
  }
}

const apiConfig = JSON.parse(readFileSync(join(dist, "api-config.json"), "utf8"));
if (!String(apiConfig.apiBaseUrl || "").includes("127.0.0.1") && !String(apiConfig.apiBaseUrl || "").includes("localhost")) {
  console.error("api-config.json must point at loopback");
  failed = true;
}

if (failed) {
  process.exit(1);
}
console.log("dist verification OK (MV3, Meet + loopback API only, no capture APIs detected).");
