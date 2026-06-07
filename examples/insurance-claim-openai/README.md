# Insurance Claim Decision Agent — OpenAI Agents SDK (Python)

An **OpenAI Agents SDK** port of the insurance-claim-decision-agent. It uses a native
`Agent` + `Runner` loop against **`gpt-4.1`**, over the **same deterministic engine, schema,
and human-review gate** as the other ports. Only the agent harness changes.

> **Halo is opt-in (`HALO=1`).** By default the tools return plain JSON — the clean baseline.
> `HALO=1` attaches the **Halo OpenAI-Agents host adapter** (it keeps large tool results out
> of the model's context and records content-addressed evidence), for an A/B. The claim API is
> REST-normalized: `payer_get_claim` returns a light attachment **manifest**, and the heavy
> clinical body — narrative/findings plus a bulky `image_b64` blob — is fetched on demand with
> `payer_get_attachment`, which is the real payload that adapter encodes. See [Halo A/B](#halo-ab-halo1).

## How it's wired

```python
from agents import Agent, Runner, RunConfig
from agent.tools import TOOLS            # 15 payer tools as @function_tool functions

agent = Agent(name="insurance-claim-decision-agent", instructions=SYSTEM_PROMPT,
              tools=TOOLS, model="gpt-4.1")
result = await Runner.run(agent, prompt, max_turns=120)
```

The 15 tools (`agent/tools.py`) are plain async functions wrapped with the SDK's
`function_tool`; each wraps the SQL on `ext.*`/`agent.*`. `payer_adjudicate_line` runs the
deterministic engine (`agent/engine.py`); `payer_request_review` blocks on the
`agent.approvals` gate until a human resolves it; `payer_post_adjudication` writes the 835/EOB.

## Quick start

```bash
# 1. Postgres (database mimic_payer — shared with the other examples)
#    docker compose up -d   (see ../insurance-claim-decision-agent)

# 2. Deps + config
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .
cp .env.example .env             # set OPENAI_API_KEY, DB DSN

# 3. Schema + agent role + seed
set -a && . ./.env && set +a
bash scripts/init_db.sh

# 4a. No-API-key smoke test (tools + engine)
python -m agent.main CLM-PROF --selftest

# 4b. The agent (CLM-PROF auto-finalizes; CLM-1001 needs the examiner)
python -m agent.main CLM-PROF
#   for CLM-1001, in another shell: python -m scripts.reviewer_console auto
```

Each run writes `runs/<label>.json` (token usage from the run's usage accumulator, estimated
cost, per-tool counts).

## Halo A/B (`HALO=1`)

The Halo OpenAI-Agents adapter wraps this agent at the **model-input boundary** — a
`call_model_input_filter` encodes a large tool result into a content-addressed store, hands
the model a shape map, and exposes a `halo_fetch` tool — without touching the engine, the
gate, or the decision logic here.

```bash
HALO=1 python -m agent.main CLM-PROF          # Halo on  -> runs/halo.json
python -m agent.main CLM-PROF                 # baseline -> runs/baseline.json
```

`HALO=1` calls `halo_format_openai.install_halo(tools=TOOLS)`, appends `halo_fetch` to the
tools and puts the `call_model_input_filter` on the run, and rides navigation guidance in the
instructions (prompt mode). The payload it earns its keep on is the **on-demand attachment
body** from `payer_get_attachment` — narrative/findings the reviewer reads, plus a bulky
`image_b64` blob it never reads. Tune the encode floor with `HALO_THRESHOLD` (default 2048).

> **Why this host has no `CACHE` toggle.** The Anthropic-based ports add explicit prompt-cache
> breakpoints (`CACHE=1`); OpenAI caches the prompt prefix **automatically**, with no write
> premium, so the A/B is fair without a toggle. The meter still reports `cached_tokens`.

### Where Halo wins, and the honest picture

The reliable, deterministic win is the **per-payload context reduction**: when the model needs
a few small fields out of a large result, the blob never enters context. The self-contained
`scripts/ab_big_payload.py` isolates it (one ~200KB attachment, a question answerable from the
small fields — only an API key, no DB):

```bash
python -m scripts.ab_big_payload          # baseline vs halo on one big payload
```

Across a *long* adjudication loop with *modest* payloads it is closer to a wash: Halo's extra
`halo_fetch` round trips can offset the small blobs they remove, and OpenAI's automatic prefix
caching makes a carried blob cheap to re-read. Halo dominates when the payload is large
relative to the conversation; measure your own workload and lean on previews + a higher
`HALO_THRESHOLD` to keep round trips down.

> **The interception seam, and why it differs from the Claude/LangGraph ports.** The OpenAI
> Agents SDK has no tool-return output-replacement hook (lifecycle hooks are observational), so
> the adapter intercepts at `RunConfig.call_model_input_filter` — the one *generic* seam that
> rewrites the assembled model input before each model call, catching every tool. It's the same
> point in the pipeline as the Claude `PostToolUse` hook, expressed against the surface this SDK
> exposes. See `halo-format-openai`.

## Layout

```
agent/
  main.py      Agent + Runner runner (OpenAI Agents SDK) + HALO toggle + token meter + --selftest
  tools.py     the 15 payer tools as @function_tool functions
  engine.py    the deterministic adjudication engine (shared, no LLM)
  prompts.py   system prompt (CLAUDE.md) + provenance hash
  db.py        asyncpg pool (least-privilege agent role)
db/            ext + agent schemas, role/grants, seed
scripts/       init_db.sh, reviewer_console.py, ab_big_payload.py
CLAUDE.md      the agent's operating manual (shared with the other ports)
```
