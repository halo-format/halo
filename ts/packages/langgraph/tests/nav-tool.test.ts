import { describe, it, expect } from "vitest";
import { ToolMessage } from "@langchain/core/messages";
import { HaloSession } from "../src/session.js";
import { createHaloFetchTool, haloFetch } from "../src/nav-tool.js";
import { HALO_FETCH_TOOL } from "../src/constants.js";

// Large enough (> the core's 1024-byte inline threshold) that the top-level object carves into
// branches: a scalar leaf (score) and a chunked-array branch (tradelines).
async function seed() {
  const session = new HaloSession({ now: () => "T" });
  await session.ingest("bureau", { applicant: 99 }, {
    score: 612,
    tradelines: Array.from({ length: 40 }, (_, i) => ({
      id: i,
      creditor: `Bank ${i}`,
      balance: i * 137,
      status: "open",
    })),
  });
  return session;
}

describe("halo_fetch navigation tool", () => {
  it("fetches a leaf verified", async () => {
    const session = await seed();
    const got = await haloFetch(session, ["99.score"]);
    expect(got["99.score"]).toEqual({ ok: true, value: 612 });
  });

  it("returns a branch ref's sub-shape instead of erroring", async () => {
    const session = await seed();
    const got = await haloFetch(session, ["99.tradelines"]);
    const entry = got["99.tradelines"];
    expect(entry && "kind" in entry && entry.kind).toBe("branch");
    expect(entry && "fields" in entry && entry.fields.some((f) => f.ref === "99.tradelines.0")).toBe(true);
  });

  it("surfaces a bad ref as a per-entry error without sinking the batch", async () => {
    const session = await seed();
    const got = await haloFetch(session, ["99.score", "99.missing"]);
    expect(got["99.score"]!.ok).toBe(true);
    expect(got["99.missing"]!.ok).toBe(false);
  });

  it("is named halo_fetch and returns content + artifact when invoked", async () => {
    const session = await seed();
    const t = createHaloFetchTool(session);
    expect(t.name).toBe(HALO_FETCH_TOOL);
    const msg = (await t.invoke({
      name: HALO_FETCH_TOOL,
      args: { refs: ["99.score"] },
      id: "c1",
      type: "tool_call",
    })) as ToolMessage;
    expect(JSON.parse(msg.content as string)["99.score"]).toEqual({ ok: true, value: 612 });
    expect((msg.artifact as Record<string, unknown>)["99.score"]).toEqual({ ok: true, value: 612 });
  });
});
