# Halo token comparison — monitoring agent (the decision point)

Same task ("triage open issues, diagnose the worst, declare an incident through
the human gate"), same model (`claude-sonnet-4-6`), same heavy environment (6
issues, 11 events with full stacktrace/breadcrumbs/contexts, 1127 logs). Both
arms reach the same decision: **declare P1 on the checkout issue (4502913)**.

## The integration (what changed vs. the credit example)

This is **our consumer-side adapter**, not the server's built-in Halo:

- The MCP server runs **RAW** in both arms (`MONITORING_HALO=0`) — every heavy
  read returns its full payload. No server code does Halo.
- The Halo arm wraps the agent's SDK options with **`@halo-format/claude`'s
  `installHalo`**: a `PostToolUse` hook encodes each raw tool result locally into
  a content-addressed map and exposes in-process `mcp__halo__halo_walk` /
  `halo_fetch`. The model reads the envelope and fetches only the slices it needs.
- The server's own `halo_fetch`/`halo_fetch_many` are **disallowed** so the model
  navigates only through the adapter's tools (a first run without this confused
  the model into mixing the two toolsets — see note).

## Result (3 runs each, with the parseToolOutput fix)

> ⚠️ Correction. An earlier single pre-fix run showed Halo at −22%. That was a
> mirage: (1) before the `parseToolOutput` fix the adapter leaf-wrapped each MCP
> result, which *limited* navigation (one opaque fetch, fewer turns) and made the
> "broken" adapter look cheap; (2) it was one favourable baseline draw. With the
> fix (envelopes carve into fields) and 3 runs averaged, the picture reverses.

| metric | baseline (raw) | halo (our adapter) | Δ |
|---|---:|---:|---:|
| mean total tokens | **241,568** | **418,148** | **+73%** |
| mean cost (USD) | $0.160 | $0.228 | +43% |
| mean turns | 17.3 | 24.0 | +6.7 |

Per-run tokens — baseline: 233,574 / 232,356 / 258,774 · halo: 383,082 / 384,470 /
486,891 (`runs/ab_samples.tsv`).

**Halo costs more end-to-end here.** The fix made the adapter *correct* (field-level
carving), but a richer envelope invites the model to **navigate more** — several
`halo_fetch` calls over multiple fields, ~7 extra turns. In a prompt-cached loop
each extra turn re-reads the ~15–18 K-token cached prefix, so `cache_read` grows
faster than the per-payload context Halo removes. (Counter-intuitively, the
pre-fix leaf-wrapping was *cheaper* because it discouraged drilling in.)

## Third arm — TOON (the compact-serialization alternative)

TOON (`@toon-format/toon` v2.3.0) is the other camp: shrink the blob with a
YAML+CSV-style encoding, but keep it **in** context (no fetch). The server
serializes results as TOON (`MONITORING_FORMAT=toon`); no adapter.

**Deterministic per-payload (same data, three serializations — no run variance):**

| tool result | JSON bytes | TOON | Halo envelope |
|---|---:|---:|---:|
| `list_open_issues` (uniform table) | 2,919 | 1,756 (**−40%**) | 622 (−79%) |
| `get_issue_detail` (nested events) | 9,346 | 10,310 (**+10%**) | 940 (−90%) |
| `search_logs` (logs w/ nested `attributes`) | 23,535 | 25,468 (**+8%**) | 828 (−96%) |

TOON delivers its advertised ~40% **only on flat, uniform arrays**. The heavy
reads here are *not* flat — event detail nests exception/stacktrace/breadcrumbs;
each log row carries a nested `attributes` object — so TOON can't tabularize them
and its indentation overhead makes them **larger than JSON**, still fully in
context. Halo is shape-agnostic: it moves the body out of context either way
(−90% / −96% of what the model sees per payload).

**End-to-end (single runs, ~±15% variance — directional):**

| arm | total tokens | cost | turns | cache_read/turn |
|---|---:|---:|---:|---:|
| baseline (raw JSON) | 338,462 | $0.211 | 20 | 16,107 |
| TOON (compact, in-context) | 411,151 | $0.272 | 21 | 18,321 |
| **Halo (our adapter)** | **263,864** | **$0.202** | 19 | **12,911** |

TOON came out *worse* than baseline on this workload — it inflated the two
heaviest payloads rather than shrinking them, and the data stays in context. All
three arms reached the **same correct decision** (P1 on the checkout issue;
`session.user` undefined at `checkout.js:88`; `backend@2026.6.3` regression; 412
users; null-guard + rollback) — so neither TOON nor Halo cost any accuracy.

This is exactly Halo's design positioning: TOON makes the blob smaller (when it's
a uniform table) but leaves it in context; Halo keeps it out of context
regardless of shape. For nested, irregular tool results — logs, event detail —
TOON has little to give and Halo wins decisively.

## Why this is the decision point

Contrast the credit example (`../creditline-decision-agent/runs/COMPARISON.md`),
where Halo was ~break-even:

| | credit agent | monitoring agent |
|---|---|---|
| heavy payloads per run | one (a 9.5 KB bureau report) | several (log windows + full event detail) |
| share of per-turn prefix | ~13 % | large enough to move the total |
| per-turn context vs baseline | ≈ flat (−0.7 %) | **−20 %** |
| token outcome | ~break-even (slightly worse) | **−22 %** |

Halo's saving is roughly *(bytes kept out of context) × (turns they'd persist)*,
minus navigation overhead (the `halo_fetch` round trips + tool schemas). In the
credit loop a single modest, prompt-cached payload couldn't clear that overhead.
Here, **multiple genuinely heavy results** the model needs only slices of clear
it comfortably — per-turn context drops a fifth and stays down for the whole run.

So the decision rule: **the adapter pays off when tool results are large and the
model needs only parts of them, and there are several of them across a run.** For
small/single payloads in a prompt-cached loop, it's break-even and the value is
the verifiable fetch trail, not tokens.

## Note (fair-test fix)

The first Halo run came in at 484 K (worse) because the raw server still
advertised its own `halo_fetch`/`halo_fetch_many`; the model called those (empty
store → errors) before falling back to the adapter's tools, and passed raw
handles around. Disallowing the server's halo tools removed the mixup and is the
run reported above. Single-run variance is ~±15 %, but the per-turn cache_read
delta (−20 %) is the controlled signal and reflects the mechanism directly.
