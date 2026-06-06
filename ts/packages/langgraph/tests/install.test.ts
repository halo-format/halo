import { describe, it, expect } from "vitest";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { installHalo, HaloSession } from "../src/index.js";
import { HALO_FETCH_TOOL } from "../src/constants.js";

const existing = tool(async () => "ok", {
  name: "existing",
  description: "an existing tool",
  schema: z.object({ x: z.number() }),
});

function toolNames(tools: unknown[]): string[] {
  return tools.map((t) => (t as { name: string }).name);
}

describe("installHalo wiring", () => {
  it("appends the nav tool and the middleware, preserving what was passed", () => {
    const other = { name: "OtherMiddleware" }; // a stand-in for the host's own middleware
    const result = installHalo({ tools: [existing], middleware: [other] });

    expect(toolNames(result.tools)).toEqual(["existing", HALO_FETCH_TOOL]);
    expect(result.middleware[0]).toBe(other);
    expect((result.middleware.at(-1) as { name: string }).name).toBe("HaloMiddleware");
    expect(result.session).toBeInstanceOf(HaloSession);
  });

  it("works with no inputs", () => {
    const result = installHalo();
    expect(toolNames(result.tools)).toEqual([HALO_FETCH_TOOL]);
    expect(result.middleware.length).toBe(1);
  });

  it("shares a passed-in session", () => {
    const session = new HaloSession();
    const result = installHalo({ tools: [existing], session });
    expect(result.session).toBe(session);
  });
});
