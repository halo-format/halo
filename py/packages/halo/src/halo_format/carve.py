"""carve(value, path) -> {"as": "leaf"} | {"as": "branch", "children": {...}}.

auto_carve default: split a top-level object one branch per key; chunk arrays longer than a
threshold (default 25); inline small subtrees as leaves. Hosts/skills override with task
knowledge. Bounds node size.
"""
