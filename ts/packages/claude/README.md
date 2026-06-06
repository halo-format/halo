# @halo-format/claude

Halo adapter for Claude on **two runtimes** (TypeScript): the
[Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-typescript) and the **raw Claude
Messages API**. Same engine — encode a large tool result, hand the model a shape map, let it pull back
only the leaves it needs, verified on read — bound to whichever loop you run.

## Agent SDK — `installHalo()`

`installHalo()` wires the adapter in one call:

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
`store: new FileStore(dir)` for the heavy / persistent deployment.

## Raw Messages API — `@halo-format/claude/raw`

No hook exists on the raw API — you own the tool-use loop on `anthropic.messages.create(...)`.
`createRawHalo()` gives you the same mechanism to drive by hand. This entrypoint imports **zero Agent
SDK code**, and `@anthropic-ai/claude-agent-sdk` is an optional peer dependency, so a raw app can use
it without installing the Agent SDK. This is the runtime where Halo's token win is largest: the raw
API re-sends every tool result in context each turn, so keeping a heavy payload out of context is a
real, growing saving.

```ts
import Anthropic from "@anthropic-ai/sdk";
import { createRawHalo } from "@halo-format/claude/raw";

const halo = createRawHalo({ threshold: 2048 });
const tools = [...domainTools, halo.toolDef];          // add the halo_fetch tool
const system = SYSTEM_PROMPT + halo.guidance;          // add the navigation guidance

// inside your loop, per tool_use block:
async function runTool(name: string, args: any) {
  if (halo.isFetch(name)) return halo.fetch(args.refs);       // verified leaves; never re-encode
  const result = await dispatch[name](args);
  return halo.encodeResult(name, args, result);              // shape map if large, else passthrough
}
```

`encodeResult` size-gates: above the threshold it encodes the result into the session store and
returns the shape map string; below it the raw JSON passes through. `fetch` returns the verified
per-ref results as a JSON string for the `tool_result` content.

The core engine is [`@halo-format/halo`](../halo); this package is only the shim that binds it to the
two Claude runtimes. See the repo root for the full integration walkthrough and runnable example
agents (the insurance-claim example runs on both runtimes).
