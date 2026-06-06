import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

// Resolve @halo-format/halo to its TypeScript source so the adapter's tests run against the working
// tree with no build step, matching the conformance harness. Consumers resolve `exports` (dist).
export default defineConfig({
  resolve: {
    alias: {
      "@halo-format/halo": resolve(here, "../halo/src/index.ts"),
    },
  },
});
