// End-to-end through a real createAgent loop driven by FakeToolCallingModel: the agent calls a tool,
// the Halo middleware rewrites the ToolMessage to a shape map (content) with the envelope as artifact,
// and the navigation tool's own output is passed through (not re-encoded). This is the TS parity to
// the Python compiled-graph test.

import { describe, it, expect } from "vitest";
import { tool } from "@langchain/core/tools";
import { HumanMessage, ToolMessage } from "@langchain/core/messages";
import { createAgent, FakeToolCallingModel } from "langchain";
import { z } from "zod";
import { installHalo } from "../src/index.js";

const BIG = {
  profile: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
  filler: "x".repeat(3000),
};

const bureauReport = tool(async () => JSON.stringify(BIG), {
  name: "bureau_report",
  description: "Get a bureau report.",
  schema: z.object({ applicant: z.number() }),
});

const getAppointments = tool(
  async () =>
    JSON.stringify({
      appointments: Array.from({ length: 29 }, (_, i) => ({ id: i, slot: `2026-06-${i + 1}` })),
    }),
  {
    name: "get_appointments",
    description: "Get appointments for an applicant.",
    schema: z.object({ applicant: z.number() }),
  },
);

// FakeToolCallingModel emits toolCalls[turn] each generation; an empty array ends the agent.
function model(turns: { name: string; args: unknown; id: string }[][]) {
  return new FakeToolCallingModel({
    toolCalls: turns.map((t) => t.map((c) => ({ ...c, type: "tool_call" as const }))) as never,
  });
}

function toolMessages(messages: unknown[]): ToolMessage[] {
  return messages.filter((m): m is ToolMessage => m instanceof ToolMessage);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function agentFor(tools: unknown[], turns: any, opts: { threshold?: number } = {}) {
  const { tools: allTools, middleware, session } = installHalo({
    tools,
    threshold: opts.threshold,
    now: () => "T",
  });
  const agent = createAgent({
    model: model(turns),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    tools: allTools as any,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    middleware: middleware as any,
  });
  return { agent, session };
}

describe("Halo adapter in a real createAgent loop", () => {
  it("withholds a large tool result as a shape map and exposes it via the session", async () => {
    const { agent, session } = agentFor(
      [bureauReport],
      [[{ name: "bureau_report", args: { applicant: 99 }, id: "c1" }], []],
    );
    const out = await agent.invoke({ messages: [new HumanMessage("check applicant 99")] });

    const tm = toolMessages(out.messages).find((m) => m.tool_call_id === "c1")!;
    expect(typeof tm.content === "string" && tm.content.startsWith('[halo] map "99"')).toBe(true);
    expect((tm.artifact as { halo?: string }).halo).toBe("1");

    // the payload never entered the model context; the session fetches it back, verified
    const got = await session.fetch(["99.profile"]);
    expect(got["99.profile"]).toEqual({
      ok: true,
      value: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
    });
  });

  it("does not re-encode the navigation tool's own output", async () => {
    const { agent } = agentFor(
      [bureauReport],
      [
        [{ name: "bureau_report", args: { applicant: 99 }, id: "c1" }],
        [{ name: "halo_fetch", args: { refs: ["99.profile"] }, id: "c2" }],
        [],
      ],
    );
    const out = await agent.invoke({ messages: [new HumanMessage("check applicant 99")] });

    const fetchMsg = toolMessages(out.messages).find((m) => m.tool_call_id === "c2")!;
    expect(typeof fetchMsg.content === "string" && fetchMsg.content.startsWith("[halo] map")).toBe(false);
    expect(fetchMsg.content).toContain("income");
  });

  it("folds two calls sharing an argument into one entity map", async () => {
    const { agent } = agentFor(
      [bureauReport, getAppointments],
      [
        [{ name: "bureau_report", args: { applicant: 123 }, id: "c1" }],
        [{ name: "get_appointments", args: { applicant: 123 }, id: "c2" }],
        [],
      ],
      { threshold: 256 },
    );
    const out = await agent.invoke({ messages: [new HumanMessage("applicant 123")] });

    const second = toolMessages(out.messages).find((m) => m.tool_call_id === "c2")!;
    const env = second.artifact as { source?: { id?: string }; view: { branches: Record<string, unknown> } };
    expect(env.source?.id).toBe("123");
    expect(Object.keys(env.view.branches).sort()).toEqual(["bureau_report", "get_appointments"]);
  });
});
