# @halo-format/claude

## 0.3.1

### Patch Changes

- @halo-format/halo@0.3.1

## 0.3.0

### Patch Changes

- @halo-format/halo@0.3.0

## 0.2.0

### Minor Changes

- e8a5a09: Add a raw Claude Messages API adapter alongside the Agent SDK one.

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

### Patch Changes

- @halo-format/halo@0.2.0

## 0.1.1

### Patch Changes

- 77094e7: Split PyPI publishing into two per-package workflows (`publish-python-halo.yml`, `publish-python-claude.yml`) so each PyPI project has its own trusted publisher. They trigger automatically off the Release workflow via `workflow_run`, matching the npm flow. No source changes; the four packages stay on one shared version.
- Updated dependencies [77094e7]
  - @halo-format/halo@0.1.1

## 0.1.0

### Minor Changes

- 27f2bbd: Initial public release of Halo — content-addressed, navigable tool results for AI agents. Ships the framework-agnostic core (encode / navigate / verify, both TypeScript and Python against the shared conformance suite) and the Claude Agent SDK host adapter. The two Python packages (`halo-format`, `halo-format-claude`) release on the same version.

### Patch Changes

- Updated dependencies [27f2bbd]
  - @halo-format/halo@0.1.0
