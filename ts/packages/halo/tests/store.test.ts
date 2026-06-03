// Unit tests for the stores: content-addressing, idempotent dedup, immutability, missing handles,
// batch reads, filesystem persistence, and cross-store handle agreement.

import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MemoryStore, FileStore, UnknownHandle } from "../src/index.js";

const enc = new TextEncoder();
const dec = new TextDecoder();
const MISSING = "h:" + "0".repeat(64);

describe("MemoryStore", () => {
  it("put returns a content handle and dedups identical bytes", async () => {
    const s = new MemoryStore();
    const h1 = await s.put(enc.encode("hello"));
    const h2 = await s.put(enc.encode("hello"));
    expect(h1).toBe(h2);
    expect(h1).toMatch(/^h:[0-9a-f]{64}$/);
    expect(s.size).toBe(1); // stored once
  });

  it("get returns the stored bytes; unknown handle throws UnknownHandle", async () => {
    const s = new MemoryStore();
    const h = await s.put(enc.encode("x"));
    expect(dec.decode(await s.get(h))).toBe("x");
    await expect(s.get(MISSING)).rejects.toThrow(UnknownHandle);
  });

  it("has reflects presence", async () => {
    const s = new MemoryStore();
    const h = await s.put(enc.encode("y"));
    expect(await s.has(h)).toBe(true);
    expect(await s.has(MISSING)).toBe(false);
  });

  it("getMany returns undefined in place for missing entries", async () => {
    const s = new MemoryStore();
    const h = await s.put(enc.encode("present"));
    const got = await s.getMany([h, MISSING]);
    expect(got[0] && dec.decode(got[0])).toBe("present");
    expect(got[1]).toBeUndefined();
  });
});

describe("FileStore", () => {
  it("round-trips and persists across instances on the same dir", async () => {
    const dir = mkdtempSync(join(tmpdir(), "halo-fs-"));
    try {
      const a = new FileStore(dir);
      const h = await a.put(enc.encode("persisted"));

      const b = new FileStore(dir); // fresh instance, same directory
      expect(await b.has(h)).toBe(true);
      expect(dec.decode(await b.get(h))).toBe("persisted");
      await expect(b.get(MISSING)).rejects.toThrow(UnknownHandle);

      const got = await b.getMany([h, MISSING]);
      expect(got[0] && dec.decode(got[0])).toBe("persisted");
      expect(got[1]).toBeUndefined();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

it("MemoryStore and FileStore produce the same handle for the same bytes", async () => {
  const dir = mkdtempSync(join(tmpdir(), "halo-fs-"));
  try {
    const bytes = enc.encode("content-addressed regardless of store");
    const mh = await new MemoryStore().put(bytes);
    const fh = await new FileStore(dir).put(bytes);
    expect(mh).toBe(fh);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
