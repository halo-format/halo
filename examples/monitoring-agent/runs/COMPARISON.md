# Halo token comparison — monitoring agent (the decision point)

Same task ("triage open issues, diagnose the worst, declare an incident through
the human gate"), same model (`claude-sonnet-4-6`), same heavy environment (6
issues, full stacktrace/breadcrumbs/contexts per event, thousands of logs). All
arms reach the same decision: **declare P1 on the checkout issue (4502913)**.

## The integration (what changed vs. the credit example)

This is **our consumer-side adapter**, not the server's built-in Halo:

- The MCP server runs **RAW** in every arm (`MONITORING_HALO=0`) — every heavy
  read returns its full payload. No server code does Halo.
- The Halo arm wraps the agent's SDK options with **`@halo-format/claude`'s
  `installHalo`**: a `PostToolUse` hook encodes each raw tool result locally into
  a content-addressed map and exposes **one** in-process tool,
  `mcp__halo__halo_fetch`. There is no `halo_walk` — a ref that lands on a branch
  returns its sub-refs, so the single batch API both pulls leaves and expands.
- Instead of the raw envelope JSON, the model sees a **shape map**: the map id +
  root kind, then one line per field with its ref, kind (`[branch]` or a value),
  and a bounded preview. No 64-char hashes (the model navigates by `id.field`
  refs, resolved from the session, never by hash).

## Result (3 paired runs each, single-tool + shape-map fix)

> The previous adapter (two tools `halo_walk`/`halo_fetch`, hash-only envelope)
> ran **+73%** over baseline: the opaque envelope made the model guess the root
> kind, mis-fetch branches, and over-navigate. Collapsing to one `halo_fetch` and
> putting kinds + previews in the envelope removes the guessing — and reverses the
> regression to roughly break-even.

| metric | baseline (raw) | halo (our adapter) | Δ |
|---|---:|---:|---:|
| mean total tokens | **352,418** | **333,516** | **−5.4%** |
| total tokens range | 339,539–377,564 | 253,173–374,633 | |
| mean turns | 20.0 | 21.0 | +1.0 |
| `halo_fetch` calls / run | — | 1–2 | |

Per-run totals (`runs/ab_fixed.tsv`) — baseline: 339,539 / 340,151 / 377,564 ·
halo: 253,173 / 374,633 / 372,741.

**Halo is now break-even-to-better, no longer a regression.** The best halo run
(253 K, −25%) fetched once and searched logs twice — the shape-map previews
(`error_count = 44`, `by_service {checkout-api:44}`, the sample error message)
were enough to diagnose with almost no navigation. The spread is dominated by how
many `search_logs` the model chooses to run (2–4), which is model
non-determinism, not the adapter. The controlled, noise-free signal is the
per-payload reduction below.

## Deterministic per-payload (same data, three serializations — no run variance)

| tool result | JSON bytes | TOON | Halo shape map |
|---|---:|---:|---:|
| `list_open_issues` (uniform table) | 2,973 | 1,811 (**−39%**) | 592 (**−80%**) |
| `get_issue_detail` (nested events) | 9,876 | 10,835 (**+10%**) | 999 (**−90%**) |
| `search_logs` (logs w/ nested `attributes`) | 24,231 | 26,049 (**+8%**) | 694 (**−97%**) |

The shape map is *smaller* than the prior hash-only envelope (e.g. search_logs
694 B vs the old ~828–890 B) **and** carries previews — dropping the 64-char
handles more than paid for the hints. TOON delivers its advertised ~40% only on
the one flat, uniform array (`list_open_issues`); event detail and logs nest
(exception/stacktrace/breadcrumbs; per-row `attributes`), so TOON's indentation
overhead makes them **larger than JSON**, still fully in context. Halo is
shape-agnostic: it moves the body out of context either way.

## Third arm — TOON (the compact-serialization alternative)

| arm | total tokens | cost | turns |
|---|---:|---:|---:|
| baseline (raw JSON) | 352,418 (3-run mean) | $0.241 | 20 |
| TOON (compact, in-context) | 399,025 (1 run) | $0.240 | 22 |
| **Halo (our adapter)** | **333,516 (3-run mean)** | **$0.199** | 21 |

TOON came out *worse* than baseline on this workload — it inflated the two
heaviest payloads rather than shrinking them, and the data stays in context. All
three arms reached the **same correct decision** (P1 on the checkout issue;
`session.user` undefined at `checkout.js:88`; `backend@2026.6.3` regression; 412
users; null-guard + rollback) — so neither TOON nor Halo cost any accuracy.

## Why this is the decision point

Halo's saving is roughly *(bytes kept out of context) × (turns they'd persist)*,
minus navigation overhead (the `halo_fetch` round trips + the one tool schema).
Two things made the difference between the prior +73% and today's break-even:

1. **One tool, not two.** The model no longer spends turns choosing between walk
   and fetch or mis-routing a branch ref through the wrong tool.
2. **Previews answer in place.** A field's preview is often enough to decide
   without a fetch at all — every avoided round trip is a turn that doesn't
   re-read the prompt-cached prefix.

The rule still holds: the adapter pays off when tool results are large and the
model needs only parts of them, and there are several across a run. The fix
removed the self-inflicted overhead that was burying that payoff.
