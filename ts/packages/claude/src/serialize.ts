// Serialization at the SDK boundary: measure a raw tool result, parse it into a JSON value the
// core can encode, and serialize a halo envelope back into the string the model sees.
//
// updatedToolOutput carries the tool's visible output, so the envelope is emitted as a compact JSON
// string prefixed with a one-line note that tells the model this is a navigable map and how to
// address it. The branches in view.branches are reached with refs of the form `<mapId>.<branch>`.

import type { HaloEnvelope, JsonValue } from "@halo-format/halo";

// A tool's raw output as the SDK hands it to a PostToolUse hook: a string, an already-parsed value,
// or the MCP content-block shape `{ content: [{ type: "text", text }] }`.
export type RawToolOutput = unknown;

/** Byte length of a raw tool output, used for the size threshold. Never throws. */
export function sizeOf(raw: RawToolOutput): number {
  if (raw === undefined || raw === null) return 0;
  if (typeof raw === "string") return byteLength(raw);
  try {
    return byteLength(JSON.stringify(raw));
  } catch {
    return 0; // unserializable (e.g. a cycle) — treat as below threshold, pass through
  }
}

function byteLength(s: string): number {
  // Prefer a real byte count; fall back to length if TextEncoder is unavailable.
  if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(s).length;
  return s.length;
}

/**
 * Coerce a raw tool output into a JSON value to encode. Strings are parsed as JSON when possible
 * and otherwise kept as a string leaf; the MCP `{ content: [{ text }] }` block is unwrapped to its
 * concatenated text (parsed when it is itself JSON). Anything already-structured is returned as is.
 * Returns `undefined` when there is nothing meaningful to encode.
 */
export function parseToolOutput(raw: RawToolOutput): JsonValue | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (typeof raw === "string") return parseMaybeJson(raw);
  if (typeof raw === "object") {
    const text = extractContentText(raw as Record<string, unknown>);
    if (text !== undefined) return parseMaybeJson(text);
    return raw as JsonValue;
  }
  return raw as JsonValue; // number | boolean
}

function parseMaybeJson(s: string): JsonValue {
  const trimmed = s.trim();
  if (trimmed === "") return s;
  const first = trimmed[0];
  // Only attempt a parse on something that looks like JSON, so plain prose stays a string leaf.
  if (first === "{" || first === "[" || first === '"') {
    try {
      return JSON.parse(trimmed) as JsonValue;
    } catch {
      return s;
    }
  }
  return s;
}

// Unwrap the MCP CallToolResult content shape to its text, concatenating multiple text blocks.
function extractContentText(obj: Record<string, unknown>): string | undefined {
  const content = obj.content;
  if (!Array.isArray(content)) return undefined;
  const texts: string[] = [];
  for (const block of content) {
    if (block && typeof block === "object" && (block as { type?: unknown }).type === "text") {
      const t = (block as { text?: unknown }).text;
      if (typeof t === "string") texts.push(t);
    }
  }
  return texts.length > 0 ? texts.join("") : undefined;
}

/**
 * Serialize an envelope into the string the model receives in place of the blob: a one-line note
 * naming the map and how to address it, then the compact envelope JSON.
 */
export function serializeEnvelope(envelope: HaloEnvelope): string {
  const id = envelope.source?.id ?? "?";
  const refs = Object.keys(envelope.view.branches)
    .map((b) => `${id}.${b}`)
    .join(", ");
  const note =
    `[halo] Large result stored out of context as map "${id}". ` +
    `Read view.summary, then halo_fetch the refs you need` +
    (refs ? ` (e.g. ${refs})` : "") +
    `; halo_walk a branch to see its sub-structure. Map:`;
  return `${note}\n${JSON.stringify(envelope)}`;
}
