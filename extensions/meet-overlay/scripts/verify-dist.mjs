import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const required = ["manifest.json", "content.js", "background.js", "icons/icon-16.png", "icons/icon-48.png", "icons/icon-128.png"];

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
const perms = [...(manifest.permissions ?? []), ...(manifest.host_permissions ?? [])];
const unexpected = perms.filter((p) => p !== "https://meet.google.com/*");
if (unexpected.length) {
  console.error("unexpected permissions:", unexpected);
  failed = true;
}

const content = readFileSync(join(dist, "content.js"), "utf8");
for (const needle of ["getUserMedia", "tabCapture", "desktopCapture", "webkitGetUserMedia"]) {
  if (content.includes(needle)) {
    console.error(`content.js unexpectedly references ${needle}`);
    failed = true;
  }
}

if (failed) {
  process.exit(1);
}
console.log("dist verification OK (MV3, Meet-only, no capture APIs detected).");
