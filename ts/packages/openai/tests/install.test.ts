// installHalo: appends the halo_fetch tool non-destructively, returns the model-wrapping helpers bound
// to the session, and shares one session. Plus the nav tool's pure helper end-to-end.

import { describe, it, expect } from "vitest";
import { installHalo, HaloSession, haloFetch, createHaloFetchTool } from "../src/index.js";
import { HALO_FETCH_TOOL } from "../src/constants.js";

function toolName(t: unknown): string {
  return (t as { name?: string }).name ?? "";
}

describe("installHalo", () => {
  it("appends the halo_fetch tool, preserving existing tools", () => {
    const existing = { name: "existing" };
    const result = installHalo({ tools: [existing] });
    expect(result.tools.map(toolName)).toEqual(["existing", HALO_FETCH_TOOL]);
    expect(typeof result.wrapModel).toBe("function");
    expect(typeof result.wrapModelProvider).toBe("function");
    expect(result.session).toBeInstanceOf(HaloSession);
  });

  it("works with no inputs", () => {
    const result = installHalo();
    expect(result.tools.map(toolName)).toEqual([HALO_FETCH_TOOL]);
  });

  it("shares a passed session", () => {
    const session = new HaloSession();
    const result = installHalo({ tools: [], session });
    expect(result.session).toBe(session);
  });

  it("builds a function tool named halo_fetch", () => {
    const tool = createHaloFetchTool(new HaloSession()) as { name?: string; type?: string };
    expect(tool.name).toBe(HALO_FETCH_TOOL);
    expect(tool.type).toBe("function");
  });

  it("fetches a verified leaf and expands a branch end-to-end", async () => {
    const session = new HaloSession({ now: () => "T" });
    // padded past the inline-carve threshold so top-level fields become navigable branches
    const value = { income: { monthly: 4200, annual: 50400, pad: "y".repeat(2000) }, score: 612 };
    await session.ingest("bureau", { applicant: 99 }, value);
    const res = await haloFetch(session, ["99.score", "99.income"]);
    expect(res["99.score"]).toEqual({ ok: true, value: 612 });
    expect((res["99.income"] as { kind?: string }).kind).toBe("branch");
  });
});
