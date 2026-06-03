import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));

// Resolve @halo-format/halo to its TypeScript source so the harness runs against the working tree
// without a build step. Production consumers resolve the package's `exports` (dist) as normal.
export default defineConfig({
  resolve: {
    alias: {
      "@halo-format/halo": resolve(here, "../packages/halo/src/index.ts"),
    },
  },
});
