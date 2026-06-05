# Insurance Claim Decision Agent

A human-in-the-loop **claim adjudication** agent built on the **Claude Agent
SDK**. It takes a submitted claim and decides each service line — **pay**,
**deny**, **reduce**, or **pend** for human review — with the patient
responsibility and the standard X12 reason codes (CARC/RARC). It acts only through
a **custom MCP server** (`mimic-payer`) backed by Postgres.

All claim / member / benefit / accumulator / network / fee-schedule data is
simulated in an `ext.*` schema shaped like the payer's systems and the X12
transactions (837 in, 835/EOB out, 270/271 eligibility). When you integrate later,
the tool bodies swap from SQL to the real feeds and **nothing above them changes**.

> This is a regulated money decision, which forces one rule that shapes the whole
> architecture:
>
> **The model orchestrates and reasons. A deterministic engine computes the money.
> A human owns every denial, reduction, or pend.**

The LLM gathers inputs, judges which rules apply, handles edge cases, and selects
reason codes from the standard set. It does **not** do benefit arithmetic and does
**not** invent codes — `payer_adjudicate_line` is a deterministic engine, not a
model call, and every adverse outcome routes to a human. And this is the agent
where verifiable evidence earns its place: every decision records the exact
content-addressed handles the data rested on, for appeals and regulatory review.

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  AGENT  (Claude Agent SDK)                                  │
│  Skills: intake-and-validate → coverage-and-rules →         │
│          adjudicate → explain-decision                      │
│  Reasoning + tool calls + the human review gate             │
└───────────────┬────────────────────────────────────────────┘
                │ MCP (stdio, domain tools)
                ▼
┌────────────────────────────────────────────────────────────┐
│  mimic-payer  (custom MCP server)                            │
│  read tools  → ext.*  (payer mirror / X12 shapes)            │
│  adjudicate_line → DETERMINISTIC engine (no LLM)             │
│  evidence    → agent.halo_nodes (content-addressed store)    │
│  write tools → agent.decisions + ext.claim_lines (gated)     │
│  → Postgres: mimic_payer (least-privilege payer_agent role)  │
└────────────────────────────────────────────────────────────┘
```

One Postgres, two schemas. `ext.*` stands in for the payer's claim, member,
benefit, accumulator, network, and fee-schedule systems, shaped like them and like
the X12 transactions. `agent.*` is the agent's own state — sessions, the
content-addressed evidence store, the human-review approvals, and the per-line
decision record — and never changes when you integrate.

## The MCP tools

| Tool | Purpose | readOnly |
|------|---------|:--------:|
| `payer_get_agent_provenance` | Canonical `prompt_version_hash` (sha256 over CLAUDE.md) | ✅ |
| `payer_get_claim`            | Claim header + lines + diagnosis + attachments (heavy, Halo) | ✅ |
| `payer_get_member_coverage`  | Member eligibility, effective dates, plan (270/271 later) | ✅ |
| `payer_get_benefit_rules`    | Per-code coverage %, frequency, waiting, preauth, category | ✅ |
| `payer_get_accumulators`     | Deductible met, annual max used, OOP met | ✅ |
| `payer_get_claim_history`    | Prior lines for frequency / duplicate checks (heavy, Halo) | ✅ |
| `payer_check_network`        | Provider in / out of network for a plan | ✅ |
| `payer_get_allowed_amount`   | Fee-schedule allowed amounts | ✅ |
| `payer_lookup_reason_code`   | CARC / RARC description (the agent selects, never invents) | ✅ |
| `payer_adjudicate_line`      | **Deterministic engine** — the money + evidence handles | ❌ |
| `payer_record_decision`      | Persist proposed per-line decisions + evidence | ❌ |
| `payer_request_review`       | Open the human review gate; **blocks** until resolved | ❌ |
| `payer_post_adjudication`    | Commit final decisions to `ext.claim_lines` (idempotent per line) | ❌ |

## The deterministic engine

`payer_adjudicate_line(claim_id, line_number)` fetches the adjudication inputs
itself (line, benefit rule, accumulators, fee schedule, network, plan) and runs
`mcp_servers/mimic_payer/engine.py` — **pure arithmetic and fixed rule
application, no model**: fee schedule → deductible → coinsurance (with the
out-of-network penalty) → annual-maximum cap. It returns the money, the
`suggested_carc`/`suggested_rarc` that explain each adjustment, a
`review_required` flag, and the **content-addressed handles** of every input it
touched. The model only names the line and reads the result — it never supplies an
input or computes an amount.

## Where Halo lands

- `payer_get_claim` is a header plus many lines plus diagnosis and **bulky
  clinical attachment bodies**; the agent fetches the line codes and amounts it is
  adjudicating and pulls attachments only if a line needs clinical review.
- `payer_get_claim_history` and the whole-plan `payer_get_benefit_rules` are large;
  Halo slices them to the codes relevant to this claim.
- And the part that matters most: **`agent.decisions.evidence` records the exact
  handles the decision rested on**. Because handles are content hashes and the
  store re-verifies on read, that evidence is tamper-evident — when a denial is
  appealed or a regulator asks how a decision was made, the answer is the specific
  data the agent adjudicated on, with proof it was not altered. The MCP server
  computes these handles with the published **`halo-format`** core, so they are
  byte-identical to the handles Halo navigates by.

## Quick start

```bash
# 1. Postgres (single engine; database mimic_payer). The example uses port 5433.
docker compose up -d

# 2. Python deps — installs the published Halo packages from PyPI alongside the SDK
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .

# 3. Config
cp .env.example .env            # defaults match docker-compose

# 4. Create the ext + agent schemas, the agent role, and seed data
set -a && . ./.env && set +a
bash scripts/init_db.sh

# 5a. Deterministic demo (no API key) — drives the real MCP tools + engine end to end
python -m scripts.run_demo

# 5b. Live, model-driven agent via the Claude Agent SDK
python -m agent.main CLM-1001
#   …in a second terminal, resolve the blocking review gate:
python -m scripts.reviewer_console        # or: python -m scripts.reviewer_console auto
```

### Run it via the Claude Code runtime

The project ships a native Claude Code setup, so you can drive the same agent
straight from the `claude` CLI — no Python entrypoint needed:

- `.mcp.json` registers the `mimic-payer` MCP server,
- `CLAUDE.md` is the agent's operating manual,
- `.claude/settings.json` enables the server and allow-lists its tools,
- `.claude/skills/` are loaded as Skills automatically.

```bash
set -a && . ./.env && set +a            # so the MCP server can reach Postgres

# one terminal: stand in for the claims examiner
python -m scripts.reviewer_console auto

# another terminal: run the agent
claude -p "Adjudicate insurance claim CLM-1001 end to end: decide each line
  (pay/deny/reduce/pend) with the deterministic engine and the standard reason
  codes, record with evidence, open the review gate, wait for the examiner, then
  post the adjudication and give the EOB explanation." --model claude-sonnet-4-6
```

This path is verified end to end: the model runs intake → coverage rules →
per-line engine adjudication → record → human review → post, producing the
mixed-outcome EOB below.

## The seeded demo claim

**CLM-1001 (Dana Whitfield)** has five lines engineered to sweep every outcome on
the Acme Dental PPO (annual max $1,500, $1,300 already used → $200 remaining):

| Line | Code | Service | Outcome | Why |
|------|------|---------|---------|-----|
| 1 | D1110 | prophylaxis | **pay** | preventive 100%, in network, within limits |
| 2 | D2391 | resin filling | **pay** | basic 80% — normal coinsurance is still a pay |
| 3 | D2740 | crown | **reduce** | major 50% share exceeds the $200 annual-max remaining (CARC 119) + fee-schedule write-off (CARC 45) |
| 4 | D4341 | perio scaling | **pend** | preauth required, none on the claim (CARC 197) |
| 5 | D9972 | external bleaching | **deny** | non-covered cosmetic (CARC 96) |

The claim total is above the auto-finalize ceiling and carries adverse lines, so
it goes to a human examiner, who confirms the proposed adjudication. A second
claim, **CLM-2001 (Marco Reyes)**, is two clean preventive lines below the ceiling
— the **auto-finalize** path with no human gate.

## Human-in-the-loop

`payer_request_review` creates a pending `agent.approvals` row and **blocks the
run** (polling) until a claims examiner resolves it out of band via
`scripts/reviewer_console.py`. The examiner can **confirm** (proposed stands),
**reject** (deny the lines), or **modify** (per-line overrides). A reject or modify
sets `is_override = true` — the appeal / audit evidence that a human owned the
adverse outcome. Only after resolution does `payer_post_adjudication` commit the
835/EOB to `ext.claim_lines` (idempotent per line, so a retry cannot pay twice).

## Token comparison with Halo

`agent/main.py` runs on plain `query()` with an always-on **token meter**: every
run prints a `TOKENS` summary and writes `runs/<label>.json`.

Set **`HALO=1`** to route every tool result through the Halo host adapter
([`halo_format_claude.install_halo`](../../py/packages/claude)). A `PostToolUse`
hook replaces a large tool result with a small **shape map** (root kind + per-field
kind and bounded preview), keeping the bulk out of context, and a single
`halo_fetch` tool pulls back only the fields the agent needs, verified on read.

```bash
# the Halo packages are installed by `uv pip install -e .` (PyPI). A/B the arms:
scripts/run_token_ab.sh baseline
scripts/run_token_ab.sh halo
```

Each run writes a token summary to `runs/<label>.json`. A live agent is
non-deterministic, so run each arm a few times and compare means.

### A measured profile (with vs without Halo)

`scripts/profile_ab.py` adjudicates the seeded **all-pay** profiling claim
`CLM-PROF` (no human gate, so both arms run unattended) and writes
`runs/prof_<label>.json` after every streamed message. Measured on
`claude-sonnet-4-6`, one run per arm:

| Arm | get_claim payload | total tokens | output | cache_read | turns | tool calls | halo_fetch |
|-----|------------------:|-------------:|-------:|-----------:|------:|-----------:|-----------:|
| baseline      | ~6.8 KB | 504,463 | 9,092 | 476,725 | 27 | 23 | 0 |
| **halo**      | ~6.8 KB | 617,486 | 9,791 | 589,481 | 31 | 27 | 1 |
| baseline_big  | ~56 KB  | 507,926 | 10,564 | 477,735 | 28 | 24 | 0 |
| **halo_big**  | ~56 KB  | 687,237 | 10,224 | 657,739 | 34 | 30 | 1 |

The deterministic part — **what enters the model's context for the one big
result** — is where Halo is unambiguous:

| `get_claim` | full payload | Halo shape map the model sees | reduction | attachment bulk kept out |
|-------------|-------------:|------------------------------:|:---------:|-------------------------:|
| small (8 attachments)  |  6,785 B | 1,040 B | **85%** |  5,398 B |
| big (40 attachments)   | 56,247 B |   936 B | **98%** | 54,526 B |

**How to read this honestly.** Halo cuts *per-result* context by 85–98% and the
agent provably fetches only `lines`, never the attachment bodies. But the
*end-to-end token count* in this runtime does **not** drop — it rises ~22–35% —
for two compounding reasons: (1) the cached prefix (CLAUDE.md + four Skills + the
13 tool schemas ≈ 480 K cache-read tokens) dwarfs any single claim, so the bytes
Halo saves are noise against it; and (2) the Claude Code CLI already spills large
tool results to scratch files on its own (note `baseline_big` ≈ `baseline`), so
Halo's encode hook is competing with built-in handling while adding navigation
turns (the extra `halo_fetch` + Skill/ToolSearch round-trips → +3–6 turns).

So in the Claude Code runtime, **adopt Halo here for the verifiable-evidence
property** — content-addressed, tamper-evident `agent.decisions.evidence`, which
is the entire point of a regulated adjudication agent — not as a token-reduction
play on a single modest claim. Halo's token win shows up where a result is both
large *and* in-context (no host spill) *and* the cached prefix is small relative
to it; scale `PROFILE_ATTACHMENTS` and shrink the prompt to move toward that
regime.

```bash
# reproduce (the seeded CLM-PROF auto-finalizes — no examiner needed):
HALO=0 RUN_LABEL=baseline python -m scripts.profile_ab CLM-PROF
HALO=1 RUN_LABEL=halo     python -m scripts.profile_ab CLM-PROF
# larger payload: re-seed with more attachments, then re-run
PROFILE_ATTACHMENTS=40 python -m db.seed.seed_payer
```

## Layout

```
agent/                      Claude Agent SDK runtime
  main.py                   registers the MCP server, loads skills, runs a claim
  prompts.py                system prompt + model/prompt provenance hash
.claude/skills/             Skills the SDK loads (intake/coverage/adjudicate/explain[/halo])
mcp_servers/mimic_payer/
  server.py                 the 13 MCP tools
  engine.py                 the deterministic adjudication engine (no LLM)
  models.py                 Pydantic tool contracts
  db.py                     asyncpg pool (least-privilege agent role)
db/                         ext + agent schemas, role/grants, seed
scripts/                    init_db.sh, run_demo.py, reviewer_console.py,
                            run_token_ab.sh, profile_ab.py (with/without-Halo A/B)
```

## The swap to real systems, later

You touch only the tool bodies: `payer_get_claim`/`payer_get_claim_history` → the
claims platform / 837 intake; `payer_get_member_coverage` → 270/271 eligibility;
`payer_get_benefit_rules`/`payer_get_allowed_amount`/`payer_check_network`/
`payer_get_accumulators` → the plan, fee-schedule, network, and accumulator
systems; `payer_post_adjudication` → 835 remittance / EOB generation.
`payer_adjudicate_line` does **not** swap — it is your own deterministic engine,
which is the point: the arithmetic is never delegated to an API or a model.
Everything above the tools — the skills, the review gate, `agent.*`, and Halo — is
untouched.
