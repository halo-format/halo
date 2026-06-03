// node: the node model and its (de)serialization.
//
//   type BranchNode = { k: "b"; summary: string; branches: Record<string, Handle> }
//   type LeafNode   = { k: "l"; value: JsonValue }
//   type Node       = BranchNode | LeafNode
//
// The `k` kind tag is part of the hashed content so a leaf and branch can never collide.
// Stored form is canonical(node) bytes, not the object.

import type { Alg, Handle, JsonValue } from "./types.js";
import { canonicalBytes } from "./canonical.js";
import { hashBytes } from "./hash.js";
import { HaloError } from "./errors.js";

export type BranchNode = { k: "b"; summary: string; branches: Record<string, Handle> };
export type LeafNode = { k: "l"; value: JsonValue };
export type Node = BranchNode | LeafNode;

export function isBranch(node: Node): node is BranchNode {
  return node.k === "b";
}
export function isLeaf(node: Node): node is LeafNode {
  return node.k === "l";
}

/** Build a branch node. A defensive copy keeps the node independent of the caller's map. */
export function branchNode(summary: string, branches: Record<string, Handle>): BranchNode {
  return { k: "b", summary, branches: { ...branches } };
}
export function leafNode(value: JsonValue): LeafNode {
  return { k: "l", value };
}

/** The exact bytes that get hashed and stored for a node: canonical(node). */
export function serialize(node: Node): Uint8Array {
  return canonicalBytes(node as unknown as JsonValue);
}

/** A node's handle: hash over its canonical bytes. The Merkle building block. */
export function nodeHandle(node: Node, alg: Alg = "sha256"): Handle {
  return hashBytes(serialize(node), alg);
}

/**
 * Decode stored bytes back into a validated node. In normal use the bytes were verified against
 * a handle first (navigate verifies on read), so decode of verified bytes always succeeds; the
 * validation here is a guard against malformed input, not a security boundary.
 */
export function decode(bytes: Uint8Array): Node {
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder().decode(bytes));
  } catch (e) {
    throw new HaloError(`node bytes are not valid JSON: ${(e as Error).message}`);
  }
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new HaloError("node must be a JSON object");
  }
  const obj = parsed as Record<string, unknown>;
  if (obj.k === "l") {
    if (!("value" in obj)) throw new HaloError("leaf node missing `value`");
    return { k: "l", value: obj.value as JsonValue };
  }
  if (obj.k === "b") {
    if (typeof obj.summary !== "string") throw new HaloError("branch node `summary` must be a string");
    const branches = obj.branches;
    if (branches === null || typeof branches !== "object" || Array.isArray(branches)) {
      throw new HaloError("branch node `branches` must be an object");
    }
    for (const [name, h] of Object.entries(branches as Record<string, unknown>)) {
      if (typeof h !== "string") throw new HaloError(`branch handle for "${name}" must be a string`);
    }
    return { k: "b", summary: obj.summary, branches: branches as Record<string, Handle> };
  }
  throw new HaloError(`unknown node kind: ${JSON.stringify(obj.k)}`);
}
