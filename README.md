# Halo

**Hash-Addressed Lazy Objects** — a navigable, content-addressed result format for AI agents.

A tool result has a body the model never sees and a halo that it does. The agent reads the
halo, and reaches through to the body only when it needs it. Only the small map enters context;
individual leaves are fetched on demand and verified on read. Because the navigation handle is a
content hash, the sequence of handles the agent touched is a tamper-evident audit record at
near-zero marginal cost.

Org/repo: `halo-format/halo` · npm scope `@halo-format` · PyPI `halo-format`.

## Layout

```
conformance/   shared, language-neutral interop vectors — the spine
ts/            TypeScript workspace (pnpm) — reference implementation
py/            Python workspace — second target
skill/         the Halo Skill (navigation guidance + bundled helper)
private/       design docs + build plan
```

## Building now

- The core (`@halo-format/halo`) in TypeScript and Python.
- The shared conformance suite.
- The first host adapter, Claude (`@halo-format/claude`).
- The Halo Skill.

## Roadmap (not yet scaffolded)

- Heavy store adapters: Redis / Valkey and S3, for persistence across sessions.
- Additional host adapters: LangGraph (Python first), OpenAI Agents, MCP middleware.
- L2 audit chain (`@halo-format/chain`): signed, Merkle-linked record of touched handles.

These are coming, but no package or stub exists for them until they are actually built.

## v1 decisions

- **Floats:** non-integer floats are allowed in leaves; we lean on the vetted JCS libraries and
  cover number formatting heavily in conformance vectors.
- **Hash:** sha256, full 64-hex handles, algorithm declared per-tree in the envelope's `alg`.
