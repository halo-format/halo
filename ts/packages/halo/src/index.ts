// Public surface of @halo-format/halo.
//
// Producer:  encode, extend, merge
// Consumer:  open -> Navigator{ walk, fetch, fetchMany, root }; free walk/fetch/fetchMany
// Stores:    MemoryStore, FileStore
// Types:     Handle, Node, HaloEnvelope, Store, CarvePolicy, EncodeOptions
// Errors:    UnknownHandle, HashMismatch, WrongKind, CanonicalizationError, StoreError
//
// Re-exports only; implementation lives in the sibling modules.

export type { JsonValue, Handle, Alg } from "./types.js";
export {
  HaloError,
  UnknownHandle,
  HashMismatch,
  WrongKind,
  CanonicalizationError,
  StoreError,
} from "./errors.js";
export { canonical, canonicalBytes } from "./canonical.js";
export { hashBytes, handleOf } from "./hash.js";
export type { BranchNode, LeafNode, Node } from "./node.js";
export {
  isBranch,
  isLeaf,
  branchNode,
  leafNode,
  serialize,
  nodeHandle,
  decode,
} from "./node.js";
export type { Store } from "./store.js";
export { MemoryStore, FileStore } from "./store.js";
export type { CarvePolicy, CarveDecision, AutoCarveOptions } from "./carve.js";
export { autoCarve, makeAutoCarve } from "./carve.js";
export type { Summarizer } from "./summarize.js";
export { deriveSummary } from "./summarize.js";
export type { HaloEnvelope } from "./envelope.js";
export { buildEnvelope, verifyEnvelope } from "./envelope.js";
export type { EncodeOptions, EncodeResult } from "./encode.js";
export { encode, extend, merge } from "./encode.js";
export type { WalkResult, FetchResult } from "./navigate.js";
export { open, walk, fetch, fetchMany, Navigator } from "./navigate.js";
