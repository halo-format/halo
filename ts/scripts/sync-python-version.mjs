// Keep the Python packages on the same version as the npm packages.
//
// Halo ships four packages on one shared (locked) version: the two npm packages
// (@halo-format/halo, @halo-format/claude — locked together via Changesets `fixed`)
// and the two PyPI packages (halo-format, halo-format-claude). Changesets only knows
// about the npm side, so this script copies the canonical npm version into the Python
// pyproject.toml files.
//
// It runs in two places:
//   1. `pnpm version` (the Changesets version step) — so the Version PR carries the
//      bumped pyproject.toml alongside the bumped package.json files.
//   2. the release workflow, just before building the Python sdists — so the published
//      wheel/sdist always carries the right version even if step 1's edit (which lives
//      outside the Changesets cwd) was not committed.
//
// Idempotent: writing the same version twice is a no-op.

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url)); // ts/scripts
const repoRoot = resolve(here, "..", ".."); // repo root

const canonical = resolve(repoRoot, "ts/packages/halo/package.json");
const { version } = JSON.parse(readFileSync(canonical, "utf8"));
if (!version) {
  throw new Error(`no version found in ${canonical}`);
}

const pyprojects = [
  "py/packages/halo/pyproject.toml",
  "py/packages/claude/pyproject.toml",
];

let changed = 0;
for (const rel of pyprojects) {
  const path = resolve(repoRoot, rel);
  const text = readFileSync(path, "utf8");
  // Only the top-level [project] version line (anchored, first match).
  const next = text.replace(/^version = "[^"]*"/m, `version = "${version}"`);
  if (!/^version = "[^"]*"/m.test(text)) {
    throw new Error(`no \`version = "..."\` line to update in ${rel}`);
  }
  if (next !== text) {
    writeFileSync(path, next);
    changed++;
  }
  console.log(`sync-python-version: ${rel} -> ${version}`);
}

console.log(`sync-python-version: done (${changed} file(s) changed, target ${version})`);
