import { describe, it, expect } from "vitest";
import { encode, MemoryStore } from "@halo-format/halo";
import { sizeOf, parseToolOutput, serializeEnvelope } from "../src/serialize.js";

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

  it("returns already-structured values unchanged, and undefined for nullish", () => {
    expect(parseToolOutput({ a: [1, 2] })).toEqual({ a: [1, 2] });
    expect(parseToolOutput(42)).toBe(42);
    expect(parseToolOutput(null)).toBeUndefined();
  });
});

describe("serializeEnvelope", () => {
  it("prefixes a one-line note naming the map and refs, then the envelope JSON", async () => {
    const { envelope } = await encode(
      { income: { monthly: 4200 }, debts: { monthly: 2604 }, filler: "x".repeat(2000) },
      { store: new MemoryStore() },
    );
    envelope.source = { id: "m1" };
    const out = serializeEnvelope(envelope);
    const [note, json] = out.split("\n");
    expect(note).toContain("[halo]");
    expect(note).toContain('"m1"');
    expect(note).toContain("m1.income");
    expect(JSON.parse(json!)).toEqual(envelope);
  });
});
