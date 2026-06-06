# Halo raw-API trace — claim CLM-PROF — HALO
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `halo_format_claude.raw.create_raw_halo` · alg `sha256` · threshold 2048 B
## Headline
- Encoded **2** large tool result(s) into content-addressed maps.
- Model saw **1,580 B** of shape maps instead of **39,331 B** of payload → **37,751 B kept out of context** (96.0% smaller).
- **2** halo_fetch call(s); every fetched handle re-verified on read.
- 141,322 tokens · $0.316407 · 13 turns.

## Tool results — how Halo hashes each payload
### `payer_get_claim`  (map `CLM-PROF`)
- payload **2,454 B** → shape map **945 B** (**61.5%** smaller)
- root handle `h:171833d881a2b5cd89bd4641dae55677565579690b78e12043c3bffb8c6f7a3e` · 12 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-PROF" — object, 11 fields from payer_get_claim, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-PROF.attachments  array[8]  [{"captured_at":"2026-02-15","documents_line":null,"image_bytes":20480,"kind":"…
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
✓ h:171833d881a2b5cd89bd4641dae55677565579690b78e12043c3bffb8c6f7a3e  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
  ✓ h:9e569e81d540666af674005d38c0be3ca3da93d4be4b7fd95318b0ad2462bbfc  [leaf 1147B] [{"captured_at": "2026-02-15", "documents_line": null, "image_bytes": 20480, "kind": "clinical_note", "modality": "intraoral", "ref": "ATT-1"}, {"captured_at": "2026-01-10", "documents_line": null, "image_bytes": 23552, "kind": "perio_char…
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
- `payer_check_network` → 90 B, below threshold, passed through.
- `payer_check_network` → 94 B, below threshold, passed through.
- `payer_get_benefit_rules` → 685 B, below threshold, passed through.
- `payer_get_allowed_amount` → 90 B, below threshold, passed through.
- `payer_get_accumulators` → 125 B, below threshold, passed through.
- `payer_get_claim_history` → 712 B, below threshold, passed through.
- `payer_get_claim_history` → 391 B, below threshold, passed through.
- `payer_get_claim_history` → 420 B, below threshold, passed through.
### `payer_get_attachment`  (map `CLM-PROF`)
- payload **36,877 B** → shape map **635 B** (**98.3%** smaller)
- root handle `h:4784f548c3e47e3b18edaf46dee48b6021cc856fe46b70a9fb44b929c1992293` · 22 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-PROF" — object, 2 fields from payer_get_attachment, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-PROF.payer_get_attachment  [branch] object{9}  ↳ attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  CLM-PROF.payer_get_claim  [branch] object{11}  ↳ attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, …
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:4784f548c3e47e3b18edaf46dee48b6021cc856fe46b70a9fb44b929c1992293  [branch] 2 branches: payer_get_attachment, payer_get_claim
  ✓ h:14e1400392cc22da9a5530fba728f70ec74b66fd27305a8be97aedf299c12e06  [branch] 9 branches: attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  ✓ h:171833d881a2b5cd89bd4641dae55677565579690b78e12043c3bffb8c6f7a3e  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
    ✓ h:357a838be1fb594810c8371f3f69fd73d016475c4a519a061e119db41aa3fda9  [leaf 7B] ATT-7
    ✓ h:2a1c1110801ce8452acc968c40c4ef680914d1ebf4975effc0fbe9380b188591  [leaf 12B] 2026-04-10
    ✓ h:1db709fd9ac321c7e0dd89a34bc9389338206218e2be21e9be22ff55c8f94b96  [leaf 10B] CLM-PROF
    ✓ h:ec26c71a2f79a37c0b5a5d8d6b3cecc58ccd4b63aaae88cc6cb819ba8e7153a5  [leaf 83B] Deep carious lesion approximating the pulp; crown indicated to restore the tooth.
    ✓ h:18e10079f7b9618cc3ac34156ef67d237e293c2b875d8fca840e6ef1d5eecba3  [leaf 35502B] 6S1J/fR9eEDcxhJxYngtN7LC+IZG2CadeuxBmkXLccvpLUn99H14QNzGEnFieC03ssL4hkbYJp167EGaRctxy+ktSf30fXhA3MYScWJ4LTeywviGRtgmnXrsQZpFy3HL6S1J/fR9eEDcxhJxYngtN7LC+IZG2CadeuxBmkXLccvpLUn99H14QNzGEnFieC03ssL4hkbYJp167EGaRctxy+ktSf30fXhA3MYScWJ4LTeywvi…
    ✓ h:b4e5dcf13fb7b2b494261965c7fbacb8f26ca7a0d787ff50592896086304d19a  [leaf 53B] {"bytes": 26624, "dpi": 300, "modality": "intraoral"}
    ✓ h:af4cf4140c4f0bf232b1af7556b9667074432284f0ff67a9fbe402f4c465b570  [leaf 15B] bitewing_xray
    ✓ h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1  [leaf 531B] Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ h:583807c62f7bc34385c67bc17296ed7233b3e3d8127cea50ffeff13b0879f944  [leaf 526B] {"1": "caries", "10": "missing", "11": "caries", "12": "sound", "13": "missing", "14": "sound", "15": "restored", "16": "caries", "17": "missing", "18": "sound", "19": "caries", "2": "missing", "20": "restored", "21": "missing", "22": "res…
    ✓ h:9e569e81d540666af674005d38c0be3ca3da93d4be4b7fd95318b0ad2462bbfc  [leaf 1147B] [{"captured_at": "2026-02-15", "documents_line": null, "image_bytes": 20480, "kind": "clinical_note", "modality": "intraoral", "ref": "ATT-1"}, {"captured_at": "2026-01-10", "documents_line": null, "image_bytes": 23552, "kind": "perio_char…
    ✓ h:468af4126202a71c9b2c5600281dc7e5b36739936d192ebf5bb47c8aaf43dcda  [leaf 9B] CN-PROF
    ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
    ✓ h:5f43a9f8b6df377b669722420392e448fde58e0757630b53081d86c0b86f6ebc  [leaf 19B] ["K02.9", "Z01.20"]
    ✓ h:df794649b8181886ebf7683afbe76c5d6f60b1f0c5eda97035bfe733730e430c  [leaf 1030B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-PROF", "date_of_service": "2026-04-10", "id": "CLP-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_co…
    ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
    ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
    ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
    ✓ h:38a83c28a8c824452e8c31a488bd8fe072c30a5ffde88dbd8f8b671c0a3027ae  [leaf 13B] adjudicated
    ✓ h:f4db1ec55a10f1decfa8845f322bdc0ff13f2c31d4bef2f15a90167ad63acabe  [leaf 5B] 36500
```
- `payer_adjudicate_line` → 864 B, below threshold, passed through.
- `payer_adjudicate_line` → 866 B, below threshold, passed through.
- `payer_adjudicate_line` → 900 B, below threshold, passed through.
- `payer_lookup_reason_code` → 66 B, below threshold, passed through.
- `payer_lookup_reason_code` → 78 B, below threshold, passed through.
- `payer_lookup_reason_code` → 115 B, below threshold, passed through.
- `payer_lookup_reason_code` → 46 B, below threshold, passed through.
- `payer_lookup_reason_code` → 47 B, below threshold, passed through.
- `payer_lookup_reason_code` → 48 B, below threshold, passed through.
- `payer_record_decision` → 228 B, below threshold, passed through.
- `payer_request_review` → 101 B, below threshold, passed through.
- `payer_post_adjudication` → 106 B, below threshold, passed through.

## halo_fetch calls — verified navigation
- turn 2: fetch ["CLM-PROF.lines", "CLM-PROF.member_id", "CLM-PROF.provider_id", "CLM-PROF.attachments", "CLM-PROF.diagnosis_codes"]
    ✓ `CLM-PROF.lines` → `h:df794649b8181886ebf7683afbe76c5d6f60b1f0c5eda97035bfe733730e430c` (1030B): [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-PROF", "date_of_service": "2026-04-10", "id": "CLP-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_co…
    ✓ `CLM-PROF.member_id` → `h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf` (10B): MBR-PROF
    ✓ `CLM-PROF.provider_id` → `h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8` (10B): PRV-1001
    ✓ `CLM-PROF.attachments` → `h:9e569e81d540666af674005d38c0be3ca3da93d4be4b7fd95318b0ad2462bbfc` (1147B): [{"captured_at": "2026-02-15", "documents_line": null, "image_bytes": 20480, "kind": "clinical_note", "modality": "intraoral", "ref": "ATT-1"}, {"captured_at": "2026-01-10", "documents_line": null, "image_bytes": 23552, "kind": "perio_char…
    ✓ `CLM-PROF.diagnosis_codes` → `h:5f43a9f8b6df377b669722420392e448fde58e0757630b53081d86c0b86f6ebc` (19B): ["K02.9", "Z01.20"]
- turn 6: fetch ["CLM-PROF.payer_get_attachment.narrative", "CLM-PROF.payer_get_attachment.findings"]
    ✓ `CLM-PROF.payer_get_attachment.narrative` → `h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1` (531B): Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ `CLM-PROF.payer_get_attachment.findings` → `h:ec26c71a2f79a37c0b5a5d8d6b3cecc58ccd4b63aaae88cc6cb819ba8e7153a5` (83B): Deep carious lesion approximating the pulp; crown indicated to restore the tooth.

## Per-turn API usage
- turn 1 (tool_use): in 401 / out 116 / cache_read 3598 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 631 / out 125 / cache_read 3598 · tools: halo_fetch
- turn 3 (tool_use): in 1789 / out 194 / cache_read 3598 · tools: payer_get_member_coverage, payer_check_network
- turn 4 (tool_use): in 1633 / out 663 / cache_read 4081 · tools: payer_check_network, payer_get_benefit_rules, payer_get_allowed_amount, payer_get_accumulators, payer_get_claim_history, payer_get_claim_history, payer_get_claim_history
- turn 5 (tool_use): in 1849 / out 467 / cache_read 4783 · tools: payer_get_attachment, payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 6 (tool_use): in 1852 / out 191 / cache_read 6466 · tools: halo_fetch, payer_lookup_reason_code, payer_lookup_reason_code
- turn 7 (tool_use): in 2353 / out 797 / cache_read 6466 · tools: payer_lookup_reason_code, payer_lookup_reason_code
- turn 8 (tool_use): in 1397 / out 101 / cache_read 8495 · tools: payer_lookup_reason_code, payer_lookup_reason_code
- turn 9 (tool_use): in 430 / out 1650 / cache_read 10371 · tools: payer_record_decision
- turn 10 (tool_use): in 1924 / out 1483 / cache_read 11519 · tools: payer_record_decision
- turn 11 (tool_use): in 3317 / out 413 / cache_read 11792 · tools: payer_request_review
- turn 12 (tool_use): in 12124 / out 173 / cache_read 0 · tools: payer_post_adjudication
- turn 13 (end_turn): in 680 / out 702 / cache_read 3598 · tools: —
