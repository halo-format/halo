# Halo raw-API trace — claim CLM-PROF — HALO
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `halo_format_claude.raw.create_raw_halo` · alg `sha256` · threshold 2048 B
## Headline
- Encoded **1** large tool result(s) into content-addressed maps.
- Model saw **1,051 B** of shape maps instead of **11,916 B** of payload → **10,865 B kept out of context** (91.2% smaller).
- **1** halo_fetch call(s); every fetched handle re-verified on read.
- 90,803 tokens · $0.187285 · 11 turns.

## Tool results — how Halo hashes each payload
### `payer_get_claim`  (map `CLM-PROF`)
- payload **11,916 B** → shape map **1,051 B** (**91.2%** smaller)
- root handle `h:073d6edd712df5009edb3f7649b14c7f6ea2741a82a6d194c84e738e51ff04ef` · 13 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-PROF" — object, 12 fields from payer_get_claim, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-PROF.attachment_bodies  array[8]  [{"attachment_ref":"ATT-1","captured_at":"2026-01-17","image_meta":{"bytes":425…
  CLM-PROF.attachments  array[8]  ["ATT-1","ATT-2","ATT-3","ATT-4","ATT-5","ATT-6","ATT-7","ATT-8"]
  CLM-PROF.claim_number  string[7]  "CN-PROF"
  CLM-PROF.date_received  string[10]  "2026-06-01"
  CLM-PROF.diagnosis_codes  array[2]  ["K02.9","Z01.20"]
  CLM-PROF.id  string[8]  "CLM-PROF"
  CLM-PROF.lines  array[3]  [{"allowed_cents":6500,"carc":"[]","charged_cents":6500,"claim_id":"CLM-PROF","…
  CLM-PROF.member_id  string[8]  "MBR-PROF"
  CLM-PROF.place_of_service  string[2]  "11"
  CLM-PROF.provider_id  string[8]  "PRV-1001"
  CLM-PROF.status  string[11]  "adjudicated"
  CLM-PROF.total_charged_cents  number  = 36500
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:073d6edd712df5009edb3f7649b14c7f6ea2741a82a6d194c84e738e51ff04ef  [branch] 12 branches: attachment_bodies, attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
  ✓ h:f0811c323bda8f6d03aff462fc010998adfd2936a0e9193ac952fa9ad959c44c  [leaf 10514B] [{"attachment_ref": "ATT-1", "captured_at": "2026-01-17", "image_meta": {"bytes": 425989, "dpi": 300, "modality": "intraoral"}, "kind": "clinical_note", "narrative": "Patient presents for evaluation. Intraoral examination performed; findin…
  ✓ h:f38cb44a30ece5cdefa54a14a8e16677aa2868cb6b0c7a59bd386ab086c8c0b7  [leaf 72B] ["ATT-1", "ATT-2", "ATT-3", "ATT-4", "ATT-5", "ATT-6", "ATT-7", "ATT-8"]
  ✓ h:468af4126202a71c9b2c5600281dc7e5b36739936d192ebf5bb47c8aaf43dcda  [leaf 9B] CN-PROF
  ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
  ✓ h:5f43a9f8b6df377b669722420392e448fde58e0757630b53081d86c0b86f6ebc  [leaf 19B] ["K02.9", "Z01.20"]
  ✓ h:1db709fd9ac321c7e0dd89a34bc9389338206218e2be21e9be22ff55c8f94b96  [leaf 10B] CLM-PROF
  ✓ h:df794649b8181886ebf7683afbe76c5d6f60b1f0c5eda97035bfe733730e430c  [leaf 1030B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-PROF", "date_of_service": "2026-04-10", "id": "CLP-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_co…
  ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
  ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
  ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
  ✓ h:38a83c28a8c824452e8c31a488bd8fe072c30a5ffde88dbd8f8b671c0a3027ae  [leaf 13B] adjudicated
  ✓ h:f4db1ec55a10f1decfa8845f322bdc0ff13f2c31d4bef2f15a90167ad63acabe  [leaf 5B] 36500
```
- `payer_get_agent_provenance` → 208 B, below threshold, passed through.
- `payer_get_member_coverage` → 446 B, below threshold, passed through.
- `payer_check_network` → 96 B, below threshold, passed through.
- `payer_check_network` → 94 B, below threshold, passed through.
- `payer_get_benefit_rules` → 685 B, below threshold, passed through.
- `payer_get_accumulators` → 125 B, below threshold, passed through.
- `payer_get_allowed_amount` → 90 B, below threshold, passed through.
- `payer_get_claim_history` → 388 B, below threshold, passed through.
- `payer_get_claim_history` → 391 B, below threshold, passed through.
- `payer_get_claim_history` → 420 B, below threshold, passed through.
- `payer_adjudicate_line` → 864 B, below threshold, passed through.
- `payer_adjudicate_line` → 866 B, below threshold, passed through.
- `payer_adjudicate_line` → 900 B, below threshold, passed through.
- `payer_lookup_reason_code` → 66 B, below threshold, passed through.
- `payer_record_decision` → 220 B, below threshold, passed through.
- `payer_post_adjudication` → 420 B, below threshold, passed through.

## halo_fetch calls — verified navigation
- turn 2: fetch ["CLM-PROF.lines", "CLM-PROF.member_id", "CLM-PROF.provider_id", "CLM-PROF.diagnosis_codes"]
    ✓ `CLM-PROF.lines` → `h:df794649b8181886ebf7683afbe76c5d6f60b1f0c5eda97035bfe733730e430c` (1030B): [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-PROF", "date_of_service": "2026-04-10", "id": "CLP-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_co…
    ✓ `CLM-PROF.member_id` → `h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf` (10B): MBR-PROF
    ✓ `CLM-PROF.provider_id` → `h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8` (10B): PRV-1001
    ✓ `CLM-PROF.diagnosis_codes` → `h:5f43a9f8b6df377b669722420392e448fde58e0757630b53081d86c0b86f6ebc` (19B): ["K02.9", "Z01.20"]

## Per-turn API usage
- turn 1 (tool_use): in 401 / out 131 / cache_read 0 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 1134 / out 111 / cache_read 3091 · tools: halo_fetch
- turn 3 (tool_use): in 1351 / out 153 / cache_read 3091 · tools: payer_get_member_coverage, payer_check_network
- turn 4 (tool_use): in 1102 / out 359 / cache_read 3589 · tools: payer_check_network, payer_get_benefit_rules, payer_get_accumulators, payer_get_allowed_amount
- turn 5 (tool_use): in 1335 / out 298 / cache_read 4336 · tools: payer_get_claim_history, payer_get_claim_history, payer_get_claim_history
- turn 6 (tool_use): in 1762 / out 560 / cache_read 4959 · tools: payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 7 (tool_use): in 2782 / out 76 / cache_read 5458 · tools: payer_lookup_reason_code
- turn 8 (tool_use): in 1663 / out 1570 / cache_read 6350 · tools: payer_record_decision
- turn 9 (tool_use): in 1790 / out 1435 / cache_read 7559 · tools: payer_record_decision
- turn 10 (tool_use): in 3211 / out 110 / cache_read 9111 · tools: payer_post_adjudication
- turn 11 (end_turn): in 1801 / out 624 / cache_read 10581 · tools: —
