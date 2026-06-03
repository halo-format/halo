// envelope: build the root envelope — the only thing that crosses into the model's context.
//
//   { halo: "1", alg, root, view: { summary, branches }, source? }
//
// view inlines the root node's content so a consumer navigates with zero fetches and can verify by
// re-hashing the reconstructed root against `root`. `source` is envelope-only identification
// metadata (id, tool, args, ts) and is NEVER hashed — it cannot affect handles or dedup.
// (Full envelope verification and `source` population land with the navigator/adapter; this module
// is the builder the encode pipeline returns.)

import type { Alg, Handle, JsonValue } from "./types.js";
import { isBranch, branchNode, nodeHandle, type Node } from "./node.js";

export type HaloEnvelope = {
  halo: "1";
  alg: Alg;
  root: Handle;
  view: { summary: string; branches: Record<string, Handle> };
  source?: {
    id: string; // map id, unique within the session, e.g. "m1"
    tool?: string;
    args?: JsonValue;
    ts?: string;
  };
};

// A leaf root has no branches to inline, so its view summary describes the value's shape instead.
// Deterministic and structural only, so it matches the Python port byte-for-byte.
function leafSummary(value: JsonValue): string {
  if (value === null) return "leaf: null";
  if (typeof value === "boolean") return "leaf: boolean";
  if (typeof value === "number") return "leaf: number";
  if (typeof value === "string") return "leaf: string";
  if (Array.isArray(value)) return `leaf: array of ${value.length} items`;
  return `leaf: object with ${Object.keys(value).length} keys`;
}

/** Build the envelope for an already-stored root node. */
export function buildEnvelope(root: Handle, rootNode: Node, alg: Alg = "sha256"): HaloEnvelope {
  const view = isBranch(rootNode)
    ? { summary: rootNode.summary, branches: { ...rootNode.branches } }
    : { summary: leafSummary(rootNode.value), branches: {} as Record<string, Handle> };
  return { halo: "1", alg, root, view };
}

/**
 * Self-verify an envelope from its inlined view alone (no store): re-hash the reconstructed root
 * branch node and compare to the claimed root. `source` is excluded by construction — it is never
 * part of a node — so two envelopes differing only in `source` verify identically.
 *
 * Only a BRANCH root can be self-verified this way; a leaf root's value is not inlined in the view,
 * so this returns false for leaf roots and the caller must verify against the store (open / fetch).
 */
export function verifyEnvelope(envelope: HaloEnvelope): boolean {
  const reconstructed = branchNode(envelope.view.summary, envelope.view.branches);
  return nodeHandle(reconstructed, envelope.alg) === envelope.root;
}
