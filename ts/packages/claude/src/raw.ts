// @halo-format/claude/raw — the Halo adapter for the RAW Claude Messages API.
//
// The Agent SDK adapter (installHalo, the package root) leans on a PostToolUse hook to encode every
// tool result before the model sees it. The raw Messages API has no hook: you own the tool-use loop
// on `anthropic.messages.create(...)`. This module gives you the same mechanism to drive by hand —
// encode a large result into the session store, hand the model a shape map, and expose a halo_fetch
// tool to pull back the verified leaves.
//
// This is the runtime where Halo's token win is largest: the raw API re-sends every tool result in
// context on each turn (no host scratch-spill) and the cached prefix is small, so keeping a heavy
// payload out of context is bytes the baseline would otherwise resend every turn.
//
// This entrypoint imports ZERO Agent SDK code — only the SDK-free core of the adapter (HaloSession,
// the serializer, the accumulation policy). So a raw-Messages-API app can depend on
// @halo-format/claude without installing @anthropic-ai/claude-agent-sdk.

import type { JsonValue } from "@halo-format/halo";
import { HaloSession, type SessionOptions } from "./session.js";
import { sizeOf, serializeEnvelope } from "./serialize.js";
import { HALO_FETCH_TOOL, HALO_FETCH_DESCRIPTION } from "./constants.js";

const DEFAULT_THRESHOLD = 2048;

/** The halo_fetch tool definition in raw Messages API shape — spread into your `tools` array. */
export type HaloFetchToolDef = {
  name: string;
  description: string;
  input_schema: {
    type: "object";
    properties: { refs: { type: "array"; items: { type: "string" }; description: string } };
    required: ["refs"];
  };
};

/** Build the halo_fetch tool definition for the Messages API (the Agent SDK builds it from a zod schema). */
export function haloFetchToolDef(): HaloFetchToolDef {
  return {
    name: HALO_FETCH_TOOL,
    description: HALO_FETCH_DESCRIPTION,
    input_schema: {
      type: "object",
      properties: {
        refs: {
          type: "array",
          items: { type: "string" },
          description: "The halo refs to fetch together in one call.",
        },
      },
      required: ["refs"],
    },
  };
}

/**
 * Navigation guidance to append to your system prompt. The hook-based adapter delivers this via a
 * Skill; on the raw API you put it in the prompt yourself. It is intentionally generic — append a
 * one-line domain hint (e.g. "fetch the line items, not the attachment bodies") if it helps.
 */
export const HALO_GUIDANCE = `
## Halo: navigating large tool results

Some tool results come back not as the full payload but as a *halo shape map* — a \`[halo] map "<id>"\`
note with one line per field giving its ref, kind, and a bounded preview; the full data is held,
verified, in a store outside your context. Read the previews first and answer from them when you can.
For anything a preview does not settle, fetch ONLY the fields you still need in a SINGLE halo_fetch
call, passing every ref as a list (e.g. ["m1.lines", "m1.total"]). A [branch] ref expands to its
sub-refs; every other ref returns its value. Each value is verified on read — an entry with ok=false
(e.g. HashMismatch) must not be trusted. Use fetched values as if returned inline; never fetch fields
you do not need.`;

export type RawHaloOptions = SessionOptions & {
  /** Below this many bytes a tool result is returned unchanged (no encode). Default 2048. */
  threshold?: number;
  /** A pre-built session to share state with, instead of creating one. */
  session?: HaloSession;
};

/** The raw Messages API adapter: a session plus the helpers a manual tool-use loop needs. */
export type RawHalo = {
  /** The shared session (store + map registry), for audit swaps or direct inspection. */
  session: HaloSession;
  /** The halo_fetch tool definition to add to your `tools` array. */
  toolDef: HaloFetchToolDef;
  /** Navigation guidance to append to your system prompt. */
  guidance: string;
  /** True if a tool-use block names the halo_fetch tool (so route it to `fetch`, never re-encode it). */
  isFetch(toolName: string): boolean;
  /** Answer a halo_fetch tool call: verified per-ref results as the JSON string for tool_result content. */
  fetch(refs: string[]): Promise<string>;
  /**
   * Process a domain tool's result for the model. Above the size threshold it is encoded into the
   * store and a shape map string is returned in its place; below it the raw JSON payload passes
   * through. Either way the return value is the string to put in the tool_result content.
   */
  encodeResult(toolName: string, toolInput: unknown, value: JsonValue): Promise<string>;
};

/**
 * Wire the Halo raw-Messages-API adapter. Returns a bundle whose three pieces map onto the manual
 * loop: add `toolDef` to your tools and `guidance` to your system prompt, then in your dispatch route
 * a `halo_fetch` call (see `isFetch`) to `fetch(refs)` and every other tool result to
 * `encodeResult(name, input, value)`.
 */
export function createRawHalo(opts: RawHaloOptions = {}): RawHalo {
  const { threshold = DEFAULT_THRESHOLD, session: provided, ...sessionOpts } = opts;
  const session = provided ?? new HaloSession(sessionOpts);

  return {
    session,
    toolDef: haloFetchToolDef(),
    guidance: HALO_GUIDANCE,
    isFetch: (toolName: string) => toolName === HALO_FETCH_TOOL,
    async fetch(refs: string[]): Promise<string> {
      // MANDATORY: this is the only place a fetched leaf is returned — never re-encode it, or the
      // model would receive another map instead of the value.
      return JSON.stringify(await session.fetch(refs));
    },
    async encodeResult(toolName: string, toolInput: unknown, value: JsonValue): Promise<string> {
      if (sizeOf(value) < threshold) return JSON.stringify(value);
      const { envelope } = await session.ingest(toolName, toolInput, value);
      const hints = await session.describe(envelope);
      return serializeEnvelope(envelope, hints);
    },
  };
}

export { HaloSession } from "./session.js";
export type { SessionOptions, IngestResult, FetchEntry } from "./session.js";
export { argJoin } from "./accumulate.js";
export type { KeyOf } from "./accumulate.js";
export { sizeOf, parseToolOutput, serializeEnvelope, shapeOf, previewOf } from "./serialize.js";
export type { FieldHint } from "./serialize.js";
export { HALO_FETCH_TOOL, HALO_FETCH_DESCRIPTION } from "./constants.js";
