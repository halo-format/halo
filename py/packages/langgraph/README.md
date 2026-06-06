# halo-format-langgraph

Halo host adapter for [LangChain](https://github.com/langchain-ai/langchain) agents and
[LangGraph](https://github.com/langchain-ai/langgraph) graphs (Python). `install_halo()` wires it in
one call:

- a **`wrap_tool_call` encode middleware** — the deterministic wrap-the-tool-call hook, LangChain's
  analog of the Claude SDK's PostToolUse — that replaces a large tool result with a halo **shape map**
  (root kind + one line per field: ref, kind, and a bounded preview), so the payload stays out of the
  model's context while it still sees what's there. The full envelope rides in the `ToolMessage`
  **`artifact`** (kept in graph state, never sent to the model) for audit/replay;
- a single plain LangChain **`halo_fetch`** tool the model uses to pull back only the leaves it needs,
  verified on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API both
  pulls and expands (there is no separate `halo_walk`).

```python
from langchain.agents import create_agent
from halo_format_langgraph import install_halo

result = install_halo(tools=my_tools)
agent = create_agent(model, tools=result.tools, middleware=result.middleware)
# result.session holds the shared store for audit/inspection
```

For hand-built `StateGraph`s, use `halo_tool_node(tools=...)` instead — it returns a `ToolNode` with the
same wrapper attached as `wrap_tool_call` / `awrap_tool_call`, plus the tools list (to bind to your
model) and the session.

The middleware is deterministic plumbing (it always fires, for every tool); the Halo Skill (or
prompt-mode guidance) is the navigation behavior. Pass `store=FileStore(dir)` for the heavy/persistent
deployment. The core engine is [`halo-format`](https://pypi.org/project/halo-format/); this package is
only the shim.
