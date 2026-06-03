// carve: (value, path) -> CarveDecision { as: "leaf" } | { as: "branch", children }.
//
// autoCarve default: split a top-level object one branch per key; chunk arrays longer than a
// threshold (default 25); inline small subtrees as leaves. Hosts/skills override with task
// knowledge. Bounds node size so no single node need be the whole payload.

export {};
