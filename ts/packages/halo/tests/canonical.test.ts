// Unit tests for behavior the JSON conformance vectors cannot express (non-finite numbers are
// not valid JSON, so they only matter at the encode API boundary).

import { describe, it, expect } from "vitest";
import { canonical, handleOf } from "../src/index.js";
import { CanonicalizationError } from "../src/errors.js";

describe("canonical: non-finite rejection", () => {
  it("rejects NaN", () => {
    expect(() => canonical(NaN as never)).toThrow(CanonicalizationError);
  });
  it("rejects Infinity", () => {
    expect(() => canonical(Infinity as never)).toThrow(CanonicalizationError);
  });
  it("rejects a non-finite number nested in an object", () => {
    expect(() => canonical({ a: 1, b: { c: -Infinity } } as never)).toThrow(CanonicalizationError);
  });
  it("rejects a non-finite number nested in an array", () => {
    expect(() => canonical([1, 2, NaN] as never)).toThrow(CanonicalizationError);
  });
});

describe("handle shape", () => {
  it("is h: + 64 lowercase hex chars", () => {
    expect(handleOf({ hello: "world" })).toMatch(/^h:[0-9a-f]{64}$/);
  });
  it("is deterministic and key-order independent", () => {
    expect(handleOf({ a: 1, b: 2 })).toBe(handleOf({ b: 2, a: 1 }));
  });
});
