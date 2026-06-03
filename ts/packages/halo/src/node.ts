// node: the node model and its (de)serialization.
//
//   type BranchNode = { k: "b"; summary: string; branches: Record<string, Handle> }
//   type LeafNode   = { k: "l"; value: JsonValue }
//   type Node       = BranchNode | LeafNode
//
// The `k` kind tag is part of the hashed content so a leaf and branch can never collide.
// Stored form is canonical(node) bytes, not the object.

export {};
