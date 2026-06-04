# @halo-format/claude

Halo host adapter for the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-typescript)
(TypeScript). `installHalo()` wires it in one call:

- a **PostToolUse encode hook** that replaces a large tool result with a halo **shape map** (root
  kind + one line per field: ref, kind, and a bounded preview), so the payload stays out of the
  model's context while it still sees what's there;
- a single in-process **`halo_fetch`** MCP tool the model uses to pull back only the leaves it needs,
  verified on read — a ref that lands on a branch returns that branch's sub-refs, so one batch API
  both pulls and expands (there is no separate `halo_walk`).

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";
import { installHalo } from "@halo-format/claude";

const { options, session } = installHalo(baseOptions, { threshold: 2048 });
// remember to allow the nav tool: allowedTools: [..., "mcp__halo__halo_fetch"]

for await (const message of query({ prompt, options })) {
  // ...
}
// `session` holds the shared store + map registry, for the audit/persistence swaps or inspection
```

The encode hook is deterministic plumbing (it always fires, even for built-in tools); a Halo
navigation **Skill** is the guidance that shapes how the model reads the map. Pass
`store: new FileStore(dir)` for the heavy / persistent deployment. The core engine is
[`@halo-format/halo`](../halo); this package is only the shim that binds it to the Claude Agent SDK.

See the repo root for the full integration walkthrough and two runnable example agents.
