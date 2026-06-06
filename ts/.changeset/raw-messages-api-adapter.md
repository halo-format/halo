---
"@halo-format/claude": minor
---

Add a raw Claude Messages API adapter alongside the Agent SDK one.

`@halo-format/claude/raw` exposes `createRawHalo(opts?)`, a bundle for a hand-built
tool-use loop on `anthropic.messages.create(...)`: `toolDef` (the `halo_fetch` tool
in Messages API shape), `guidance` (system-prompt navigation text), `isFetch(name)`,
`fetch(refs)`, and `encodeResult(tool, args, value)` (size-gated encode → shape map,
or passthrough). This is the runtime where Halo's token win is largest — the raw API
re-sends every tool result in context each turn, so keeping a heavy payload out of
context is a real, growing saving.

The new entrypoint imports zero Agent SDK code, and `@anthropic-ai/claude-agent-sdk`
is now an optional peer dependency, so a raw-Messages-API app can use
`@halo-format/claude/raw` without installing the Agent SDK. The `halo_fetch`
description is shared between the hook tool and the raw tool def so they cannot drift.
