# @halo-format/openai

## 0.4.0

### Minor Changes

- 033c1b2: Add the OpenAI Agents SDK adapter (`@halo-format/openai` on npm, `halo-format-openai` on PyPI).

  It swaps large tool results for a halo shape map before the model sees them — keeping the payload out of context — and exposes a single `halo_fetch(refs[])` navigation tool to pull back only the leaves the model needs, verified on read. `installHalo()` / `install_halo()` wires it in one call.

  Host note: the OpenAI Agents SDK has no tool-return output-replacement hook. The Python port uses `RunConfig.call_model_input_filter` (the generic seam that catches every tool, including external/MCP ones). The released JS SDK has no such hook, so the TS port intercepts at the equivalent point one layer down — wrapping the `Model` (`wrapModel` / `wrapModelProvider`) to rewrite `request.input` before the model call.

### Patch Changes

- @halo-format/halo@0.4.0
