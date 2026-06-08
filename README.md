# Halo

**Hash-Addressed Lazy Objects** — a navigable, content-addressed result format for AI agents.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status: pre-1.0](https://img.shields.io/badge/status-pre--1.0-orange.svg)](#status)
[![TypeScript](https://img.shields.io/badge/TypeScript-reference-3178c6.svg)](ts/)
[![Python](https://img.shields.io/badge/Python-parity-3776ab.svg)](py/)

> A tool result has a **body** the model never sees and a **halo** that it does. The agent reads the
> halo, and reaches through to the body only when it needs it.

When a tool returns a large result, Halo encodes it into a small map of content-addressed nodes.
Only that map (the *halo*) enters the model's context; the full payload sits in a store the agent
can reach but the model does not read. The agent fetches individual fields on demand, and every
fetch is **verified against its content hash on read**. Because the navigation handle *is* the
integrity proof, the sequence of handles an agent touched is a tamper-evident record of exactly what
a decision used — an audit trail at near-zero marginal cost.

---

## Why

Most agents dump whole tool results into context as JSON. That has two costs:

- **Tokens.** A 50-row response sits in context for the rest of the run, repeating field names the
  model never needed and crowding out reasoning space.
- **Provenance.** The log shows that a tool returned data, not which parts a decision actually rested
  on. For anything that must be reconstructed later — a credit denial, a trade, a benefit refusal —
  that gap matters.

Compact formats (e.g. TOON) shrink the blob but still land it in context. Code-execution patterns
keep data out of context but treat that purely as a cost win, with nothing verifiable. **Halo unifies
the two:** the same content hash that keeps data out of context is also the integrity proof, so
*cheap* and *verifiable* are one act rather than two bolted together.

Halo assumes the agent runs somewhere with scratch space and can call `fetch`/`walk` (the
code-execution assumption). Plain prompt-loop agents with no runtime are out of scope — they should
use a compact in-context format instead.

## How it works

A node is either a **branch** (a summary plus named handles to children) or a **leaf** (a JSON
value). A handle is `"h:" + sha256(canonical(node))`, where `canonical` is RFC 8785 (JCS). Because a
branch hashes its children's handles, the root handle is a Merkle root over the whole value: change
any leaf and the root changes.

```ts
import { encode, open, MemoryStore } from "@halo-format/halo";

const store = new MemoryStore();

// Producer: encode a tool result into the store. The envelope is the whole "halo" —
// a summary plus named handles — and is the only thing that need enter the model's context.
const { envelope } = await encode(bureauReport, { store });
envelope.view.summary;   // e.g. "4 branches: debts, income, inquiries, tradelines"
envelope.view.branches;  // { income: "h:…", debts: "h:…", inquiries: "h:…", tradelines: "h:…" }

// Consumer: navigate by name; each fetch re-hashes the bytes and verifies before returning.
const nav    = await open(envelope, store);
const income = await nav.fetch("income");  // pull just this leaf
const debts  = await nav.fetch("debts");   // ...and this one
// inquiries and tradelines are never fetched — they stay out of context
```

Three layers, each depending only on the ones below — you adopt only as far up as you need:

| Layer | Adds | Who wants it |
|---|---|---|
| **L0** navigable result | summary + branches; lazy fetch | anyone paying for tokens |
| **L1** content-addressed | handles are content hashes; dedup, caching, integrity | anyone, for the git/IPFS reasons |
| **L2** signed + chained | tamper-evident audit log over touched handles | regulated / audited agents |

L0 and L1 are the core package. L2 ships separately and depends on the core, never the reverse.

## Use it with your agent SDK

Halo ships host adapters for three agent SDKs (TypeScript and Python each). Same core, one call to
wire in: the adapter encodes every large tool result and replaces it with a compact **shape map**
(root kind + per-field kind and bounded preview), and a single `halo_fetch` tool lets the model pull
back only the fields it needs, verified on read. They differ only in *where* they intercept:

| Host SDK | Packages (npm · PyPI) | Interception seam |
|---|---|---|
| Claude Agent SDK | `@halo-format/claude` · `halo-format-claude` | `PostToolUse` hook |
| LangChain / LangGraph | `@halo-format/langgraph` · `halo-format-langgraph` | `wrap_tool_call` middleware |
| OpenAI Agents SDK | `@halo-format/openai` · `halo-format-openai` | `call_model_input_filter` (Py) / model wrapper (TS) |

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";
import { installHalo } from "@halo-format/claude";

const { options } = installHalo(baseOptions, { threshold: 2048 });
for await (const msg of query({ prompt, options })) { /* … */ }
```

See each adapter's README ([Claude](ts/packages/claude), [LangGraph](ts/packages/langgraph),
[OpenAI](ts/packages/openai)) and the runnable examples below.

## Examples

Self-contained agents, each with an A/B harness comparing baseline (raw JSON) vs Halo (and, where
noted, the TOON compact format):

- **[examples/creditline-decision-agent](examples/creditline-decision-agent)** (Python) — a
  human-in-the-loop credit-line decision agent over a simulated bureau/Postgres world. The decision
  fetches only the few policy scalars it needs and provably never opens the tradeline bulk.
- **[examples/monitoring-agent](examples/monitoring-agent)** (TypeScript) — an on-call agent that
  triages Sentry-shaped issues, diagnoses against Datadog/Loki-shaped logs, and declares
  PagerDuty-shaped incidents through a human-gated tool layer.
- **insurance-claim adjudication agent** — the same deterministic claim-adjudication agent ported
  across host SDKs: [Claude](examples/insurance-claim-decision-agent),
  [LangGraph](examples/insurance-claim-langgraph), and the OpenAI Agents SDK
  ([Python](examples/insurance-claim-openai) · [TypeScript](examples/insurance-claim-openai-ts)).
  Each ships a self-contained big-payload A/B (`ab_big_payload`): the model answers from a few small
  clinical fields while a ~200KB `image_b64` blob never enters context. On the OpenAI Agents SDK port
  that one payload measured **≈99% (Python) / ≈98% (TypeScript) less context and cost**, with the
  identical decision — a single illustrative run; the deterministic per-payload reduction is the
  stable signal (see each port's README for methodology and caveats).

## Repository layout

```
conformance/   shared, language-neutral interop vectors — the spine
ts/            TypeScript workspace (pnpm) — reference implementation
py/            Python workspace — second target
skill/         the Halo Skill (navigation guidance + bundled helper)
examples/      runnable example agents with token A/B harnesses
```

### Packages

| Package | Ecosystem | What it is |
|---|---|---|
| `@halo-format/halo` | npm | Core: encode / navigate / verify; `MemoryStore` + `FileStore` |
| `@halo-format/claude` | npm | Host adapter for the Claude Agent SDK |
| `@halo-format/langgraph` | npm | Host adapter for LangChain / LangGraph |
| `@halo-format/openai` | npm | Host adapter for the OpenAI Agents SDK |
| `halo-format` | PyPI | Core (Python port) |
| `halo-format-claude` | PyPI | Host adapter for the Claude Agent SDK (Python port) |
| `halo-format-langgraph` | PyPI | Host adapter for LangChain / LangGraph (Python port) |
| `halo-format-openai` | PyPI | Host adapter for the OpenAI Agents SDK (Python port) |

Both ports produce **identical handles for identical input** — enforced by the shared conformance
vectors in [`conformance/`](conformance).

## Develop

The packages are pre-release; build and test from the monorepo.

**TypeScript** (Node 20+, pnpm):

```bash
cd ts
pnpm install
pnpm -r build
pnpm -r test        # unit + conformance vectors
pnpm -r typecheck
```

**Python** (3.10+):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e py/packages/halo -e py/packages/claude pytest
pytest py            # core + adapter unit tests + conformance vectors
```

The [`conformance/`](conformance) vectors are the interop contract: every port loads the same
`input -> canonical bytes -> handle` and `input -> envelope` vectors and asserts against them, so a
halo produced by one port verifies and navigates under the other. The vectors are weighted toward the
sharp edges — number formatting, unicode in keys/strings, empty containers, nesting depth, array
chunking boundaries.

## Status

Pre-1.0. The framework-agnostic core (encode / navigate / verify, both ports, against the shared
conformance suite) and three host adapters — Claude Agent SDK, LangChain / LangGraph, and the OpenAI
Agents SDK — are built, tested, and published (npm + PyPI). The format version is `1`, declared in
every envelope.

### Roadmap

- **Heavy store adapters** — Redis / Valkey and S3, for persistence across sessions.
- **More host adapters** — MCP producer middleware.
- **L2 audit chain** — signed, Merkle-linked log over the handles a run touched.
- **L2 audit chain** (`@halo-format/chain`) — signed, Merkle-linked record of touched handles.

These are planned; no package or stub exists until each is actually built.

## Design notes (v1)

- **Floats.** Non-integer floats are allowed in leaves; Halo leans on vetted JCS canonicalization
  libraries and covers number formatting heavily in the conformance vectors. (If you need maximal
  cross-language safety, prefer integers or decimal strings for money.)
- **Hash.** sha256, full 64-hex handles. The algorithm is declared per-tree in the envelope's `alg`
  and is pluggable behind a registry, so a future move (e.g. blake3) does not touch call sites.
- **The store is untrusted by design.** Every read re-hashes the bytes before use, so a buggy or
  hostile store cannot substitute data without detection — which is what lets the heavy store be a
  shared or remote service without widening the trust boundary.

## Contributing

Issues and pull requests are welcome. Two ground rules keep the format coherent:

1. **Don't break the conformance vectors.** They are the cross-language interop contract. If a change
   intentionally changes encoding, update the vectors and explain why.
2. **Keep dependencies strictly downward.** The core knows nothing about agents, MCP, or hooks;
   adapters depend on the core, never the reverse.

Run the relevant port's tests (above) before opening a PR. If your change should ship in a release,
add a changeset (`cd ts && pnpm changeset`) and commit it with your PR. All four packages move
together on one version and are published from CI; merging the generated "version packages" PR cuts
the release.

## License

[MIT](LICENSE) © the Halo authors
