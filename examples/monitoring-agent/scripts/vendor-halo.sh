#!/usr/bin/env bash
# Vendor the (unpublished) Halo adapter packages into this example's node_modules.
# Run after `pnpm --filter @halo-format/{halo,claude} build`, and again after ANY
# `npm install` (npm prunes these as "extraneous" because they're not in package.json).
set -euo pipefail
cd "$(dirname "$0")/.."

TS=/Users/aj/halo/ts/packages
for pkg in halo claude; do
  test -f "$TS/$pkg/dist/index.js" || { echo "build $pkg first: (cd /Users/aj/halo/ts && pnpm --filter @halo-format/$pkg build)"; exit 1; }
  rm -rf "node_modules/@halo-format/$pkg"
  mkdir -p "node_modules/@halo-format/$pkg"
  cp -R "$TS/$pkg/package.json" "$TS/$pkg/dist" "node_modules/@halo-format/$pkg/"
done

node -e "import('@halo-format/claude').then(m=>console.log('vendored: installHalo is', typeof m.installHalo)).catch(e=>{console.error('FAILED:',e.message);process.exit(1)})"
