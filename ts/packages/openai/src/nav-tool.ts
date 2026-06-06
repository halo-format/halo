// The navigation surface — how the model pulls back what the model wrapper withheld. A single OpenAI
// Agents SDK function tool, halo_fetch, backed by the session store and verified on read. No MCP server:
// it is an ordinary tool, appended to the agent's tools list and bound to the model like any other.
//
// One tool on purpose: an earlier design (in the Claude adapter's history) also exposed halo_walk and
// the model wasted turns choosing between them and fetching a branch ref through the leaf tool.
// halo_fetch now does both — a leaf ref returns its value, a branch ref returns its sub-shape — so there
// is a single batch API and nothing to disambiguate.
//
// halo_fetch takes an ARRAY of refs: each fetch is a separate model round trip, the dominant latency in
// the loop, so the model is nudged to gather every ref a step needs and pull them in one call. It
// returns a per-ref result (JSON), so one unknown or tampered entry (a HashMismatch) never sinks the batch.
//
// The parameters are declared as a plain JSON schema (not zod), so this adapter pulls in no schema
// library and avoids the OpenAI SDK's zod-version peer entirely. The pure handler (haloFetch) is split
// from the tool wrapping so it can be tested without the SDK runtime.

import { tool } from "@openai/agents";
import type { HaloSession, FetchEntry } from "./session.js";
import { HALO_FETCH_TOOL } from "./constants.js";

/** Fetch several refs at once, verified, with a per-ref result; branch refs return their sub-shape. */
export async function haloFetch(
  session: HaloSession,
  refs: string[],
): Promise<Record<string, FetchEntry>> {
  return session.fetch(refs);
}

const FETCH_DESC =
  "The one tool for reading a halo map. Pass ALL the refs a step needs in one call (refs is an " +
  "array) rather than one at a time — each call is a separate round trip. A ref like `m1.income` " +
  "(or a raw `h:` handle) that points at a value returns it as `{ok:true,value}`; a ref that points " +
  "at a [branch] returns `{ok:true,kind:'branch',fields:[…]}` listing its sub-refs to fetch next. " +
  "An entry with `ok:false` (e.g. HashMismatch) means that data must not be trusted.";

// A plain JSON object schema for { refs: string[] }. strict mode (the SDK default) requires every
// property listed in `required` and additionalProperties:false — both satisfied here. Literal kinds are
// pinned with `as const`, but `required` stays a mutable string[] (the SDK's schema type wants mutable).
const FETCH_PARAMS = {
  type: "object" as const,
  properties: {
    refs: {
      type: "array" as const,
      items: { type: "string" as const },
      description: "The halo refs to fetch together in one call.",
    },
  },
  required: ["refs"] as string[],
  additionalProperties: false as const,
};

/** Build the single halo_fetch function tool over the given session. */
export function createHaloFetchTool(session: HaloSession) {
  return tool({
    name: HALO_FETCH_TOOL,
    description: FETCH_DESC,
    parameters: FETCH_PARAMS,
    execute: async (input: unknown): Promise<string> => {
      const refs = (input as { refs?: unknown }).refs;
      const list = Array.isArray(refs) ? (refs.filter((r) => typeof r === "string") as string[]) : [];
      return JSON.stringify(await haloFetch(session, list));
    },
  });
}
