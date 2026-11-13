/** Local development API configuration (loopback only). */

export type ApiClientConfig = {
  apiBaseUrl: string;
  allowedHosts: string[];
};

export const DEFAULT_API_CONFIG: ApiClientConfig = {
  apiBaseUrl: "http://127.0.0.1:8765",
  allowedHosts: ["127.0.0.1", "localhost"],
};

export function assertLoopbackApiBaseUrl(url: string, allowedHosts: string[]): URL {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("Invalid API base URL");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("API base URL must be http(s)");
  }
  if (!allowedHosts.includes(parsed.hostname)) {
    throw new Error("API base URL host is not an allowed loopback host");
  }
  if (parsed.hostname === "0.0.0.0") {
    throw new Error("API base URL must not use 0.0.0.0");
  }
  return parsed;
}

export function isSafeRelativePath(value: string): boolean {
  const v = value.trim().replace(/\\/g, "/");
  if (!v || v.startsWith("/") || v.includes("://") || v.includes("..")) return false;
  if (/^[a-zA-Z]:/.test(v)) return false;
  return true;
}
