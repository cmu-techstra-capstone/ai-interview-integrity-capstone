import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const required = [
  "manifest.json",
  "content.js",
  "background.js",
  "offscreen.js",
  "offscreen.html",
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

const apiPermissions = new Set(manifest.permissions ?? []);
if (!apiPermissions.has("tabCapture")) {
  console.error('manifest must include permission "tabCapture"');
  failed = true;
}
if (!apiPermissions.has("offscreen")) {
  console.error('manifest must include permission "offscreen"');
  failed = true;
}
if (apiPermissions.has("desktopCapture")) {
  console.error("desktopCapture must not be present");
  failed = true;
}

const allowedHostPerms = new Set([
  "https://meet.google.com/*",
  "http://127.0.0.1:8765/*",
  "http://localhost:8765/*",
]);
const allowedApiPerms = new Set(["tabCapture", "offscreen"]);
const hostPerms = [...(manifest.host_permissions ?? [])];
const unexpectedHosts = hostPerms.filter((p) => !allowedHostPerms.has(p));
if (unexpectedHosts.length) {
  console.error("unexpected host permissions:", unexpectedHosts);
  failed = true;
}
for (const need of allowedHostPerms) {
  if (!hostPerms.includes(need)) {
    console.error("missing expected host permission:", need);
    failed = true;
  }
}
const unexpectedApi = [...apiPermissions].filter((p) => !allowedApiPerms.has(p));
if (unexpectedApi.length) {
  console.error("unexpected api permissions:", unexpectedApi);
  failed = true;
}

const content = readFileSync(join(dist, "content.js"), "utf8");
const background = readFileSync(join(dist, "background.js"), "utf8");
const offscreen = readFileSync(join(dist, "offscreen.js"), "utf8");

// Content script must not redeem MediaStreams itself.
for (const needle of ["getUserMedia", "tabCapture", "desktopCapture", "webkitGetUserMedia"]) {
  if (content.includes(needle)) {
    console.error(`content.js unexpectedly references ${needle}`);
    failed = true;
  }
}
if (content.includes("desktopCapture") || background.includes("desktopCapture") || offscreen.includes("desktopCapture")) {
  console.error("desktopCapture must not appear in bundles");
  failed = true;
}
if (!background.includes("tabCapture") && !background.includes("getMediaStreamId")) {
  console.error("background.js must coordinate tabCapture.getMediaStreamId");
  failed = true;
}
if (!offscreen.includes("getUserMedia")) {
  console.error("offscreen.js must call getUserMedia to redeem the stream id");
  failed = true;
}
if (offscreen.includes("MediaRecorder")) {
  console.error("offscreen.js must not record/persist via MediaRecorder by default");
  failed = true;
}

const apiConfig = JSON.parse(readFileSync(join(dist, "api-config.json"), "utf8"));
if (!String(apiConfig.apiBaseUrl || "").includes("127.0.0.1") && !String(apiConfig.apiBaseUrl || "").includes("localhost")) {
  console.error("api-config.json must point at loopback");
  failed = true;
}

if (failed) {
  process.exit(1);
}
console.log(
  "dist verification OK (MV3, Meet + loopback API, tabCapture/offscreen capture foundation, no MediaRecorder).",
);
