# @halo-format/langgraph

Halo host adapter for [LangChain](https://github.com/langchain-ai/langchainjs) agents and
[LangGraph](https://github.com/langchain-ai/langgraphjs). `installHalo()` wires it in one call:

- a **`wrapToolCall` encode middleware** — the deterministic wrap-the-tool-call hook, LangChain's
  analog of the Claude SDK's PostToolUse — that replaces a large tool result with a halo **shape map**
  (root kind + one line per field: ref, kind, and a bounded preview), so the payload stays out of the
  model's context while it still sees what's there. The full envelope rides in the `ToolMessage`
  **`artifact`** (kept in graph state, never sent to the model) for audit/replay;
- a single plain LangChain **`halo_fetch`** tool the model uses to pull back only the leaves it needs,
  verified on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API both
  pulls and expands (there is no separate `halo_walk`).

```ts
import { createAgent } from "langchain";
import { installHalo } from "@halo-format/langgraph";

const { tools, middleware, session } = installHalo({ tools: myTools });
const agent = createAgent({ model, tools, middleware });
// session holds the shared store for audit/inspection
```

The middleware is deterministic plumbing (it always fires, for every tool); the Halo Skill (or
prompt-mode guidance) is the navigation behavior. Pass `store: new FileStore(dir)` for the
heavy/persistent deployment. The core engine is
[`@halo-format/halo`](https://www.npmjs.com/package/@halo-format/halo); this package is only the shim.

> **JS vs. Python note.** The JS `ToolNode` does not accept a wrap option, so on this host the
> middleware is the only clean interception surface — there is no `haloToolNode()` the way there is in
> the Python adapter.
