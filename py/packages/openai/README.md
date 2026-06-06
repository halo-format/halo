# halo-format-openai

Halo host adapter for the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) (Python).
`install_halo()` wires it in one call:

- a **`call_model_input_filter`** — the interception seam on this host. The OpenAI Agents SDK has no
  tool-return output-replacement hook (`on_tool_end` is observational), so this filter, which rewrites
  the assembled model input before each model call, is the only **generic** point that catches *every*
  tool — including external/MCP/hosted tools your app does not own. Above a size threshold it replaces a
  large tool result with a halo **shape map** (root kind + one line per field: ref, kind, and a bounded
  preview), so the payload stays out of the model's context while it still sees what's there;
- a single **`halo_fetch`** function tool the model uses to pull back only the leaves it needs, verified
  on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API both pulls and
  expands (there is no separate `halo_walk`).

```python
from agents import Agent, Runner, RunConfig
from halo_format_openai import install_halo

result = install_halo(tools=my_tools)
agent = Agent(name="assistant", tools=result.tools)
out = await Runner.run(
    agent, "…",
    run_config=RunConfig(call_model_input_filter=result.call_model_input_filter),
)
# result.session holds the shared store for audit/inspection
```

Because the filter fires before every model call over the whole input list (not once per tool return),
the adapter correlates each `function_call_output` to its `function_call` by `call_id` — both to skip
`halo_fetch`'s own output (the mandatory no-re-encode rule) and to feed entity accumulation the real
tool name/args — and caches each encoded result by `call_id` so repeated firings stay idempotent. The
filter is deterministic plumbing (it always runs, for every tool); the Halo Skill (or prompt-mode
guidance) is the navigation behavior. Pass `store=FileStore(dir)` for the heavy/persistent deployment.
The core engine is [`halo-format`](https://pypi.org/project/halo-format/); this package is only the shim.
