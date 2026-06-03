// Unit tests for the encode pipeline: carve, summarize, encode, extend, merge. These defend the
// load-bearing invariants (determinism, content-addressing, Merkle integrity, dedup) that the
// shared whole-tree envelope vectors will later pin cross-port. The CROSS_PORT_ROOT literal is the
// root handle the Python port produces for the same input — asserting it here is a real
// cross-implementation lock without needing a vector file yet.

import { describe, it, expect } from "vitest";
import {
  encode,
  extend,
  merge,
  autoCarve,
  makeAutoCarve,
  deriveSummary,
  MemoryStore,
  serialize,
  branchNode,
  leafNode,
  decode,
  nodeHandle,
  isBranch,
  WrongKind,
  type JsonValue,
} from "../src/index.js";

// The credit-report-shaped fixture, with a `note` big enough to force the top object to carve.
const FIXTURE: JsonValue = {
  income: { monthly: 4200 },
  debts: { monthly: 2604 },
  inquiries: [1, 2, 3],
  tradelines: ["a", "b", "c", "d", "e", "f", "g"],
  note: "x".repeat(2000),
};

// Root handle the Python port produces for FIXTURE — the cross-port interop lock.
const CROSS_PORT_ROOT = "h:41d7286f74ae2aeb6ca69823ddf25b9381dccba488602c1a8347a6b5eb163223";

describe("autoCarve", () => {
  it("inlines primitives, empty containers, and small objects as leaves", () => {
    expect(autoCarve(42, [])).toEqual({ as: "leaf" });
    expect(autoCarve("s", [])).toEqual({ as: "leaf" });
    expect(autoCarve(null, [])).toEqual({ as: "leaf" });
    expect(autoCarve({}, [])).toEqual({ as: "leaf" });
    expect(autoCarve([], [])).toEqual({ as: "leaf" });
    expect(autoCarve({ a: 1 }, [])).toEqual({ as: "leaf" }); // small object inlines
  });

  it("carves a large object one branch per key", () => {
    const big = { a: "x".repeat(2000), b: 1 };
    const d = autoCarve(big, []);
    expect(d.as).toBe("branch");
    if (d.as === "branch") expect(Object.keys(d.children).sort()).toEqual(["a", "b"]);
  });

  it("chunks an array longer than the threshold into contiguous slices", () => {
    const arr = Array.from({ length: 60 }, (_, i) => i);
    const d = makeAutoCarve({ arrayThreshold: 25 })(arr, []);
    expect(d.as).toBe("branch");
    if (d.as === "branch") {
      expect(Object.keys(d.children)).toEqual(["0", "1", "2"]);
      expect(d.children["0"]).toEqual(arr.slice(0, 25));
      expect(d.children["2"]).toEqual(arr.slice(50, 60));
    }
  });

  it("forces branching with inlineBytes:0", () => {
    expect(makeAutoCarve({ inlineBytes: 0 })({ a: 1 }, []).as).toBe("branch");
  });
});

describe("deriveSummary", () => {
  it("is deterministic and sorts names by UTF-16 code unit", () => {
    expect(deriveSummary(null, {})).toBe("0 branches");
    expect(deriveSummary(null, { child: "h:x" })).toBe("1 branch: child");
    expect(deriveSummary(null, { income: "h:1", debts: "h:2" })).toBe(
      "2 branches: debts, income",
    );
  });
});

describe("encode", () => {
  it("is deterministic and byte-identical to the Python port", async () => {
    const a = await encode(FIXTURE, { store: new MemoryStore() });
    const b = await encode(FIXTURE, { store: new MemoryStore() });
    expect(a.handle).toBe(b.handle);
    expect(a.handle).toBe(CROSS_PORT_ROOT);
    expect(a.envelope).toEqual(b.envelope);
  });

  it("returns a well-formed envelope whose view inlines the root branch", async () => {
    const store = new MemoryStore();
    const { handle, envelope } = await encode(FIXTURE, { store });
    expect(envelope.halo).toBe("1");
    expect(envelope.alg).toBe("sha256");
    expect(envelope.root).toBe(handle);
    expect(envelope.view.summary).toBe("5 branches: debts, income, inquiries, note, tradelines");
    expect(Object.keys(envelope.view.branches).sort()).toEqual([
      "debts",
      "income",
      "inquiries",
      "note",
      "tradelines",
    ]);
  });

  it("content-addresses the root: handle == hash(canonical(root node))", async () => {
    const store = new MemoryStore();
    const { handle, envelope } = await encode(FIXTURE, { store });
    const rootNode = branchNode(envelope.view.summary, envelope.view.branches);
    expect(nodeHandle(rootNode)).toBe(handle);
  });

  it("Merkle integrity: changing any leaf changes the root handle", async () => {
    const changed = { ...(FIXTURE as Record<string, JsonValue>), income: { monthly: 4201 } };
    const a = await encode(FIXTURE, { store: new MemoryStore() });
    const b = await encode(changed, { store: new MemoryStore() });
    expect(b.handle).not.toBe(a.handle);
  });

  it("dedup: equal subtrees are stored once", async () => {
    const store = new MemoryStore();
    // two top-level branches with identical (large) subtrees -> the subtree leaf is stored once
    const sub = { blob: "y".repeat(2000) };
    await encode({ left: sub, right: sub, pad: "z".repeat(2000) }, { store });
    // root + 3 children, but left and right share one leaf -> 4 nodes, not 5
    expect(store.size).toBe(4);
  });

  it("encodes a leaf root with a structural view summary", async () => {
    const store = new MemoryStore();
    const { envelope } = await encode([1, 2, 3], { store });
    expect(envelope.view.summary).toBe("leaf: array of 3 items");
    expect(envelope.view.branches).toEqual({});
  });
});

describe("extend", () => {
  it("adds a branch, reuses existing child handles, and stores only the new root + child", async () => {
    const store = new MemoryStore();
    const base = await encode({ a: "x".repeat(2000), b: "y".repeat(2000) }, { store });
    const sizeBefore = store.size;
    const ext = await extend(base.handle, "c", "z".repeat(2000), { store });
    expect(Object.keys(ext.envelope.view.branches).sort()).toEqual(["a", "b", "c"]);
    // unchanged children a, b reused; only a new leaf c and a new root are added
    expect(store.size).toBe(sizeBefore + 2);
    // the prior root survives (immutability -> version history)
    expect(await store.has(base.handle)).toBe(true);
  });

  it("last write wins on a name collision", async () => {
    const store = new MemoryStore();
    const base = await encode({ a: "x".repeat(2000), b: "y".repeat(2000) }, { store });
    const ext = await extend(base.handle, "a", "new", { store });
    const aHandle = ext.envelope.view.branches["a"];
    expect(decode(await store.get(aHandle))).toEqual(leafNode("new"));
  });

  it("rejects a non-branch root", async () => {
    const store = new MemoryStore();
    const leaf = await encode(42, { store }); // primitive -> leaf root
    await expect(extend(leaf.handle, "x", 1, { store })).rejects.toBeInstanceOf(WrongKind);
  });
});

describe("merge", () => {
  it("combines branch tables, last write wins in order", async () => {
    const store = new MemoryStore();
    const m1 = await encode({ a: "x".repeat(2000), b: "y".repeat(2000) }, { store });
    const m2 = await encode({ b: "Y".repeat(2000), c: "z".repeat(2000) }, { store });
    const merged = await merge([m1.handle, m2.handle], { store });
    expect(Object.keys(merged.envelope.view.branches).sort()).toEqual(["a", "b", "c"]);
    // b came from m2 (last write)
    const m2Node = decode(await store.get(m2.handle));
    if (isBranch(m2Node)) {
      expect(merged.envelope.view.branches["b"]).toBe(m2Node.branches["b"]);
    }
  });
});
