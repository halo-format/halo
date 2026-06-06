# @halo-format/langgraph

## 0.3.1

### Patch Changes

- 793e48a: Align the `zod` dependency to `^4.0.0` (was `^3.25.0`), matching `@halo-format/claude` and
  the LangChain v1 ecosystem. The navigation tool's schema is built with zod, so it should
  track the same major as the host.
  - @halo-format/halo@0.3.1

## 0.3.0

### Minor Changes

- 0e4e0fd: New host adapter `@halo-format/langgraph` for LangChain agents and LangGraph graphs. `installHalo()`
  adds a `wrapToolCall` encode middleware (large tool results become a shape map, out of context, with
  the full envelope carried in the `ToolMessage` artifact) and a single `halo_fetch` navigation tool for
  verified, batched drill-down. Ships at parity with the Python `halo-format-langgraph` package.

### Patch Changes

- @halo-format/halo@0.3.0
