// The navigation tools — how the model pulls back what the hook withheld. An in-process MCP server
// exposing halo_walk and halo_fetch, both backed by the session store and verified on read.
//
// halo_fetch takes an ARRAY of refs on purpose: each fetch is a separate model round trip, the
// dominant latency in the loop, so the model is nudged to gather every ref a step needs and pull
// them in one call. It returns a per-ref result, so one unknown or tampered entry (surfaced as a
// HashMismatch) never sinks the batch.
//
// The pure handlers (haloWalk / haloFetch) are split out from the MCP wrapping so they can be tested
// without the SDK runtime, and so the SDK tool() call is the only SDK-coupled line.

import { z } from "zod";
import { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { WalkResult, FetchResult } from "@halo-format/halo";
import type { HaloSession } from "./session.js";
import { HALO_MCP_SERVER, HALO_WALK_TOOL, HALO_FETCH_TOOL } from "./constants.js";

/** Walk a branch ref to its summary and child handles; never returns leaf data. */
export async function haloWalk(session: HaloSession, ref: string): Promise<WalkResult> {
  return session.walk(ref);
}

/** Fetch several leaf refs at once, verified, with a per-ref ok/error result. */
export async function haloFetch(
  session: HaloSession,
  refs: string[],
): Promise<Record<string, FetchResult>> {
  return session.fetch(refs);
}

function ok(value: unknown): CallToolResult {
  return { content: [{ type: "text", text: JSON.stringify(value) }] };
}

function fail(message: string): CallToolResult {
  return { content: [{ type: "text", text: message }], isError: true };
}

const WALK_DESC =
  "Expand a halo branch to its summary and child refs, without pulling any leaf data. " +
  "Pass a ref like `m1.income` (or a raw `h:` handle). Use this to see a large branch's " +
  "sub-structure before fetching deeper.";

const FETCH_DESC =
  "Fetch one or more halo leaves by ref, verified on read. Pass ALL the refs a step needs in one " +
  "call (refs is an array) rather than one at a time — each call is a separate round trip. Returns " +
  "a per-ref result; an entry with ok:false (e.g. HashMismatch) means that data must not be trusted.";

/** Build the in-process MCP server exposing halo_walk and halo_fetch over the given session. */
export function createNavServer(session: HaloSession) {
  return createSdkMcpServer({
    name: HALO_MCP_SERVER,
    tools: [
      tool(
        HALO_WALK_TOOL,
        WALK_DESC,
        { ref: z.string().describe("A halo ref: `mapId.branch[.child]` or a raw `h:` handle.") },
        async ({ ref }) => {
          try {
            return ok(await haloWalk(session, ref));
          } catch (e) {
            return fail(`halo_walk failed for "${ref}": ${errorName(e)}`);
          }
        },
      ),
      tool(
        HALO_FETCH_TOOL,
        FETCH_DESC,
        { refs: z.array(z.string()).describe("The halo refs to fetch together in one call.") },
        async ({ refs }) => ok(await haloFetch(session, refs)),
      ),
    ],
  });
}

function errorName(e: unknown): string {
  if (e instanceof Error) return e.name === "Error" ? e.message : e.name;
  return String(e);
}
