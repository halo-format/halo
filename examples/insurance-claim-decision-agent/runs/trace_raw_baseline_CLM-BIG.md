# Halo raw-API trace — claim CLM-BIG — BASELINE (no Halo)
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `None` · alg `sha256` · threshold 2048 B
## Headline
- **No Halo.** All **3** large tool result(s) (**82,568 B**) entered the model's context **in full** and were re-sent every subsequent turn.
- Nothing kept out of context; no content-addressed handles; no verified-on-read fetches.
- 678,445 tokens · $0.852789 · 12 turns.

## Tool results — full payloads in context (no Halo)
- `payer_get_claim` → **3,350 B** in context  ← LARGE, in context in full
- `payer_get_agent_provenance` → **208 B** in context
- `payer_get_member_coverage` → **446 B** in context
- `payer_check_network` → **90 B** in context
- `payer_check_network` → **94 B** in context
- `payer_get_benefit_rules` → **687 B** in context
- `payer_get_accumulators` → **125 B** in context
- `payer_get_allowed_amount` → **92 B** in context
- `payer_get_claim_history` → **732 B** in context
- `payer_get_claim_history` → **398 B** in context
- `payer_get_claim_history` → **399 B** in context
- `payer_get_attachment` → **28,681 B** in context  ← LARGE, in context in full
- `payer_get_attachment` → **50,537 B** in context  ← LARGE, in context in full
- `payer_lookup_reason_code` → **45 B** in context
- `payer_lookup_reason_code` → **78 B** in context
- `payer_lookup_reason_code` → **70 B** in context
- `payer_lookup_reason_code` → **114 B** in context
- `payer_adjudicate_line` → **863 B** in context
- `payer_adjudicate_line` → **902 B** in context
- `payer_adjudicate_line` → **902 B** in context
- `payer_lookup_reason_code` → **66 B** in context
- `payer_lookup_reason_code` → **115 B** in context
- `payer_record_decision` → **227 B** in context
- `payer_request_review` → **422 B** in context
- `payer_post_adjudication` → **414 B** in context

## Per-turn API usage
- turn 1 (tool_use): in 400 / out 109 / cache_read 0 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 1590 / out 156 / cache_read 3092 · tools: payer_get_member_coverage, payer_check_network
- turn 3 (tool_use): in 2046 / out 379 / cache_read 3092 · tools: payer_check_network, payer_get_benefit_rules, payer_get_accumulators, payer_get_allowed_amount
- turn 4 (tool_use): in 1353 / out 509 / cache_read 3567 · tools: payer_get_claim_history, payer_get_claim_history, payer_get_claim_history, payer_get_attachment, payer_get_attachment
- turn 5 (tool_use): in 68953 / out 1002 / cache_read 5182 · tools: payer_lookup_reason_code, payer_lookup_reason_code, payer_lookup_reason_code, payer_lookup_reason_code, payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 6 (tool_use): in 1949 / out 146 / cache_read 6660 · tools: payer_lookup_reason_code, payer_lookup_reason_code
- turn 7 (tool_use): in 230 / out 2037 / cache_read 76188 · tools: payer_record_decision
- turn 8 (tool_use): in 2753 / out 1531 / cache_read 76188 · tools: payer_record_decision
- turn 9 (tool_use): in 3817 / out 1458 / cache_read 78183 · tools: payer_record_decision
- turn 10 (tool_use): in 3216 / out 397 / cache_read 80264 · tools: payer_request_review
- turn 11 (tool_use): in 2095 / out 122 / cache_read 82417 · tools: payer_post_adjudication
- turn 12 (end_turn): in 836 / out 743 / cache_read 84030 · tools: —
