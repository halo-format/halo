import { describe, it, expect } from "vitest";
import { createRawHalo, haloFetchToolDef, HALO_GUIDANCE } from "../src/raw.js";
import { HALO_FETCH_TOOL } from "../src/constants.js";

const big = (n: number) => "x".repeat(n);

describe("haloFetchToolDef", () => {
  it("is the halo_fetch tool in raw Messages API shape (refs: string[])", () => {
    const def = haloFetchToolDef();
    expect(def.name).toBe(HALO_FETCH_TOOL);
    expect(def.description.length).toBeGreaterThan(0);
    expect(def.input_schema.type).toBe("object");
    expect(def.input_schema.properties.refs).toEqual({
      type: "array",
      items: { type: "string" },
      description: expect.any(String),
    });
    expect(def.input_schema.required).toEqual(["refs"]);
  });
});

describe("createRawHalo", () => {
  it("exposes the toolDef, guidance, and a session", () => {
    const halo = createRawHalo();
    expect(halo.toolDef.name).toBe(HALO_FETCH_TOOL);
    expect(halo.guidance).toBe(HALO_GUIDANCE);
    expect(halo.session).toBeDefined();
  });

  it("isFetch matches the bare halo_fetch name (raw API has no mcp__ prefix)", () => {
    const halo = createRawHalo();
    expect(halo.isFetch("halo_fetch")).toBe(true);
    expect(halo.isFetch("payer_get_claim")).toBe(false);
    expect(halo.isFetch("mcp__halo__halo_fetch")).toBe(false);
  });

  it("passes a small result through as raw JSON (no encode, no map)", async () => {
    const halo = createRawHalo();
    const value = { status: "ok", n: 3 };
    const out = await halo.encodeResult("t", {}, value);
    expect(out).toBe(JSON.stringify(value));
    expect(out).not.toContain("[halo]");
  });

  it("encodes a large result into a shape map, then fetches a field back verified", async () => {
    const halo = createRawHalo();
    const value = { lines: [1, 2, 3], bulk: big(4000) };
    const out = await halo.encodeResult("payer_get_claim", { claim_id: "CLM-1" }, value);
    expect(out).toContain("[halo]");
    expect(out).toContain("CLM-1.lines"); // argJoin keys the map on the claim_id argument
    expect(out).not.toContain(big(4000)); // the bulk stays out of context

    const fetched = JSON.parse(await halo.fetch(["CLM-1.lines"]));
    expect(fetched["CLM-1.lines"]).toEqual({ ok: true, value: [1, 2, 3] });
  });

  it("respects a custom threshold", async () => {
    const halo = createRawHalo({ threshold: 10 });
    const out = await halo.encodeResult("t", { id: "m" }, { a: 1, b: 2, c: 3 });
    expect(out).toContain("[halo]");
  });

  it("shares a provided session so maps accumulate across calls", async () => {
    const a = createRawHalo();
    const b = createRawHalo({ session: a.session });
    expect(b.session).toBe(a.session);
  });
});
