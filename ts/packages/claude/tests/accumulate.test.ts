import { describe, it, expect } from "vitest";
import { argJoin } from "../src/accumulate.js";

describe("argJoin (default entity-key policy)", () => {
  it("keys on the first scalar argument value, regardless of field name", () => {
    expect(argJoin("get_customer", { id: 123 })).toBe("123");
    expect(argJoin("get_appointments", { customerId: 123 })).toBe("123");
    // Both detail calls about customer 123 land under the same map id, so they fold into one map.
  });

  it("keys on the argument value, not on field names — different fields, same value, same key", () => {
    expect(argJoin("a", { customerId: 123 })).toBe(argJoin("b", { id: 123, extra: "x" }));
  });

  it("keeps a search-style call its own map (its scalar is the query, shared by nothing)", () => {
    expect(argJoin("search", { query: "smith" })).toBe("smith");
    expect(argJoin("search", { query: "smith" })).not.toBe(argJoin("get_customer", { id: 123 }));
  });

  it("handles bare scalars and arrays", () => {
    expect(argJoin("t", 42)).toBe("42");
    expect(argJoin("t", "abc")).toBe("abc");
    expect(argJoin("t", [7, 8])).toBe("7");
  });

  it("returns null when there is no id-like scalar (so the call gets a fresh map id)", () => {
    expect(argJoin("list_all", {})).toBeNull();
    expect(argJoin("noop", undefined)).toBeNull();
    expect(argJoin("t", { active: true })).toBeNull(); // booleans are not id-like
    expect(argJoin("t", { body: "x".repeat(200) })).toBeNull(); // long strings are free text
  });
});
