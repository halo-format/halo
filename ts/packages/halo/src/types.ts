// Shared primitive types for the core. The node model (BranchNode/LeafNode) lives in node.ts;
// this module holds the value, handle, and algorithm types the leaf modules depend on.

export type JsonValue =
  | null
  | boolean
  | number
  | string
  | JsonValue[]
  | { [key: string]: JsonValue };

// A handle is "h:" + lowercase 64-hex sha256 digest of the canonical node bytes.
export type Handle = string;

// Hash algorithm identifier, declared per-tree in the envelope's `alg`. Default sha256.
export type Alg = "sha256";
