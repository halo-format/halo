# Insurance Claim Decision Agent — LangGraph (Python)

A **LangGraph** port of the insurance-claim-decision-agent. It uses the prebuilt
tool-calling agent from LangChain v1 (`create_agent`, built on LangGraph) with
**Claude** via `ChatAnthropic`, over the **same deterministic engine, schema, and
human-review gate** as the other ports. Only the agent harness changes.

> **Halo is opt-in (`HALO=1`).** By default the tools return plain JSON — this is the
> clean baseline. `HALO=1` attaches the **Halo LangGraph host adapter** (it keeps large
> tool results out of the model's context and records content-addressed evidence), for
> an A/B. The claim API is REST-normalized: `payer_get_claim` returns a light attachment
> **manifest**, and the heavy clinical body — narrative/findings plus a bulky `image_b64`
> blob — is fetched on demand with `payer_get_attachment`, which is the real payload that
> adapter encodes. See the [Halo A/B](#halo-ab-halo1) section.

## How it's wired

```python
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from agent.tools import TOOLS            # 13 payer tools as @tool functions

model = ChatAnthropic(model="claude-sonnet-4-6", max_tokens=8000)
agent = create_agent(model, tools=TOOLS, system_prompt=SYSTEM_PROMPT)  # SYSTEM_PROMPT = CLAUDE.md
result = await agent.ainvoke({"messages": [{"role": "user", "content": prompt}]},
                             config={"recursion_limit": 120})
```

The 13 tools (`agent/tools.py`) are `langchain_core.tools.@tool` async functions that
wrap the SQL on `ext.*`/`agent.*`. `payer_adjudicate_line` runs the deterministic
engine (`agent/engine.py`); `payer_request_review` blocks on the `agent.approvals`
gate until a human resolves it; `payer_post_adjudication` writes the 835/EOB.

## Quick start

```bash
# 1. Postgres (database mimic_payer — shared with the other examples)
#    docker compose up -d   (see ../insurance-claim-decision-agent)

# 2. Deps + config
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e .
cp .env.example .env             # set ANTHROPIC_API_KEY, DB DSN

# 3. Schema + agent role + seed
set -a && . ./.env && set +a
bash scripts/init_db.sh

# 4a. No-API-key smoke test (tools + engine)
python -m agent.main CLM-PROF --selftest

# 4b. The agent (CLM-PROF auto-finalizes; CLM-1001 needs the examiner)
python -m agent.main CLM-PROF
#   for CLM-1001, in another shell: python -m scripts.reviewer_console auto
```

Each run writes `runs/<label>.json` (token usage from the message stream, estimated
cost, per-tool counts).

## Halo A/B (`HALO=1`)

The Halo LangGraph adapter wraps this agent at the **tool-result boundary** — a
`wrap_tool_call` middleware encodes a large `ToolMessage` into a content-addressed
store, hands the model a shape map, and exposes a `halo_fetch` tool — without
touching the engine, the gate, or the decision logic here.

```bash
HALO=1 python -m agent.main CLM-PROF          # Halo on  -> runs/halo.json
python -m agent.main CLM-PROF                 # baseline -> runs/baseline.json
```

`HALO=1` calls `halo_format_langgraph.install_halo(tools=TOOLS)`, appends `halo_fetch`
to the tools and the encode middleware to `create_agent`, and rides navigation guidance
in the system prompt (prompt mode). The payload it earns its keep on is the **on-demand
attachment body** from `payer_get_attachment` — narrative/findings the reviewer reads,
plus a bulky `image_b64` blob it never reads. Tune the encode floor with `HALO_THRESHOLD`
(default 2048 bytes). Add **`CACHE=1`** to turn on Anthropic prompt caching (off by default
in `ChatAnthropic`; applies to both arms — see `agent/caching.py`).

### Measured: where Halo wins, and the caching effect

Two A/Bs on `claude-sonnet-4-6`, against the seeded `CLM-BIG` claim (two crown lines that
require documentation review).

**1. Big payload, short read path** — `scripts/ab_big_payload.py` (self-contained, only an
API key): one ~270KB attachment, a question answerable from the small clinical fields.

| arm | context ingested | cost | tool calls |
|---|---|---|---|
| baseline | 238,457 tok | $0.72 | 1 |
| **halo** | **2,726 tok** | **$0.015** | 2 |

**~98% less** — identical answer. The model reads `kind`/`findings` from the shape map; the
200KB `image_b64` blob never enters context. (With `CACHE=1` it's still ~98%: caching can
even make baseline *worse* here — it pays the 1.25× write premium to cache a blob it reads
once.)

**2. Full adjudication loop** (`HALO=1` end-to-end on `CLM-BIG`, modest 2×~40KB bodies,
~20 tool calls):

| | baseline | halo | Δ |
|---|---|---|---|
| no caching | $1.53 | $1.79 | halo **+17%** |
| `CACHE=1` | $0.46 | $0.47 | halo **+2%** |

> **The honest picture.** Halo's reliable, deterministic win is the **per-payload context
> reduction** (table 1), and it dominates when the payload is large relative to the
> conversation. Across a *long* loop with *modest* payloads (table 2) it's a wash:
> without caching Halo's extra `halo_fetch` round trips cost more than the small blobs they
> remove (+17%); **prompt caching cuts both arms ~70% and closes the gap to ~break-even**
> (+2%), because once re-reads are cheap, neither carrying the blob (baseline) nor the extra
> turns (halo) costs much. Measure your own workload; lean on previews and a higher
> `HALO_THRESHOLD` to keep round trips down.

## Layout

```
agent/
  main.py      create_agent runner (LangGraph) + HALO toggle + token meter + --selftest
  tools.py     the 15 payer tools as LangChain @tool functions
  engine.py    the deterministic adjudication engine (shared, no LLM)
  prompts.py   system prompt (CLAUDE.md) + provenance hash
  db.py        asyncpg pool (least-privilege agent role)
db/            ext + agent schemas, role/grants, seed
scripts/       init_db.sh, reviewer_console.py
CLAUDE.md      the agent's operating manual (shared with the other ports)
```
