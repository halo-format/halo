---
"@halo-format/langgraph": minor
---

New host adapter `@halo-format/langgraph` for LangChain agents and LangGraph graphs. `installHalo()`
adds a `wrapToolCall` encode middleware (large tool results become a shape map, out of context, with
the full envelope carried in the `ToolMessage` artifact) and a single `halo_fetch` navigation tool for
verified, batched drill-down. Ships at parity with the Python `halo-format-langgraph` package.
