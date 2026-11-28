import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
const index = await readFile("dist/index.html", "utf8");
const jsPath = index.match(/<script[^>]*src="([^"]+)"/)[1];
const cssPath = index.match(/<link[^>]*href="([^"]+\.css)"/)[1];
const script = (
  await readFile(resolve("dist", jsPath.replace(/^\//, "")), "utf8")
).replaceAll("</script", "<\\/script");
const styles = await readFile(
  resolve("dist", cssPath.replace(/^\//, "")),
  "utf8",
);
await writeFile(
  "../standalone-preview.html",
  `<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Techstra | Interview Review Mock</title><style>${styles}</style></head><body><div id="root"></div><script type="module">${script}</script></body></html>`,
);
console.log("Updated standalone-preview.html");
