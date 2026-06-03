"""summarize(value, branches) -> str, deterministic.

The summary is inside the hashed node, so it must be a pure function of the data (counts, ranges,
fixed template) — never LLM-generated prose, which would break content-addressing. Default
derive_summary uses only structural facts.
"""
