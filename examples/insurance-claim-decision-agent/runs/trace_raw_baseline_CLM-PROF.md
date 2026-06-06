# Halo raw-API trace — claim CLM-PROF — BASELINE (no Halo)
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `None` · alg `sha256` · threshold 2048 B
## Headline
- **No Halo.** All **1** large tool result(s) (**11,916 B**) entered the model's context **in full** and were re-sent every subsequent turn.
- Nothing kept out of context; no content-addressed handles; no verified-on-read fetches.
- 104,617 tokens · $0.213767 · 10 turns.

## Tool results — full payloads in context (no Halo)
- `payer_get_claim` → **11,916 B** in context  ← LARGE, in context in full
- `payer_get_agent_provenance` → **208 B** in context
- `payer_get_member_coverage` → **446 B** in context
- `payer_check_network` → **96 B** in context
- `payer_check_network` → **94 B** in context
- `payer_get_benefit_rules` → **685 B** in context
- `payer_get_allowed_amount` → **90 B** in context
- `payer_get_accumulators` → **125 B** in context
- `payer_get_claim_history` → **388 B** in context
- `payer_get_claim_history` → **391 B** in context
- `payer_get_claim_history` → **420 B** in context
- `payer_adjudicate_line` → **864 B** in context
- `payer_adjudicate_line` → **866 B** in context
- `payer_adjudicate_line` → **900 B** in context
- `payer_lookup_reason_code` → **66 B** in context
- `payer_record_decision` → **220 B** in context
- `payer_post_adjudication` → **420 B** in context

## Per-turn API usage
- turn 1 (tool_use): in 400 / out 131 / cache_read 0 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 3837 / out 175 / cache_read 2654 · tools: payer_get_member_coverage, payer_check_network
- turn 3 (tool_use): in 4316 / out 373 / cache_read 2654 · tools: payer_check_network, payer_get_benefit_rules, payer_get_allowed_amount, payer_get_accumulators
- turn 4 (tool_use): in 1351 / out 302 / cache_read 3151 · tools: payer_get_claim_history, payer_get_claim_history, payer_get_claim_history
- turn 5 (tool_use): in 1766 / out 443 / cache_read 7028 · tools: payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 6 (tool_use): in 2665 / out 90 / cache_read 7543 · tools: payer_lookup_reason_code
- turn 7 (tool_use): in 1677 / out 1637 / cache_read 8439 · tools: payer_record_decision
- turn 8 (tool_use): in 1857 / out 1428 / cache_read 9531 · tools: payer_record_decision
- turn 9 (tool_use): in 3164 / out 116 / cache_read 11097 · tools: payer_post_adjudication
- turn 10 (end_turn): in 1797 / out 807 / cache_read 12634 · tools: —
