# Halo raw-API trace — claim CLM-PROF — BASELINE (no Halo)
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `None` · alg `sha256` · threshold 2048 B
## Headline
- **No Halo.** All **2** large tool result(s) (**48,032 B**) entered the model's context **in full** and were re-sent every subsequent turn.
- Nothing kept out of context; no content-addressed handles; no verified-on-read fetches.
- 320,272 tokens · $0.593632 · 10 turns.

## Tool results — full payloads in context (no Halo)
- `payer_get_claim` → **2,426 B** in context  ← LARGE, in context in full
- `payer_get_agent_provenance` → **208 B** in context
- `payer_get_member_coverage` → **446 B** in context
- `payer_check_network` → **90 B** in context
- `payer_check_network` → **94 B** in context
- `payer_get_benefit_rules` → **685 B** in context
- `payer_get_allowed_amount` → **90 B** in context
- `payer_get_accumulators` → **125 B** in context
- `payer_get_claim_history` → **722 B** in context
- `payer_get_claim_history` → **399 B** in context
- `payer_get_attachment` → **45,606 B** in context  ← LARGE, in context in full
- `payer_adjudicate_line` → **864 B** in context
- `payer_adjudicate_line` → **866 B** in context
- `payer_adjudicate_line` → **900 B** in context
- `payer_lookup_reason_code` → **66 B** in context
- `payer_record_decision` → **220 B** in context
- `payer_post_adjudication` → **420 B** in context

## Per-turn API usage
- turn 1 (tool_use): in 400 / out 129 / cache_read 3092 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 1205 / out 175 / cache_read 3092 · tools: payer_get_member_coverage, payer_check_network
- turn 3 (tool_use): in 1680 / out 373 / cache_read 3092 · tools: payer_check_network, payer_get_benefit_rules, payer_get_allowed_amount, payer_get_accumulators
- turn 4 (tool_use): in 1343 / out 334 / cache_read 3587 · tools: payer_get_claim_history, payer_get_claim_history, payer_get_attachment
- turn 5 (tool_use): in 40817 / out 510 / cache_read 4836 · tools: payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 6 (tool_use): in 41731 / out 94 / cache_read 5343 · tools: payer_lookup_reason_code
- turn 7 (tool_use): in 1682 / out 1651 / cache_read 6292 · tools: payer_record_decision
- turn 8 (tool_use): in 1868 / out 1544 / cache_read 46449 · tools: payer_record_decision
- turn 9 (tool_use): in 3360 / out 110 / cache_read 48020 · tools: payer_post_adjudication
- turn 10 (end_turn): in 1914 / out 658 / cache_read 49571 · tools: —
