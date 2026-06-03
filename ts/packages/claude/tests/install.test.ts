import { describe, it, expect } from "vitest";
import type { Options, PostToolUseHookInput, HookCallback } from "@anthropic-ai/claude-agent-sdk";
import { installHalo } from "../src/index.js";
import { HALO_MCP_SERVER, HALO_TOOL_PREFIX } from "../src/constants.js";

describe("installHalo wiring", () => {
  it("adds the PostToolUse encode hook and the halo MCP server, preserving existing config", () => {
    const existingPost = { hooks: [] } as never;
    const base: Options = {
      hooks: { PostToolUse: [existingPost], PreToolUse: [existingPost] },
      mcpServers: { other: { type: "sdk", name: "other", instance: {} } as never },
    };

    const { options } = installHalo(base);

    // PostToolUse: existing matcher kept, ours appended, excluding the halo nav tools.
    const post = options.hooks!.PostToolUse!;
    expect(post.length).toBe(2);
    expect(post[0]).toBe(existingPost);
    expect(post[1]!.matcher).toBe(`^(?!${HALO_TOOL_PREFIX})`);

    // Other hook events and other MCP servers are untouched; the halo server is added.
    expect(options.hooks!.PreToolUse).toEqual([existingPost]);
    expect(options.mcpServers!.other).toBeDefined();
    expect(options.mcpServers![HALO_MCP_SERVER]).toBeDefined();
  });

  it("works end to end: the installed hook encodes, and the session navigates the result", async () => {
    const { options, session } = installHalo({}, { now: () => "T" });
    const cb = options.hooks!.PostToolUse!.at(-1)!.hooks[0] as HookCallback;

    const payload = JSON.stringify({
      profile: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
      filler: "x".repeat(2000),
    });
    const input = {
      hook_event_name: "PostToolUse",
      tool_name: "bureau_report",
      tool_input: { applicant: 99 },
      tool_response: payload,
      tool_use_id: "u1",
      session_id: "s1",
      transcript_path: "/tmp/t",
      cwd: "/tmp",
    } as PostToolUseHookInput;

    const out = await cb(input, "u1", {} as never);
    expect((out as { hookSpecificOutput?: unknown }).hookSpecificOutput).toBeDefined();

    // The hook withheld the blob; the model pulls back just the leaf it needs, verified.
    const got = await session.fetch(["99.bureau_report.profile"]);
    expect(got["99.bureau_report.profile"]).toEqual({
      ok: true,
      value: { income: { monthly: 4200 }, debts: { monthly: 2604 } },
    });
  });
});
