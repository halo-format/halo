# Halo raw-API trace — claim CLM-BIG — HALO
Runtime **raw_messages_api** · model **claude-sonnet-4-6** · adapter `halo_format_claude.raw.create_raw_halo` · alg `sha256` · threshold 2048 B
## Headline
- Encoded **4** large tool result(s) into content-addressed maps.
- Model saw **2,822 B** of shape maps instead of **133,166 B** of payload → **130,344 B kept out of context** (97.9% smaller).
- **3** halo_fetch call(s); every fetched handle re-verified on read.
- 150,085 tokens · $0.264 · 13 turns.

## Tool results — how Halo hashes each payload
### `payer_get_claim`  (map `CLM-BIG`)
- payload **3,411 B** → shape map **926 B** (**72.9%** smaller)
- root handle `h:41a7cd8f3dd0bf646a1aee6aa782eede7283d8c61116a9fb865bdfcb956711d5` · 12 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-BIG" — object, 11 fields from payer_get_claim, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-BIG.attachments  array[14]  [{"captured_at":"2026-01-16","documents_line":2,"image_bytes":20480,"kind":"pan…
  CLM-BIG.claim_number  string[6]  "CN-BIG"
  CLM-BIG.date_received  string[10]  "2026-06-01"
  CLM-BIG.diagnosis_codes  array[2]  ["K02.9","K04.0"]
  CLM-BIG.id  string[7]  "CLM-BIG"
  CLM-BIG.lines  array[3]  [{"allowed_cents":6500,"carc":"[]","charged_cents":6500,"claim_id":"CLM-BIG","d…
  CLM-BIG.member_id  string[8]  "MBR-PROF"
  CLM-BIG.place_of_service  string[2]  "11"
  CLM-BIG.provider_id  string[8]  "PRV-1001"
  CLM-BIG.status  string[6]  "pended"
  CLM-BIG.total_charged_cents  number  = 206500
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:41a7cd8f3dd0bf646a1aee6aa782eede7283d8c61116a9fb865bdfcb956711d5  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
  ✓ h:2e2c32a59662744a071afb3cda89fb303d83fe38f67eb132aa0ac1dc81e969a4  [leaf 2073B] [{"captured_at": "2026-01-16", "documents_line": 2, "image_bytes": 20480, "kind": "panoramic_xray", "modality": "intraoral", "ref": "ATT-BIG-01"}, {"captured_at": "2026-04-10", "documents_line": 3, "image_bytes": 36864, "kind": "bitewing_x…
  ✓ h:547970b079f932358097755e3fa8318f25330c3dba0e76bde5858a041e7da31c  [leaf 8B] CN-BIG
  ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
  ✓ h:ffbd59e989cefa47c50bf55efd6ee40a73aa9beebaebe566e490a1de19739062  [leaf 18B] ["K02.9", "K04.0"]
  ✓ h:1816eb849520e83598c0fbbefab74ef35c0de85f51c3fd9f3f923d0eedfa8276  [leaf 9B] CLM-BIG
  ✓ h:086cce6735e654abed0d377f83cd5c0e7c4c343594a93ebdfc5a1bc6daf07a98  [leaf 1068B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-BIG", "date_of_service": "2026-05-18", "id": "CLB-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_cod…
  ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
  ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
  ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
  ✓ h:13eeebe0695244bd58db615ef99f530105aeafe58a0e406a5834d4270c64704e  [leaf 8B] pended
  ✓ h:530d9995d8429b9e20b3dce374669f8728613c28f073ff91338de33de12e1462  [leaf 6B] 206500
```
- `payer_get_agent_provenance` → 208 B, below threshold, passed through.
- `payer_get_member_coverage` → 446 B, below threshold, passed through.
- `payer_check_network` → 92 B, below threshold, passed through.
### `payer_get_attachment`  (map `CLM-BIG`)
- payload **28,681 B** → shape map **632 B** (**97.8%** smaller)
- root handle `h:40495f0a1bc403117db75603fea7371421b67daa449bc3806030a980377a043c` · 22 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-BIG" — object, 2 fields from payer_get_attachment, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-BIG.payer_get_attachment  [branch] object{9}  ↳ attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  CLM-BIG.payer_get_claim  [branch] object{11}  ↳ attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, …
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:40495f0a1bc403117db75603fea7371421b67daa449bc3806030a980377a043c  [branch] 2 branches: payer_get_attachment, payer_get_claim
  ✓ h:85e66284f0666fc7718c9070424c4f76d2e529fc1f55c8a022ee6f983b672d66  [branch] 9 branches: attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  ✓ h:41a7cd8f3dd0bf646a1aee6aa782eede7283d8c61116a9fb865bdfcb956711d5  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
    ✓ h:3932914653d5590ecfaf50589f54696c4b97a34ec82a765a51684747d6bf9475  [leaf 12B] ATT-BIG-01
    ✓ h:edcc7adeb33a40068c3211f838e1a97bfaaaa5f58bf0668caa90718bde4e1b5e  [leaf 12B] 2026-01-16
    ✓ h:1816eb849520e83598c0fbbefab74ef35c0de85f51c3fd9f3f923d0eedfa8276  [leaf 9B] CLM-BIG
    ✓ h:28a20c402ecacba242364d94af2202fcb39addc360a711e9032642971814a227  [leaf 88B] Radiograph supports the proposed restoration; margins intact, no periapical pathology.
    ✓ h:c11ce811880ef05598a572a2b7676abd519df3faad8d54eab7846b17e3450d0a  [leaf 27310B] ycz8dx8/8vdgCmpDZ1vBONmQWdXDojbKX/6mXJwm/ULJzPx3Hz/y92AKakNnW8E42ZBZ1cOiNspf/qZcnCb9QsnM/HcfP/L3YApqQ2dbwTjZkFnVw6I2yl/+plycJv1Cycz8dx8/8vdgCmpDZ1vBONmQWdXDojbKX/6mXJwm/ULJzPx3Hz/y92AKakNnW8E42ZBZ1cOiNspf/qZcnCb9QsnM/HcfP/L3YApqQ2dbwTjZkFn…
    ✓ h:9a9c2e6f3ab87905374749180223a409c15bfbe69d025778d23242b23b8fa7e4  [leaf 53B] {"bytes": 20480, "dpi": 300, "modality": "intraoral"}
    ✓ h:74c2c6e3767955574f70c8e76e6e33c7a76c5962dd944a505c8e6e557a83b96a  [leaf 16B] panoramic_xray
    ✓ h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1  [leaf 531B] Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ h:740ee9ba091f5719c7673a2363e0df7d3ec3aecff14ae363571dae1de2b367dc  [leaf 512B] {"1": "missing", "10": "caries", "11": "caries", "12": "sound", "13": "restored", "14": "caries", "15": "restored", "16": "restored", "17": "restored", "18": "sound", "19": "caries", "2": "sound", "20": "caries", "21": "caries", "22": "sou…
    ✓ h:2e2c32a59662744a071afb3cda89fb303d83fe38f67eb132aa0ac1dc81e969a4  [leaf 2073B] [{"captured_at": "2026-01-16", "documents_line": 2, "image_bytes": 20480, "kind": "panoramic_xray", "modality": "intraoral", "ref": "ATT-BIG-01"}, {"captured_at": "2026-04-10", "documents_line": 3, "image_bytes": 36864, "kind": "bitewing_x…
    ✓ h:547970b079f932358097755e3fa8318f25330c3dba0e76bde5858a041e7da31c  [leaf 8B] CN-BIG
    ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
    ✓ h:ffbd59e989cefa47c50bf55efd6ee40a73aa9beebaebe566e490a1de19739062  [leaf 18B] ["K02.9", "K04.0"]
    ✓ h:086cce6735e654abed0d377f83cd5c0e7c4c343594a93ebdfc5a1bc6daf07a98  [leaf 1068B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-BIG", "date_of_service": "2026-05-18", "id": "CLB-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_cod…
    ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
    ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
    ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
    ✓ h:13eeebe0695244bd58db615ef99f530105aeafe58a0e406a5834d4270c64704e  [leaf 8B] pended
    ✓ h:530d9995d8429b9e20b3dce374669f8728613c28f073ff91338de33de12e1462  [leaf 6B] 206500
```
### `payer_get_attachment`  (map `CLM-BIG`)
- payload **50,537 B** → shape map **632 B** (**98.7%** smaller)
- root handle `h:258e658bc5b1c562308ab219ad230f06867c02d008232eaa247b6fcffbb9b0b2` · 22 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-BIG" — object, 2 fields from payer_get_attachment, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-BIG.payer_get_attachment  [branch] object{9}  ↳ attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  CLM-BIG.payer_get_claim  [branch] object{11}  ↳ attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, …
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:258e658bc5b1c562308ab219ad230f06867c02d008232eaa247b6fcffbb9b0b2  [branch] 2 branches: payer_get_attachment, payer_get_claim
  ✓ h:f64416d6f05851a3ff4e76fe2b0b4bfc762ae44098e636d42515fd78c72d6242  [branch] 9 branches: attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  ✓ h:41a7cd8f3dd0bf646a1aee6aa782eede7283d8c61116a9fb865bdfcb956711d5  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
    ✓ h:3dc59b5a9590a4ccca5c319749462e3605608ab8fbb059593ec9f01480de66e6  [leaf 12B] ATT-BIG-02
    ✓ h:2a1c1110801ce8452acc968c40c4ef680914d1ebf4975effc0fbe9380b188591  [leaf 12B] 2026-04-10
    ✓ h:1816eb849520e83598c0fbbefab74ef35c0de85f51c3fd9f3f923d0eedfa8276  [leaf 9B] CLM-BIG
    ✓ h:28a20c402ecacba242364d94af2202fcb39addc360a711e9032642971814a227  [leaf 88B] Radiograph supports the proposed restoration; margins intact, no periapical pathology.
    ✓ h:8fca5f011682652c8cca32360efe867e5ea0b336d43659262ab47545097a27cb  [leaf 49154B] tg8Jj+ncbgzKg5ag77zzWImPm0/vPcMF7Dhi20Z2tu+2DwmP6dxuDMqDlqDvvPNYiY+bT+89wwXsOGLbRna277YPCY/p3G4MyoOWoO+881iJj5tP7z3DBew4YttGdrbvtg8Jj+ncbgzKg5ag77zzWImPm0/vPcMF7Dhi20Z2tu+2DwmP6dxuDMqDlqDvvPNYiY+bT+89wwXsOGLbRna277YPCY/p3G4MyoOWoO+881iJj5t…
    ✓ h:6319e16905d6972db1e03d34280e725017c7e7c3deb6c1863d819bc441bd8d54  [leaf 53B] {"bytes": 36864, "dpi": 300, "modality": "intraoral"}
    ✓ h:af4cf4140c4f0bf232b1af7556b9667074432284f0ff67a9fbe402f4c465b570  [leaf 15B] bitewing_xray
    ✓ h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1  [leaf 531B] Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ h:e083cde754240ade2dfe1277c3cf706bd8dc012999d0929b67328abca0ff6366  [leaf 525B] {"1": "restored", "10": "restored", "11": "missing", "12": "caries", "13": "missing", "14": "sound", "15": "restored", "16": "caries", "17": "caries", "18": "missing", "19": "missing", "2": "sound", "20": "restored", "21": "caries", "22": …
    ✓ h:2e2c32a59662744a071afb3cda89fb303d83fe38f67eb132aa0ac1dc81e969a4  [leaf 2073B] [{"captured_at": "2026-01-16", "documents_line": 2, "image_bytes": 20480, "kind": "panoramic_xray", "modality": "intraoral", "ref": "ATT-BIG-01"}, {"captured_at": "2026-04-10", "documents_line": 3, "image_bytes": 36864, "kind": "bitewing_x…
    ✓ h:547970b079f932358097755e3fa8318f25330c3dba0e76bde5858a041e7da31c  [leaf 8B] CN-BIG
    ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
    ✓ h:ffbd59e989cefa47c50bf55efd6ee40a73aa9beebaebe566e490a1de19739062  [leaf 18B] ["K02.9", "K04.0"]
    ✓ h:086cce6735e654abed0d377f83cd5c0e7c4c343594a93ebdfc5a1bc6daf07a98  [leaf 1068B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-BIG", "date_of_service": "2026-05-18", "id": "CLB-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_cod…
    ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
    ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
    ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
    ✓ h:13eeebe0695244bd58db615ef99f530105aeafe58a0e406a5834d4270c64704e  [leaf 8B] pended
    ✓ h:530d9995d8429b9e20b3dce374669f8728613c28f073ff91338de33de12e1462  [leaf 6B] 206500
```
- `payer_check_network` → 94 B, below threshold, passed through.
- `payer_get_benefit_rules` → 687 B, below threshold, passed through.
- `payer_get_allowed_amount` → 92 B, below threshold, passed through.
- `payer_get_accumulators` → 125 B, below threshold, passed through.
- `payer_get_claim_history` → 722 B, below threshold, passed through.
- `payer_get_claim_history` → 423 B, below threshold, passed through.
- `payer_get_claim_history` → 419 B, below threshold, passed through.
### `payer_get_attachment`  (map `CLM-BIG`)
- payload **50,537 B** → shape map **632 B** (**98.7%** smaller)
- root handle `h:258e658bc5b1c562308ab219ad230f06867c02d008232eaa247b6fcffbb9b0b2` · 22 nodes · all verified: **True**

**Shape map the model saw:**

```
[halo] map "CLM-BIG" — object, 2 fields from payer_get_attachment, stored out of context. Pull only the fields you need with ONE halo_fetch call — batch every ref into that one call; each call is a round trip. A [branch] ref expands to its sub-refs when fetched; every other ref returns its value.
Fields:
  CLM-BIG.payer_get_attachment  [branch] object{9}  ↳ attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  CLM-BIG.payer_get_claim  [branch] object{11}  ↳ attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, …
```

**Content-addressed node tree (handle → kind → verified):**

```
✓ h:258e658bc5b1c562308ab219ad230f06867c02d008232eaa247b6fcffbb9b0b2  [branch] 2 branches: payer_get_attachment, payer_get_claim
  ✓ h:f64416d6f05851a3ff4e76fe2b0b4bfc762ae44098e636d42515fd78c72d6242  [branch] 9 branches: attachment_ref, captured_at, claim_id, findings, image_b64, image_meta, kind, narrative, tooth_chart
  ✓ h:41a7cd8f3dd0bf646a1aee6aa782eede7283d8c61116a9fb865bdfcb956711d5  [branch] 11 branches: attachments, claim_number, date_received, diagnosis_codes, id, lines, member_id, place_of_service, provider_id, status, total_charged_cents
    ✓ h:3dc59b5a9590a4ccca5c319749462e3605608ab8fbb059593ec9f01480de66e6  [leaf 12B] ATT-BIG-02
    ✓ h:2a1c1110801ce8452acc968c40c4ef680914d1ebf4975effc0fbe9380b188591  [leaf 12B] 2026-04-10
    ✓ h:1816eb849520e83598c0fbbefab74ef35c0de85f51c3fd9f3f923d0eedfa8276  [leaf 9B] CLM-BIG
    ✓ h:28a20c402ecacba242364d94af2202fcb39addc360a711e9032642971814a227  [leaf 88B] Radiograph supports the proposed restoration; margins intact, no periapical pathology.
    ✓ h:8fca5f011682652c8cca32360efe867e5ea0b336d43659262ab47545097a27cb  [leaf 49154B] tg8Jj+ncbgzKg5ag77zzWImPm0/vPcMF7Dhi20Z2tu+2DwmP6dxuDMqDlqDvvPNYiY+bT+89wwXsOGLbRna277YPCY/p3G4MyoOWoO+881iJj5tP7z3DBew4YttGdrbvtg8Jj+ncbgzKg5ag77zzWImPm0/vPcMF7Dhi20Z2tu+2DwmP6dxuDMqDlqDvvPNYiY+bT+89wwXsOGLbRna277YPCY/p3G4MyoOWoO+881iJj5t…
    ✓ h:6319e16905d6972db1e03d34280e725017c7e7c3deb6c1863d819bc441bd8d54  [leaf 53B] {"bytes": 36864, "dpi": 300, "modality": "intraoral"}
    ✓ h:af4cf4140c4f0bf232b1af7556b9667074432284f0ff67a9fbe402f4c465b570  [leaf 15B] bitewing_xray
    ✓ h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1  [leaf 531B] Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ h:e083cde754240ade2dfe1277c3cf706bd8dc012999d0929b67328abca0ff6366  [leaf 525B] {"1": "restored", "10": "restored", "11": "missing", "12": "caries", "13": "missing", "14": "sound", "15": "restored", "16": "caries", "17": "caries", "18": "missing", "19": "missing", "2": "sound", "20": "restored", "21": "caries", "22": …
    ✓ h:2e2c32a59662744a071afb3cda89fb303d83fe38f67eb132aa0ac1dc81e969a4  [leaf 2073B] [{"captured_at": "2026-01-16", "documents_line": 2, "image_bytes": 20480, "kind": "panoramic_xray", "modality": "intraoral", "ref": "ATT-BIG-01"}, {"captured_at": "2026-04-10", "documents_line": 3, "image_bytes": 36864, "kind": "bitewing_x…
    ✓ h:547970b079f932358097755e3fa8318f25330c3dba0e76bde5858a041e7da31c  [leaf 8B] CN-BIG
    ✓ h:8ed46f78a3b4525ad09e74baafb2010fa06cf4c4040be2ae982f4daff2bbb1e9  [leaf 12B] 2026-06-01
    ✓ h:ffbd59e989cefa47c50bf55efd6ee40a73aa9beebaebe566e490a1de19739062  [leaf 18B] ["K02.9", "K04.0"]
    ✓ h:086cce6735e654abed0d377f83cd5c0e7c4c343594a93ebdfc5a1bc6daf07a98  [leaf 1068B] [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-BIG", "date_of_service": "2026-05-18", "id": "CLB-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_cod…
    ✓ h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf  [leaf 10B] MBR-PROF
    ✓ h:25443f153a5956d53748b6ce723cd7be82ba711c9d7f37da569d5cd3a0c54ca8  [leaf 4B] 11
    ✓ h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8  [leaf 10B] PRV-1001
    ✓ h:13eeebe0695244bd58db615ef99f530105aeafe58a0e406a5834d4270c64704e  [leaf 8B] pended
    ✓ h:530d9995d8429b9e20b3dce374669f8728613c28f073ff91338de33de12e1462  [leaf 6B] 206500
```
- `payer_adjudicate_line` → 863 B, below threshold, passed through.
- `payer_adjudicate_line` → 902 B, below threshold, passed through.
- `payer_adjudicate_line` → 902 B, below threshold, passed through.
- `payer_lookup_reason_code` → 66 B, below threshold, passed through.
- `payer_record_decision` → 227 B, below threshold, passed through.
- `payer_request_review` → 422 B, below threshold, passed through.
- `payer_post_adjudication` → 427 B, below threshold, passed through.

## halo_fetch calls — verified navigation
- turn 2: fetch ["CLM-BIG.lines", "CLM-BIG.attachments", "CLM-BIG.member_id", "CLM-BIG.provider_id", "CLM-BIG.diagnosis_codes"]
    ✓ `CLM-BIG.lines` → `h:086cce6735e654abed0d377f83cd5c0e7c4c343594a93ebdfc5a1bc6daf07a98` (1068B): [{"allowed_cents": 6500, "carc": "[]", "charged_cents": 6500, "claim_id": "CLM-BIG", "date_of_service": "2026-05-18", "id": "CLB-1", "line_number": 1, "patient_resp_cents": 0, "plan_paid_cents": 6500, "preauth_number": null, "procedure_cod…
    ✓ `CLM-BIG.attachments` → `h:2e2c32a59662744a071afb3cda89fb303d83fe38f67eb132aa0ac1dc81e969a4` (2073B): [{"captured_at": "2026-01-16", "documents_line": 2, "image_bytes": 20480, "kind": "panoramic_xray", "modality": "intraoral", "ref": "ATT-BIG-01"}, {"captured_at": "2026-04-10", "documents_line": 3, "image_bytes": 36864, "kind": "bitewing_x…
    ✓ `CLM-BIG.member_id` → `h:d048994759a44b25f89545835bf713fbd4ccd0dd98b3e046d65ec6768d4fadcf` (10B): MBR-PROF
    ✓ `CLM-BIG.provider_id` → `h:bb1079d52b7be78ed024b4ed177249b37c24627d7c88a118b56f4d0e920605b8` (10B): PRV-1001
    ✓ `CLM-BIG.diagnosis_codes` → `h:ffbd59e989cefa47c50bf55efd6ee40a73aa9beebaebe566e490a1de19739062` (18B): ["K02.9", "K04.0"]
- turn 4: fetch ["CLM-BIG.payer_get_attachment.narrative", "CLM-BIG.payer_get_attachment.findings"]
    ✓ `CLM-BIG.payer_get_attachment.narrative` → `h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1` (531B): Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ `CLM-BIG.payer_get_attachment.findings` → `h:28a20c402ecacba242364d94af2202fcb39addc360a711e9032642971814a227` (88B): Radiograph supports the proposed restoration; margins intact, no periapical pathology.
- turn 6: fetch ["CLM-BIG.payer_get_attachment.narrative", "CLM-BIG.payer_get_attachment.findings", "CLM-BIG.payer_get_attachment.attachment_ref"]
    ✓ `CLM-BIG.payer_get_attachment.narrative` → `h:d21186ac0cde2782184e823de7699765ec662e5efb89759e367937231b4083e1` (531B): Patient presents for evaluation. Intraoral examination performed; findings documented per chart. Radiographic series reviewed and correlated with the clinical exam. Treatment plan discussed with the patient and informed consent obtained. N…
    ✓ `CLM-BIG.payer_get_attachment.findings` → `h:28a20c402ecacba242364d94af2202fcb39addc360a711e9032642971814a227` (88B): Radiograph supports the proposed restoration; margins intact, no periapical pathology.
    ✓ `CLM-BIG.payer_get_attachment.attachment_ref` → `h:3dc59b5a9590a4ccca5c319749462e3605608ab8fbb059593ec9f01480de66e6` (12B): ATT-BIG-02

## Per-turn API usage
- turn 1 (tool_use): in 401 / out 118 / cache_read 0 · tools: payer_get_claim, payer_get_agent_provenance
- turn 2 (tool_use): in 632 / out 132 / cache_read 3598 · tools: halo_fetch
- turn 3 (tool_use): in 2205 / out 411 / cache_read 3598 · tools: payer_get_member_coverage, payer_check_network, payer_get_attachment, payer_get_attachment
- turn 4 (tool_use): in 2726 / out 709 / cache_read 4083 · tools: payer_check_network, payer_get_benefit_rules, payer_get_allowed_amount, payer_get_accumulators, payer_get_claim_history, payer_get_claim_history, payer_get_claim_history, halo_fetch
- turn 5 (tool_use): in 2120 / out 398 / cache_read 4793 · tools: payer_get_attachment
- turn 6 (tool_use): in 306 / out 103 / cache_read 7545 · tools: halo_fetch
- turn 7 (tool_use): in 618 / out 671 / cache_read 7545 · tools: payer_adjudicate_line, payer_adjudicate_line, payer_adjudicate_line
- turn 8 (tool_use): in 2233 / out 101 / cache_read 9983 · tools: payer_lookup_reason_code
- turn 9 (tool_use): in 1706 / out 1889 / cache_read 10200 · tools: payer_record_decision
- turn 10 (tool_use): in 2104 / out 1509 / cache_read 11043 · tools: payer_record_decision
- turn 11 (tool_use): in 3378 / out 420 / cache_read 12638 · tools: payer_request_review
- turn 12 (tool_use): in 2167 / out 112 / cache_read 14427 · tools: payer_post_adjudication
- turn 13 (end_turn): in 822 / out 691 / cache_read 16192 · tools: —
