// Unit tests for node decode validation and the leaf/branch kind-tag separation. The happy-path
// serialize/handle/round-trip behavior is covered by the shared node vectors in ts/conformance.

import { describe, it, expect } from "vitest";
import {
  branchNode,
  leafNode,
  serialize,
  decode,
  nodeHandle,
  isBranch,
  isLeaf,
  HaloError,
} from "../src/index.js";

const enc = new TextEncoder();

describe("node constructors + guards", () => {
  it("builds and recognizes a leaf", () => {
    const n = leafNode(42);
    expect(n).toEqual({ k: "l", value: 42 });
    expect(isLeaf(n)).toBe(true);
    expect(isBranch(n)).toBe(false);
  });
  it("builds and recognizes a branch (defensive copy of branches)", () => {
    const branches = { a: "h:aa" };
    const n = branchNode("one", branches);
    branches.a = "h:bb"; // mutate caller's map
    expect(n.branches.a).toBe("h:aa"); // node unaffected
    expect(isBranch(n)).toBe(true);
  });
});

describe("node decode validation", () => {
  it("rejects invalid JSON", () => {
    expect(() => decode(enc.encode("{bad"))).toThrow(HaloError);
  });
  it("rejects a non-object (array)", () => {
    expect(() => decode(enc.encode("[1,2]"))).toThrow(HaloError);
  });
  it("rejects an unknown kind", () => {
    expect(() => decode(enc.encode('{"k":"x"}'))).toThrow(HaloError);
  });
  it("rejects a leaf missing value", () => {
    expect(() => decode(enc.encode('{"k":"l"}'))).toThrow(HaloError);
  });
  it("rejects a branch with non-string summary", () => {
    expect(() => decode(enc.encode('{"k":"b","summary":1,"branches":{}}'))).toThrow(HaloError);
  });
  it("rejects a branch with a non-string child handle", () => {
    expect(() => decode(enc.encode('{"k":"b","summary":"s","branches":{"a":1}}'))).toThrow(HaloError);
  });
});

describe("kind tag prevents leaf/branch collision", () => {
  it("a leaf wrapping branch-shaped data hashes differently from a branch", () => {
    const leaf = leafNode({ summary: "x", branches: {} });
    const branch = branchNode("x", {});
    expect(nodeHandle(leaf)).not.toBe(nodeHandle(branch));
  });
});
