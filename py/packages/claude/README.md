# halo-format-claude

Halo adapter for Claude on **two runtimes** (Python): the
[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) and the **raw Claude
Messages API**. Same engine — encode a large tool result, hand the model a shape map, let it pull back
only the leaves it needs, verified on read — bound to whichever loop you run.

## Agent SDK — `install_halo()`

`install_halo()` wires the adapter in one call (install the Agent SDK extra:
`pip install halo-format-claude[agent-sdk]`):

- a **PostToolUse encode hook** that replaces a large tool result with a halo **shape map** (root
  kind + one line per field: ref, kind, and a bounded preview), so the payload stays out of the
  model's context while it still sees what's there;
- a single in-process **`halo_fetch`** MCP tool the model uses to pull back only the leaves it needs,
  verified on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API
  both pulls and expands (there is no separate `halo_walk`).

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from halo_format_claude import install_halo

result = install_halo(ClaudeAgentOptions(...))
# pass result.options to query(); result.session holds the shared store for audit/inspection
```

The encode hook is deterministic plumbing (it always fires, even for built-in tools); the Halo Skill
is the navigation guidance. Pass `store=FileStore(dir)` for the heavy/persistent deployment.

## Raw Messages API — `halo_format_claude.raw`

No hook exists on the raw API — you own the tool-use loop on `messages.create(...)`. `create_raw_halo()`
gives you the same mechanism to drive by hand. This submodule imports **zero Agent SDK code** (the
package imports the SDK lazily), so `pip install halo-format-claude` without the `agent-sdk` extra is
enough for the raw path. This is the runtime where Halo's token win is largest: the raw API re-sends
every tool result in context each turn, so keeping a heavy payload out of context is a real, growing
saving.

```python
import json
from anthropic import Anthropic
from halo_format_claude.raw import create_raw_halo

halo = create_raw_halo(threshold=2048)
tools = [*domain_tools, halo.tool_def]          # add the halo_fetch tool
system = SYSTEM_PROMPT + halo.guidance          # add the navigation guidance

# inside your loop, per tool_use block:
async def run_tool(name, args):
    if halo.is_fetch(name):
        return halo.fetch(args["refs"])          # verified leaves; never re-encode
    result = await dispatch[name](**args)
    return halo.encode_result(name, args, result)  # shape map if large, else passthrough
```

`encode_result` size-gates (shape map above the threshold, raw JSON below); `fetch` returns the
verified per-ref results as a JSON string for the `tool_result` content. The core engine is
[`halo-format`](https://pypi.org/project/halo-format/); this package is only the shim that binds it to
the two Claude runtimes.
