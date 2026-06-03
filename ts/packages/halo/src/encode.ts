// encode: bottom-up Merkle build, plus extend / merge.
//
// buildNode recurses children-first so a parent references its children by handle, which gives the
// tree its Merkle structure and free dedup (store.put is idempotent and content-keyed). encode
// returns { handle, envelope }. extend(root, name, value) folds a new branch onto an existing root
// (last write wins on name collision); merge(roots[]) combines several roots' branch tables. Both
// reuse every unchanged child handle, so the only new node is the root, and because nodes are
// immutable the prior root stays in the store — version history and a change audit for free.

import type { Alg, Handle, JsonValue } from "./types.js";
import type { Store } from "./store.js";
import { autoCarve, type CarvePolicy } from "./carve.js";
import { deriveSummary, type Summarizer } from "./summarize.js";
import { branchNode, leafNode, serialize, decode, isBranch, type Node, type BranchNode } from "./node.js";
import { buildEnvelope, type HaloEnvelope } from "./envelope.js";
import { WrongKind } from "./errors.js";

export type EncodeOptions = {
  store: Store;
  carve?: CarvePolicy;
  summarize?: Summarizer;
  alg?: Alg;
};

export type EncodeResult = { handle: Handle; envelope: HaloEnvelope };

type Resolved = { store: Store; carve: CarvePolicy; summarize: Summarizer; alg: Alg };

function resolve(opts: EncodeOptions): Resolved {
  return {
    store: opts.store,
    carve: opts.carve ?? autoCarve,
    summarize: opts.summarize ?? deriveSummary,
    alg: opts.alg ?? "sha256",
  };
}

// Build one node and everything beneath it, returning the node's handle. Children are built first
// so the parent branch can reference them by handle (the Merkle property).
async function buildNode(
  value: JsonValue,
  path: string[],
  r: Resolved,
): Promise<Handle> {
  const decision = r.carve(value, path);
  let node: Node;
  if (decision.as === "leaf") {
    node = leafNode(value);
  } else {
    const branches: Record<string, Handle> = {};
    for (const [name, child] of Object.entries(decision.children)) {
      branches[name] = await buildNode(child, [...path, name], r);
    }
    node = branchNode(decision.summary ?? r.summarize(value, branches), branches);
  }
  return r.store.put(serialize(node));
}

// Build the result from an already-stored root handle: read the root node back and wrap it.
async function resultFor(root: Handle, r: Resolved): Promise<EncodeResult> {
  const rootNode = decode(await r.store.get(root));
  return { handle: root, envelope: buildEnvelope(root, rootNode, r.alg) };
}

/** Encode a JSON value into content-addressed nodes and return its halo. */
export async function encode(value: JsonValue, opts: EncodeOptions): Promise<EncodeResult> {
  const r = resolve(opts);
  const root = await buildNode(value, [], r);
  return resultFor(root, r);
}

async function readBranch(root: Handle, store: Store): Promise<BranchNode> {
  const node = decode(await store.get(root));
  if (!isBranch(node)) throw new WrongKind("extend/merge expect a branch root");
  return node;
}

/** Fold `value` onto `root` as a new branch named `name` (last write wins on collision). */
export async function extend(
  root: Handle,
  name: string,
  value: JsonValue,
  opts: EncodeOptions,
): Promise<EncodeResult> {
  const r = resolve(opts);
  const base = await readBranch(root, r.store);
  const childHandle = await buildNode(value, [name], r);
  const branches = { ...base.branches, [name]: childHandle };
  const newRoot = await r.store.put(serialize(branchNode(r.summarize(value, branches), branches)));
  return resultFor(newRoot, r);
}

/** Combine several roots' branch tables into one new root (last write wins, in order). */
export async function merge(roots: Handle[], opts: EncodeOptions): Promise<EncodeResult> {
  const r = resolve(opts);
  let branches: Record<string, Handle> = {};
  for (const root of roots) {
    const node = await readBranch(root, r.store);
    branches = { ...branches, ...node.branches };
  }
  const newRoot = await r.store.put(serialize(branchNode(r.summarize(null, branches), branches)));
  return resultFor(newRoot, r);
}
