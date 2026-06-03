import { describe, it, expect } from "vitest";
import type { PostToolUseHookInput } from "@anthropic-ai/claude-agent-sdk";
import { HaloSession } from "../src/session.js";
import { createEncodeHook } from "../src/encode-hook.js";
import { HALO_FETCH_TOOL, HALO_TOOL_PREFIX } from "../src/constants.js";

// A minimal PostToolUse input; only the fields the hook reads matter.
function input(toolName: string, toolResponse: unknown, toolInput: unknown = {}): PostToolUseHookInput {
  return {
    hook_event_name: "PostToolUse",
    tool_name: toolName,
    tool_input: toolInput,
    tool_response: toolResponse,
    tool_use_id: "u1",
    session_id: "s1",
    transcript_path: "/tmp/t",
    cwd: "/tmp",
  } as PostToolUseHookInput;
}

const bigResult = JSON.stringify({
  rows: Array.from({ length: 80 }, (_, i) => ({ i, v: `row-${i}-${"x".repeat(40)}` })),
});

describe("encode hook", () => {
  it("replaces a large result with the envelope (the map), not the blob", async () => {
    const s = new HaloSession({ now: () => "T" });
    const hook = createEncodeHook(s, { threshold: 2048 });
    const out = await hook(input("query_db", bigResult));

    const so = (out as { hookSpecificOutput?: { hookEventName: string; updatedToolOutput: string } })
      .hookSpecificOutput;
    expect(so).toBeDefined();
    expect(so!.hookEventName).toBe("PostToolUse");
    expect(typeof so!.updatedToolOutput).toBe("string");
    expect(so!.updatedToolOutput).toContain("[halo]");

    const json = so!.updatedToolOutput.split("\n")[1]!;
    const envelope = JSON.parse(json);
    expect(envelope.halo).toBe("1");
    expect(envelope.source.id).toBe("m1");
    expect(envelope.source.tool).toBe("query_db");
  });

  it("passes a small result through untouched (no encode)", async () => {
    const s = new HaloSession();
    const hook = createEncodeHook(s, { threshold: 2048 });
    expect(await hook(input("ping", '{"ok":true}'))).toEqual({});
  });

  it("MANDATORY: never re-encodes the halo navigation tools' own output", async () => {
    const s = new HaloSession();
    const hook = createEncodeHook(s, { threshold: 2048 });
    // A halo_fetch result is large, but encoding it would replace the leaf with a new map.
    const out = await hook(input(`${HALO_TOOL_PREFIX}${HALO_FETCH_TOOL}`, bigResult));
    expect(out).toEqual({});
    // And nothing was ingested: a fresh fetch finds no map.
    expect(await s.fetch(["m1.x"])).toEqual({ "m1.x": { ok: false, error: "UnknownHandle" } });
  });
});
