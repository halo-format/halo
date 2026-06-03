// Conformance harness (TypeScript).
//
// Loads the shared vectors from ../../conformance/vectors and asserts @halo-format/halo matches
// them: canonical bytes and handles. These are the same vectors the Python harness runs,
// generated with an independent JCS oracle (rfc8785), so a port reproducing them is a genuine
// cross-implementation check — and a halo produced in one port verifies and navigates in the other.

import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  canonical,
  handleOf,
  serialize,
  nodeHandle,
  decode,
  type Node,
} from "@halo-format/halo";

const here = dirname(fileURLToPath(import.meta.url));
const VECTORS = join(here, "..", "..", "conformance", "vectors");

type CanonicalCase = { name: string; input: unknown; canonical: string };
type HandleCase = { name: string; input: unknown; handle: string };
type NodeCase = { name: string; node: Node; canonical: string; handle: string };

const dec = new TextDecoder();

function loadCases<T>(kind: string): Array<{ file: string; case: T }> {
  const dir = join(VECTORS, kind);
  const out: Array<{ file: string; case: T }> = [];
  for (const file of readdirSync(dir).sort()) {
    if (!file.endsWith(".json")) continue;
    const data = JSON.parse(readFileSync(join(dir, file), "utf8")) as { cases: T[] };
    for (const c of data.cases) out.push({ file, case: c });
  }
  return out;
}

describe("conformance: canonical", () => {
  for (const { file, case: c } of loadCases<CanonicalCase>("canonical")) {
    it(`${file} :: ${c.name}`, () => {
      expect(canonical(c.input as never)).toBe(c.canonical);
    });
  }
});

describe("conformance: handles", () => {
  for (const { file, case: c } of loadCases<HandleCase>("handles")) {
    it(`${file} :: ${c.name}`, () => {
      expect(handleOf(c.input as never)).toBe(c.handle);
    });
  }
});

describe("conformance: nodes", () => {
  for (const { file, case: c } of loadCases<NodeCase>("nodes")) {
    it(`${file} :: ${c.name}`, () => {
      expect(dec.decode(serialize(c.node))).toBe(c.canonical);
      expect(nodeHandle(c.node)).toBe(c.handle);
      // round-trip: decode(serialize(node)) reconstructs the node
      expect(decode(serialize(c.node))).toEqual(c.node);
    });
  }
});
