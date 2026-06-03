// summarize: (value, branches) -> string, deterministic.
//
// The summary is inside the hashed node, so it MUST be a pure function of the data (counts,
// key names, value ranges, fixed template) — never LLM-generated prose, which would break
// content-addressing. Default deriveSummary uses only structural facts.

export {};
