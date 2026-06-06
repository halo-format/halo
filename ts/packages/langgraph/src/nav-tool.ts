// The navigation surface — how the model pulls back what the middleware withheld. A single plain
// LangChain tool, halo_fetch, backed by the session store and verified on read. No MCP server: it is
// an ordinary tool, appended to the agent's tools list and bound to the model like any other.
//
// One tool on purpose: an earlier design (in the Claude adapter's history) also exposed halo_walk and
// the model wasted turns choosing between them and fetching a branch ref through the leaf tool.
// halo_fetch now does both — a leaf ref returns its value, a branch ref returns its sub-shape — so
// there is a single batch API and nothing to disambiguate.
//
// halo_fetch takes an ARRAY of refs: each fetch is a separate model round trip, the dominant latency
// in the loop, so the model is nudged to gather every ref a step needs and pull them in one call. It
// returns a per-ref result, so one unknown or tampered entry (surfaced as a HashMismatch) never sinks
// the batch.
//
// It is declared `responseFormat: "content_and_artifact"`: the model reads the per-ref values from the
// message content, and the same structured result is attached as the artifact (kept in graph state for
// audit/replay, not re-sent to the model). The pure handler (haloFetch) is split from the tool wrapping
// so it can be tested without the LangChain runtime.

import { z } from "zod";
import { tool } from "@langchain/core/tools";
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

/** Build the single halo_fetch LangChain tool over the given session. */
export function createHaloFetchTool(session: HaloSession) {
  return tool(
    async ({ refs }): Promise<[string, Record<string, FetchEntry>]> => {
      const results = await haloFetch(session, refs);
      // content: the JSON the model reads (the fetched values / branch sub-shapes).
      // artifact: the same structured result, kept in graph state for audit/replay.
      return [JSON.stringify(results), results];
    },
    {
      name: HALO_FETCH_TOOL,
      description: FETCH_DESC,
      schema: z.object({
        refs: z.array(z.string()).describe("The halo refs to fetch together in one call."),
      }),
      responseFormat: "content_and_artifact",
    },
  );
}
