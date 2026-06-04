import { describe, it, expect } from "vitest";
import { encode, MemoryStore } from "@halo-format/halo";
import {
  sizeOf,
  parseToolOutput,
  serializeEnvelope,
  shapeOf,
  previewOf,
  type FieldHint,
} from "../src/serialize.js";

describe("sizeOf", () => {
  it("measures strings and objects in bytes, and is 0 for nullish", () => {
    expect(sizeOf("abc")).toBe(3);
    expect(sizeOf("é")).toBe(2); // 2 UTF-8 bytes
    expect(sizeOf({ a: 1 })).toBe(JSON.stringify({ a: 1 }).length);
    expect(sizeOf(null)).toBe(0);
    expect(sizeOf(undefined)).toBe(0);
  });

  it("never throws on an unserializable value", () => {
    const cyclic: Record<string, unknown> = {};
    cyclic.self = cyclic;
    expect(sizeOf(cyclic)).toBe(0);
  });
});

describe("parseToolOutput", () => {
  it("parses a JSON string into a value", () => {
    expect(parseToolOutput('{"a":1}')).toEqual({ a: 1 });
    expect(parseToolOutput("[1,2,3]")).toEqual([1, 2, 3]);
  });

  it("keeps plain prose as a string leaf", () => {
    expect(parseToolOutput("hello world")).toBe("hello world");
    expect(parseToolOutput("not json {oops")).toBe("not json {oops");
  });

  it("unwraps the MCP content-block shape to its (parsed) text", () => {
    expect(parseToolOutput({ content: [{ type: "text", text: '{"k":2}' }] })).toEqual({ k: 2 });
    expect(
      parseToolOutput({ content: [{ type: "text", text: "a" }, { type: "text", text: "b" }] }),
    ).toBe("ab");
  });

  it("unwraps a BARE content-block array (the shape some SDK hosts hand the hook)", () => {
    expect(parseToolOutput([{ type: "text", text: '{"issue":{"id":"1"},"events":[]}' }])).toEqual({
      issue: { id: "1" },
      events: [],
    });
    // A genuine JSON array (not content blocks) is returned as-is, not unwrapped.
    expect(parseToolOutput([1, 2, 3])).toEqual([1, 2, 3]);
  });

  it("returns already-structured values unchanged, and undefined for nullish", () => {
    expect(parseToolOutput({ a: [1, 2] })).toEqual({ a: [1, 2] });
    expect(parseToolOutput(42)).toBe(42);
    expect(parseToolOutput(null)).toBeUndefined();
  });
});

describe("shapeOf / previewOf", () => {
  it("tags a value's structural kind with a size for strings/arrays/objects", () => {
    expect(shapeOf(1843)).toBe("number");
    expect(shapeOf(null)).toBe("null");
    expect(shapeOf("checkout-api")).toBe("string[12]");
    expect(shapeOf([1, 2, 3])).toBe("array[3]");
    expect(shapeOf({ a: 1, b: 2 })).toBe("object{2}");
  });

  it("samples a value to a bounded single line", () => {
    expect(previewOf({ id: "BACKEND-12A" })).toBe('{"id":"BACKEND-12A"}');
    const long = previewOf("x".repeat(500));
    expect(long.length).toBeLessThanOrEqual(80);
    expect(long.endsWith("…")).toBe(true);
  });
});

describe("serializeEnvelope", () => {
  it("states the map id and root kind, lists field refs, and emits NO hashes/JSON", async () => {
    const { envelope } = await encode(
      { income: { monthly: 4200 }, debts: { monthly: 2604 }, filler: "x".repeat(2000) },
      { store: new MemoryStore() },
    );
    envelope.source = { id: "m1" };
    const out = serializeEnvelope(envelope);
    expect(out).toContain("[halo]");
    expect(out).toContain('"m1"');
    expect(out).toContain("object, 3 fields");
    expect(out).toContain("m1.income");
    // The hashed envelope and its 64-char handles are not shown to the model.
    expect(out).not.toContain(envelope.root);
    expect(out).not.toContain('"halo":"1"');
  });

  it("renders per-field hints (kind + preview) when supplied", async () => {
    const { envelope } = await encode(
      { income: { monthly: 4200 }, filler: "x".repeat(2000) },
      { store: new MemoryStore() },
    );
    envelope.source = { id: "m1", tool: "mcp__bank__get_profile" };
    const hints: FieldHint[] = [
      { ref: "m1.income", kind: "leaf", shape: "object{1}", preview: '{"monthly":4200}' },
      { ref: "m1.rows", kind: "branch", shape: "[branch] array{4}", preview: "↳ 0, 1, 2, 3" },
    ];
    const out = serializeEnvelope(envelope, hints);
    expect(out).toContain("from get_profile"); // short tool name
    expect(out).toContain('m1.income  object{1}  {"monthly":4200}');
    expect(out).toContain("m1.rows  [branch] array{4}  ↳ 0, 1, 2, 3");
  });

  it("tells the model to fetch the map itself when the root is a leaf", async () => {
    const { envelope } = await encode("just a long string ".repeat(200), {
      store: new MemoryStore(),
    });
    envelope.source = { id: "m9" };
    const out = serializeEnvelope(envelope);
    expect(out).toContain('Fetch "m9" itself');
  });
});
