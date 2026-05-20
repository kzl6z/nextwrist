/** Cloudflare Workers expose secrets on `env`, not always on `process.env`. */
export function applyWorkerEnv(env: unknown): void {
  if (!env || typeof env !== "object") return;
  for (const [key, value] of Object.entries(env as Record<string, unknown>)) {
    if (typeof value === "string" && value.length > 0) {
      process.env[key] = value;
    }
  }
}
