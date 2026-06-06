import { describe, it, expect } from "vitest";
import { ToolMessage } from "@langchain/core/messages";
import { HaloSession } from "../src/session.js";
import { rewrite } from "../src/middleware.js";

const BIG = JSON.stringify({
  profile: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
  filler: "x".repeat(3000),
});

// rewrite() reads only request.toolCall; a structural stub is enough for the unit level (the full
// ToolCallRequest, including the agent loop, is exercised in graph.test.ts).
function req(name: string, args: unknown) {
  return { toolCall: { name, args, id: "c1" } };
}

function msg(content: string, artifact?: unknown) {
  return new ToolMessage({ content, tool_call_id: "c1", name: "bureau", artifact });
}

describe("Halo encode middleware — rewrite()", () => {
  it("rewrites a large result into a shape map with the envelope as artifact", async () => {
    const session = new HaloSession({ now: () => "T" });
    const out = (await rewrite(session, 2048, msg(BIG), req("bureau", { applicant: 99 }))) as ToolMessage;

    expect(typeof out.content === "string" && out.content.startsWith('[halo] map "99"')).toBe(true);
    expect((out.artifact as { halo?: string }).halo).toBe("1");
    expect((out.artifact as { source?: { id?: string } }).source?.id).toBe("99");

    const got = await session.fetch(["99.profile"]);
    expect(got["99.profile"]).toEqual({
      ok: true,
      value: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
    });
  });

  it("passes a small result through unchanged", async () => {
    const session = new HaloSession();
    const small = msg('{"ok":true}');
    const out = await rewrite(session, 2048, small, req("ping", {}));
    expect(out).toBe(small);
  });

  it("passes a non-ToolMessage return (e.g. a Command) through unchanged", async () => {
    const session = new HaloSession();
    const command = { update: { foo: "bar" } }; // stand-in for a langgraph Command
    const out = await rewrite(session, 2048, command, req("set_state", { a: 1 }));
    expect(out).toBe(command);
  });

  it("preserves an upstream content_and_artifact tool's own artifact", async () => {
    const session = new HaloSession({ now: () => "T" });
    const out = (await rewrite(session, 2048, msg(BIG, { mine: 1 }), req("t", { a: 7 }))) as ToolMessage;
    expect((out.artifact as { halo?: string }).halo).toBe("1"); // Halo's envelope takes the slot
    expect(out.additional_kwargs.halo_prior_artifact).toEqual({ mine: 1 }); // upstream kept
  });

  it("returns a fresh message and does not mutate the handler's message", async () => {
    const session = new HaloSession({ now: () => "T" });
    const original = msg(BIG);
    const out = (await rewrite(session, 2048, original, req("bureau", { applicant: 99 }))) as ToolMessage;
    expect(out).not.toBe(original);
    expect(original.content).toBe(BIG); // untouched
    expect(out.tool_call_id).toBe("c1"); // identity preserved
  });
});
