# Insurance Claim Decision Agent — LangGraph (Python)

A **LangGraph** port of the insurance-claim-decision-agent. It uses the prebuilt
tool-calling agent from LangChain v1 (`create_agent`, built on LangGraph) with
**Claude** via `ChatAnthropic`, over the **same deterministic engine, schema, and
human-review gate** as the other ports. Only the agent harness changes.

> **No Halo here on purpose.** The tools return plain JSON; this is the clean agent
> the **Halo LangGraph host adapter** attaches to (it keeps large tool results out
> of the model's context and records content-addressed evidence). `payer_get_claim`
> still returns the heavy claim — header + lines + bulky attachment bodies — so
> there's a real payload for that adapter to encode.

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

## Where Halo plugs in (for you)

The Halo LangGraph adapter wraps this agent at the **tool-result boundary** —
encode a large `ToolMessage` into a content-addressed store, hand the model a shape
map, and expose a `halo_fetch` tool — without touching the engine, the gate, or the
decision logic here. The `agent.halo_nodes` / `agent.halo_maps` tables in the schema
are already present for it to use.

## Layout

```
agent/
  main.py      create_agent runner (LangGraph) + token meter + --selftest
  tools.py     the 13 payer tools as LangChain @tool functions
  engine.py    the deterministic adjudication engine (shared, no LLM)
  prompts.py   system prompt (CLAUDE.md) + provenance hash
  db.py        asyncpg pool (least-privilege agent role)
db/            ext + agent schemas, role/grants, seed
scripts/       init_db.sh, reviewer_console.py
CLAUDE.md      the agent's operating manual (shared with the other ports)
```
