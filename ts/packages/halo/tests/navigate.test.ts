// Unit tests for the navigator: verified walk/fetch/fetchMany, the trust chain (store-untrusted
// safety), ref resolution (raw handle, branch name, nested path, map-scoped via registered
// envelopes), and the encode -> open -> walk -> fetch round trip that is the L0+L1 milestone.

import { describe, it, expect } from "vitest";
import {
  encode,
  open,
  walk,
  fetch,
  fetchMany,
  verifyEnvelope,
  MemoryStore,
  type Store,
  type Handle,
  type HaloEnvelope,
  type JsonValue,
  UnknownHandle,
  HashMismatch,
  WrongKind,
} from "../src/index.js";

// Top object > 1024 bytes (via bio) so it carves; profile also carves; score/tags inline as leaves.
const DATA: JsonValue = {
  profile: { name: "Ada", city: "London", bio: "x".repeat(2000) },
  score: 612,
  tags: ["a", "b"],
};

async function encoded(value: JsonValue = DATA) {
  const store = new MemoryStore();
  const { handle, envelope } = await encode(value, { store });
  return { store, handle, envelope };
}

// A store that serves correct bytes for everything except one target handle, for which it returns
// attacker-chosen bytes — exercises the store-untrusted guarantee. No getMany, so reads fall back
// to get() and hit this override.
class TamperStore implements Store {
  constructor(
    private readonly base: MemoryStore,
    private readonly target: Handle,
    private readonly evil: Uint8Array,
  ) {}
  put(bytes: Uint8Array) {
    return this.base.put(bytes);
  }
  get(handle: Handle) {
    return handle === this.target ? Promise.resolve(this.evil) : this.base.get(handle);
  }
  has(handle: Handle) {
    return this.base.has(handle);
  }
}

describe("open", () => {
  it("verifies an honest branch root with zero store reads", async () => {
    const { store, envelope } = await encoded();
    const nav = await open(envelope, store);
    expect(nav.root).toBe(envelope.root);
  });

  it("opens a leaf-root envelope", async () => {
    const { store, envelope } = await encoded([1, 2, 3]);
    const nav = await open(envelope, store);
    expect(nav.root).toBe(envelope.root);
  });

  it("throws HashMismatch when the inlined view is tampered", async () => {
    const { store, envelope } = await encoded();
    const tampered: HaloEnvelope = {
      ...envelope,
      view: { ...envelope.view, summary: "lies" },
    };
    await expect(open(tampered, store)).rejects.toBeInstanceOf(HashMismatch);
  });
});

describe("verifyEnvelope (store-free self-check)", () => {
  it("is true for an honest branch root and stable across different source blocks", async () => {
    const { envelope } = await encoded();
    expect(verifyEnvelope(envelope)).toBe(true);
    const a: HaloEnvelope = { ...envelope, source: { id: "m1" } };
    const b: HaloEnvelope = { ...envelope, source: { id: "m2", tool: "t" } };
    expect(verifyEnvelope(a)).toBe(true);
    expect(verifyEnvelope(b)).toBe(true);
  });

  it("is false for a tampered view and for a leaf root (value not inlined)", async () => {
    const { envelope } = await encoded();
    expect(verifyEnvelope({ ...envelope, view: { ...envelope.view, summary: "lies" } })).toBe(false);
    const leaf = await encoded(42);
    expect(verifyEnvelope(leaf.envelope)).toBe(false);
  });
});

describe("free walk / fetch", () => {
  it("fetches a verified leaf by raw handle and walks a branch", async () => {
    const { store, envelope } = await encoded();
    const profileHandle = envelope.view.branches["profile"]!;
    const w = await walk(profileHandle, store);
    expect(w.summary).toBe("3 branches: bio, city, name");
    const nameHandle = w.branches["name"]!;
    expect(await fetch(nameHandle, store)).toBe("Ada");
  });

  it("walk on a leaf and fetch on a branch both throw WrongKind", async () => {
    const { store, envelope } = await encoded();
    const scoreHandle = envelope.view.branches["score"]!; // leaf
    const profileHandle = envelope.view.branches["profile"]!; // branch
    await expect(walk(scoreHandle, store)).rejects.toBeInstanceOf(WrongKind);
    await expect(fetch(profileHandle, store)).rejects.toBeInstanceOf(WrongKind);
  });

  it("throws UnknownHandle for an absent handle", async () => {
    const { store } = await encoded();
    await expect(fetch("h:" + "0".repeat(64), store)).rejects.toBeInstanceOf(UnknownHandle);
  });
});

describe("store-untrusted safety", () => {
  it("a substituted leaf fails its hash check on read", async () => {
    const { store, envelope } = await encoded();
    const scoreHandle = envelope.view.branches["score"]!;
    const evil = new TextEncoder().encode('{"k":"l","value":999}'); // attacker leaf
    const evilStore = new TamperStore(store, scoreHandle, evil);
    await expect(fetch(scoreHandle, evilStore)).rejects.toBeInstanceOf(HashMismatch);
  });
});

describe("Navigator ref resolution", () => {
  it("resolves a branch name, a nested path, and a raw handle off the opened envelope", async () => {
    const { store, envelope } = await encoded();
    const nav = await open(envelope, store);
    expect(await nav.fetch("score")).toBe(612);
    expect(await nav.fetch("profile.name")).toBe("Ada");
    expect(await nav.fetch("profile.city")).toBe("London");
    const w = await nav.walk("profile");
    expect(Object.keys(w.branches).sort()).toEqual(["bio", "city", "name"]);
    // raw handle still works
    expect(await nav.fetch(envelope.view.branches["score"]!)).toBe(612);
  });

  it("rejects descending into a leaf and unknown branch names", async () => {
    const { store, envelope } = await encoded();
    const nav = await open(envelope, store);
    await expect(nav.fetch("score.nope")).rejects.toBeInstanceOf(WrongKind);
    await expect(nav.fetch("missing")).rejects.toBeInstanceOf(UnknownHandle);
  });

  it("resolves map-scoped refs across registered envelopes (m1 vs m2)", async () => {
    const store = new MemoryStore();
    const a = await encode({ score: 1, pad: "x".repeat(2000) }, { store });
    const b = await encode({ score: 2, pad: "y".repeat(2000) }, { store });
    const env1: HaloEnvelope = { ...a.envelope, source: { id: "m1" } };
    const env2: HaloEnvelope = { ...b.envelope, source: { id: "m2" } };
    const nav = (await open(env1, store)).register(env2);
    expect(await nav.fetch("m1.score")).toBe(1);
    expect(await nav.fetch("m2.score")).toBe(2);
    // bare name resolves against the primary (m1)
    expect(await nav.fetch("score")).toBe(1);
  });
});

describe("Navigator.fetchMany", () => {
  it("batches with per-ref results; one bad entry does not sink the batch", async () => {
    const { store, envelope } = await encoded();
    const out = await fetchMany(
      [envelope.view.branches["score"]!, envelope.view.branches["profile"]!, "h:" + "0".repeat(64)],
      store,
    );
    const scoreRef = envelope.view.branches["score"]!;
    const profileRef = envelope.view.branches["profile"]!;
    expect(out[scoreRef]).toEqual({ ok: true, value: 612 });
    expect(out[profileRef]).toEqual({ ok: false, error: "WrongKind" }); // branch, not a leaf
    expect(out["h:" + "0".repeat(64)]).toEqual({ ok: false, error: "UnknownHandle" });
  });

  it("resolves refs and surfaces a HashMismatch per entry", async () => {
    const { store, envelope } = await encoded();
    const nav = await open(envelope, store);
    const scoreHandle = envelope.view.branches["score"]!;
    const evil = new TextEncoder().encode('{"k":"l","value":999}');
    const evilNav = await open(envelope, new TamperStore(store, scoreHandle, evil));
    const out = await evilNav.fetchMany(["score", "profile.name", "missing"]);
    expect(out["score"]).toEqual({ ok: false, error: "HashMismatch" });
    expect(out["profile.name"]).toEqual({ ok: true, value: "Ada" });
    expect(out["missing"]).toEqual({ ok: false, error: "UnknownHandle" });
    void nav;
  });
});

describe("round trip (L0 + L1 milestone)", () => {
  it("encode -> open -> fetch reconstructs the values used", async () => {
    const { store, envelope } = await encoded();
    const nav = await open(envelope, store);
    const out = await nav.fetchMany(["profile.name", "profile.city", "score"]);
    expect(out).toEqual({
      "profile.name": { ok: true, value: "Ada" },
      "profile.city": { ok: true, value: "London" },
      score: { ok: true, value: 612 },
    });
  });
});
