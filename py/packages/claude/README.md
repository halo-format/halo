# halo-format-claude

Halo host adapter for the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
(Python). `install_halo()` wires it in one call:

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
is the navigation guidance. Pass `store=FileStore(dir)` for the heavy/persistent deployment. The
core engine is [`halo-format`](https://pypi.org/project/halo-format/); this package is only the shim.
