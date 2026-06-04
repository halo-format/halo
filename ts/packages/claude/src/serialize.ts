// Serialization at the SDK boundary: measure a raw tool result, parse it into a JSON value the
// core can encode, and serialize a halo envelope back into the string the model sees.
//
// updatedToolOutput carries the tool's visible output. What the model sees in place of the blob is a
// SHAPE MAP, not the raw envelope: the root kind stated up front, then one line per field giving its
// ref, its kind (leaf vs [branch]), and a bounded preview. This is deliberately not the hashed
// envelope JSON — the 64-char branch handles are dead weight to the model (it navigates by
// `<mapId>.<field>` refs, which the session's navigator resolves from its own registry), and showing
// only names without kinds is exactly what made the model guess the root kind and fetch a branch as
// if it were a leaf. The hints close both gaps. The envelope object itself is unchanged and still
// held verbatim in the session for verified reads.

import type { HaloEnvelope, JsonValue } from "@halo-format/halo";

// A per-field descriptor the model sees in the shape map. `shape` is a short structural tag
// ("number", `string[42]`, `object{4}`, `[branch] object{7}`); `preview` is a bounded sample of a
// leaf's value, or the child-ref names of a branch. Built by HaloSession.describe (it needs the
// store to read each child node); rendered here.
export type FieldHint = { ref: string; kind: "leaf" | "branch"; shape: string; preview?: string };

const PREVIEW_MAX = 80;

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
    // The MCP result may arrive as `{ content: [{type:text,text}] }` OR as the bare content-block
    // array `[{type:text,text}]` (the shape some SDK hosts hand the hook). Unwrap either.
    const text = extractContentText(raw);
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

// Unwrap the MCP content-block shape to its text, concatenating multiple text blocks. Accepts both
// the `{ content: [...] }` object and a bare `[{type:text,text}]` array. Returns undefined when the
// value is not content blocks (a genuine array/object result), so it is encoded as-is.
function extractContentText(value: unknown): string | undefined {
  const content = Array.isArray(value)
    ? value
    : value && typeof value === "object" && Array.isArray((value as { content?: unknown }).content)
      ? ((value as { content: unknown[] }).content)
      : null;
  if (!content) return undefined;
  const texts: string[] = [];
  for (const block of content) {
    if (block && typeof block === "object" && (block as { type?: unknown }).type === "text") {
      const t = (block as { text?: unknown }).text;
      if (typeof t === "string") texts.push(t);
    }
  }
  return texts.length > 0 ? texts.join("") : undefined;
}

/** A short structural tag for a leaf value: its kind plus a size for strings/arrays/objects. */
export function shapeOf(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return "boolean";
  if (typeof value === "number") return "number";
  if (typeof value === "string") return `string[${value.length}]`;
  if (Array.isArray(value)) return `array[${value.length}]`;
  return `object{${Object.keys(value).length}}`;
}

/** A bounded, single-line JSON sample of a value — enough to recognise it, never the whole payload. */
export function previewOf(value: JsonValue, max: number = PREVIEW_MAX): string {
  let s: string | undefined;
  try {
    s = JSON.stringify(value);
  } catch {
    return "";
  }
  if (s === undefined) return "";
  return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

// Render one field line: ref, structural tag, then the preview/child-names. A leaf primitive reads
// "ref  number = 1843"; an object leaf "ref  object{4}  {…}"; a branch "ref  [branch] object{7}  ↳ a, b".
function hintLine(h: FieldHint): string {
  const tail = h.preview ? `  ${h.kind === "leaf" && isScalarShape(h.shape) ? "= " : ""}${h.preview}` : "";
  return `  ${h.ref}  ${h.shape}${tail}`;
}

function isScalarShape(shape: string): boolean {
  return shape === "null" || shape === "boolean" || shape === "number";
}

// "object, 7 fields" / "array, 4 chunks" for a branch root; for a leaf root reuse the view summary.
function rootShape(names: string[]): string {
  const n = names.length;
  const arrayLike = n > 0 && names.every((name) => /^\d+$/.test(name));
  return arrayLike ? `array, ${n} chunks` : `object, ${n} field${n === 1 ? "" : "s"}`;
}

function shortTool(tool: string): string {
  if (tool.startsWith("mcp__")) {
    const parts = tool.split("__");
    if (parts.length >= 3) return parts.slice(2).join("__");
  }
  return tool;
}

/**
 * Serialize an envelope into the string the model receives in place of the blob: the map id and root
 * kind stated up front, then (when `hints` are supplied) one line per field with its kind and a
 * bounded preview. With no hints it degrades to a bare ref list — still no hashes, still names the
 * root kind, just without the per-field previews the session computes from the store.
 */
export function serializeEnvelope(envelope: HaloEnvelope, hints?: FieldHint[]): string {
  const id = envelope.source?.id ?? "?";
  const names = Object.keys(envelope.view.branches);
  const isLeafRoot = names.length === 0;
  const root = isLeafRoot ? envelope.view.summary.replace(/^leaf:\s*/, "") : rootShape(names);
  const from = envelope.source?.tool ? ` from ${shortTool(envelope.source.tool)}` : "";

  const head =
    `[halo] map "${id}" — ${root}${from}, stored out of context. ` +
    `Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; ` +
    `each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ` +
    `ref returns its value.`;

  if (isLeafRoot) return `${head}\nFetch "${id}" itself to read the value.`;

  const lines =
    hints && hints.length ? hints.map(hintLine) : names.map((n) => `  ${id}.${n}`);
  return `${head}\nFields:\n${lines.join("\n")}`;
}
