# Halo token comparison — credit-line decision agent

Same request (`11111111…`, Dana Whitfield, $25k increase that escalates), same
flow (intake → bureau → policy → score → escalate → record → HITL gate → officer
modifies to $12k → notify), decision identical in every run (**APPROVED $12,000**,
`is_override=true`). The only variable is the Halo adapter (`HALO=1` →
`halo_format_claude.install_halo`). Model: `claude-opus-4-8`, thinking on,
prompt-caching on (SDK default).

Runfile was removed; `agent/main.py` now uses plain `query()` + an always-on
token meter (`runs/<label>.json`).

## Integration (how Halo is wired in)

Two surfaces, matching the design (`halo-claude-sdk-integration.md` §6 — plumbing
in the adapter, guidance in the Skill):

1. **Plumbing** — `halo_format_claude.install_halo(options)` adds a `PostToolUse`
   encode hook (large tool result → content-addressed envelope, the bulk held in
   a store) and an in-process MCP server exposing `halo_walk` / `halo_fetch`.
2. **Guidance** — the **halo Skill** (`.claude/skills/halo/SKILL.md`,
   navigation-only) is enabled via the SDK `skills` option **only on the Halo
   run** (`skills=[…, "halo"]`); the baseline lists `["intake","scoring",
   "decisioning"]` and never sees it, so the A/B stays clean. (Earlier drafts used
   a system-prompt addendum; that was replaced by the Skill.)

Confirmed in the Skill run: the model loaded the skills, walked the bureau branch,
then fetched exactly the five policy leaves via `halo_fetch` — decision unchanged.
One rough edge observed: the model first tried to `halo_fetch` the whole bureau
*branch* (a `WrongKind`), then `halo_walk`ed it and fetched the leaves — one wasted
round trip. The branch is also named after the full tool name
(`<mapId>.mcp__mimic-creditline__creditline_pull_bureau.credit_score`), which is
verbose. Both are navigation-overhead costs, not correctness issues.

Run-to-run token variance is high, so single-run deltas are directional only. Note
that §1's per-payload reduction is a clean measure of *what the hook does to one
tool result* — but, as §2 shows, it does **not** translate into a token/cost win
in this cached loop, because that payload is a small, cache-cheap slice of the
per-turn context that Halo refills with its own tool/skill overhead.

## 1. Deterministic mechanism proof (noise-free)

What the **bureau tool result** costs in the model's context, measured directly
(no model, no caching, no turn noise):

| | bytes in context |
|---|---|
| Baseline — full bureau JSON inlined | **9,469** |
| Halo — envelope (the map) | 2,126 |
| Halo — + the 5 policy leaves the agent fetched | +161 |
| **Halo — total in context** | **2,287** |
| **Reduction on this payload** | **−7,182 B (−75.8%)** |

The agent fetched exactly `credit_score=712`, `total_outstanding_debt=8000`,
`delinquencies_24m=0`, `hard_inquiries_6m=1`, `bureau_report_id` — and **never
pulled** the 26 tradelines, 7 inquiries, or public-records bulk. That is Halo's
worked example, reproduced: the decision names its basis as the specific leaves
it verifiably opened and proves it walked past the rest.

## 2. End-to-end A/B — Halo *engages* (realistic 9.5 KB bureau)

Both arms on the **same skills harness** (baseline `skills=["intake","scoring",
"decisioning"]`; halo adds the `halo` skill). Decision identical throughout.

| run | total tokens | cost | turns | navigation |
|---|---:|---:|---:|---|
| baseline | 272,528 | $0.315 | 12 | — |
| halo — *wrapped* (first cut) | 466,656 | $0.499 | 18 | ToolSearch ×3, **walk ×1, fetch ×2** + 1 wasted branch-fetch |
| **halo — *flat* (fixed)** | **290,280** | **$0.317** | **13** | ToolSearch ×1, **fetch ×1** |

The first cut wrapped every result under a `{tool_name: value}` branch, so the
envelope's top-level view showed only one branch (`…pull_bureau`) and hid the
fields. The model had to `halo_walk` into it (and first mis-fetched the branch)
before it could batch — **+71% tokens, +58% cost**.

**The fix** (`HaloSession`, both ports): encode a map's *first* result **flat**, so
the value's own fields (`credit_score`, `total_outstanding_debt`, …) are the
top-level branches and appear in the envelope directly; only namespace under the
tool name when a *second* result actually accumulates into the same entity map.
The model then batch-fetches the leaves straight from the envelope in **one
`halo_fetch`, no walk** — refs read cleanly as `<mapId>.credit_score`.

Result: the Halo run dropped **467 K → 290 K tokens (−38%)** and **$0.499 →
$0.317 (−36%)**, landing **~break-even with baseline** (+6% tokens, +0.6% cost).

### Why break-even — and why the §1 75.8% does NOT show up here

The per-turn context is nearly identical in both arms:

| | baseline | halo |
|---|---:|---:|
| cache_read **per turn** | ~21,174 | ~21,024 |
| turns | 12 | 13 |

So Halo barely changed how much context each turn carries (−0.7%), and the total
(`cache_read ≈ per-turn × turns`) is decided by **turn count** — Halo's one extra
navigation turn (the `halo_fetch` round trip) adds a full ~21 K re-read, which is
the entire +17.7 K gap.

The §1 reduction is real but doesn't translate, for three compounding reasons:

1. **The bureau is a small slice of the prefix.** Each turn re-sends ~21 K tokens
   — system prompt + CLAUDE.md + 3–4 skills + ~10 tool schemas + the growing
   reasoning transcript. The 9.5 KB bureau (~2,700 tokens) is only ~13 % of that.
2. **Halo backfills what it removes.** It takes the bureau out of the prefix but
   adds its own ~2,550 tokens to the *same* prefix — the `halo_walk` / `halo_fetch`
   tool schemas, the halo skill, and the fetched-leaf messages. Net per-turn
   change ≈ −150 tokens.
3. **Prompt caching already made the blob cheap.** A result sitting in context is
   cache-created once, then re-read at ~1/10th price — so removing it saves little
   in a cached loop.

Net: the 75.8 % cut of the *bureau result* is genuine, but it is a small,
already-cache-cheap slice that Halo refills with its own overhead, so per-turn
context is flat and the extra fetch turn makes Halo marginally worse. Run-to-run
variance is ~±15 %, so the two arms are effectively tied.

## 3. End-to-end A/B — Halo is *preempted* (69 KB bureau)

| metric | baseline-big | halo-big |
|---|---:|---:|
| total tokens | 357,805 | 389,842 |
| cost (USD) | $0.3879 | $0.4219 |
| halo maps encoded | — | **0** |

At 69 KB the **Claude CLI's own large-output handling** spills the tool result to
a file and the model reads it with `Bash`+`jq` (seen in both arms). The hook then
sees only a small file reference (< threshold) and passes through, so Halo never
engages (`maps_encoded: 0`). The CLI already does a form of context offloading at
that scale.

## Takeaways (honest)

1. **The integration works**: `install_halo` dropped in via the PostToolUse hook
   + in-process `halo_walk`/`halo_fetch`; the agent navigated halos and reached
   the identical, correct decision.
2. **Per tool result, Halo shrinks that result's context footprint** (−75.8%
   here) and yields a precise, verifiable record of which fields the decision used
   — but this does **not** reduce the *total per-turn context* (≈ flat at ~21 K
   tokens/turn), because the result is a small slice of a prefix dominated by the
   prompt + skills + tool schemas, and Halo backfills it with its own tool/skill
   text (see §2).
3. **Navigation shape matters as much as the payload.** The first cut wrapped
   each result under a tool-name branch, forcing a `halo_walk` and blowing the run
   to +71% tokens. Encoding the first result **flat** (fields top-level) let the
   model batch-fetch from the envelope in one call and brought Halo to
   **~break-even** with baseline (+6% tokens) — while still cutting the bureau's
   context footprint 75.8% and recording the exact fields used.
4. **In a prompt-cached CLI loop on a single modest payload, break-even is the
   ceiling**: caching already discounts the re-read blob, and the halo tools cost
   one ToolSearch (harness deferral, same as the mimic tools). This matches Halo's
   own design note — its token win needs larger/multiple payloads or caching off,
   where the −75.8% context cut dominates instead of being discounted.
5. **Halo's regime** is where it wins cleanly: many results / large payloads the
   model needs *few* fields from, with caching off or in the SDK adapter path
   (where the deterministic −75.8% context cut is the dominant effect), and where
   the verifiable fetch trail (the audit byproduct) is wanted. Note it overlaps
   the CLI's native file-spill above ~tens of KB.

Cross-run cost numbers carry prompt-cache-state noise; the §1 deterministic
measurement is the reliable signal of Halo's effect.

---

## Narrative: navigation shape is everything (verbatim note)

Case 2: end-to-end A/B where Halo actually engages
This is the practical case. Here the question is not “did Halo shrink the payload?” but “did the whole agent run get cheaper once you include the navigation machinery?” The answer is: only barely, and only after the flat fix.

The important thing here is that there are really two subcases.

wrapped first cut:
This version hid the actual useful fields one level down under the tool name. So the model could not immediately see credit_score, total_outstanding_debt, and the other policy fields in the envelope. It first had to navigate into the branch, which added extra calls and even caused one mistaken branch fetch. That is why this version explodes in tokens and cost. The lesson is that Halo is extremely sensitive to navigation shape. If the model has to “drill down” before it can ask for the real leaves, the saved payload bytes are eaten by extra turns.

flat fixed:
This version exposes the useful fields directly at the top level of the first map. That lets the model read the envelope, decide which five leaves matter, and fetch them in one batch. This is much healthier. It removes the wasted walk, removes the mistaken branch fetch, and cuts the Halo overhead enough to get close to baseline.
