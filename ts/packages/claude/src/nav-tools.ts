// The navigation surface — how the model pulls back what the hook withheld. An in-process MCP server
// exposing exactly ONE tool, halo_fetch, backed by the session store and verified on read.
//
// One tool on purpose: an earlier version also exposed halo_walk (expand a branch) alongside
// halo_fetch (pull leaves), and the model wasted turns choosing between them and fetching a branch
// ref through the leaf tool. halo_fetch now does both — a leaf ref returns its value, a branch ref
// returns its sub-shape — so there is a single batch API and nothing to disambiguate.
//
// halo_fetch takes an ARRAY of refs: each fetch is a separate model round trip, the dominant latency
// in the loop, so the model is nudged to gather every ref a step needs and pull them in one call. It
// returns a per-ref result, so one unknown or tampered entry (surfaced as a HashMismatch) never
// sinks the batch.
//
// The pure handler (haloFetch) is split out from the MCP wrapping so it can be tested without the SDK
// runtime, and so the SDK tool() call is the only SDK-coupled line.

import { z } from "zod";
import { tool, createSdkMcpServer } from "@anthropic-ai/claude-agent-sdk";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { HaloSession, FetchEntry } from "./session.js";
import { HALO_MCP_SERVER, HALO_FETCH_TOOL } from "./constants.js";

/** Fetch several refs at once, verified, with a per-ref result; branch refs return their sub-shape. */
export async function haloFetch(
  session: HaloSession,
  refs: string[],
): Promise<Record<string, FetchEntry>> {
  return session.fetch(refs);
}

function ok(value: unknown): CallToolResult {
  return { content: [{ type: "text", text: JSON.stringify(value) }] };
}

const FETCH_DESC =
  "The one tool for reading a halo map. Pass ALL the refs a step needs in one call (refs is an " +
  "array) rather than one at a time — each call is a separate round trip. A ref like `m1.income` " +
  "(or a raw `h:` handle) that points at a value returns it as `{ok:true,value}`; a ref that points " +
  "at a [branch] returns `{ok:true,kind:'branch',fields:[…]}` listing its sub-refs to fetch next. " +
  "An entry with `ok:false` (e.g. HashMismatch) means that data must not be trusted.";

/** Build the in-process MCP server exposing the single halo_fetch tool over the given session. */
export function createNavServer(session: HaloSession) {
  return createSdkMcpServer({
    name: HALO_MCP_SERVER,
    tools: [
      tool(
        HALO_FETCH_TOOL,
        FETCH_DESC,
        { refs: z.array(z.string()).describe("The halo refs to fetch together in one call.") },
        async ({ refs }) => ok(await haloFetch(session, refs)),
      ),
    ],
  });
}
