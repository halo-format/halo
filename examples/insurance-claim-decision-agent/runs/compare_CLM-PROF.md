# Halo on the raw Claude Messages API — CLM-PROF: baseline vs Halo

Same agent, same claim, same model (**claude-sonnet-4-6**), same tools — the only difference is whether the
published `halo_format_claude.raw` adapter sits in the tool-use loop.

| Metric | Baseline (no Halo) | Halo | Delta |
|---|--:|--:|--:|
| Total tokens | 104,617 | 90,803 | **−13,814 (13.2%)** |
| Cost (USD) | $0.213767 | $0.187285 | **−$0.026482 (12.4%)** |
| Turns | 10 | 11 | +1 |
| halo_fetch calls | 0 | 1 | — |
| Large `payer_get_claim` payload | 11,916 B | 11,916 B | same source |
| …bytes the model ingested for it | **11,916 B** (full) | **1,051 B** (shape map) | **−91.2%** |
| Content-addressed, verified-on-read | no | **yes (all nodes verified: True)** | — |

**Read it:** the big `payer_get_claim` payload (11,916 B — mostly clinical attachment
bodies) lands in context **in full** in the baseline and is re-sent every turn; under Halo the model sees a
1,051 B shape map and fetches only the ~1 KB of fields it needs, each verified against
its content hash. Net: **−13.2% tokens / −12.4% cost** on this small
claim — and the gap widens with payload size (heavier claims save far more).

Per-arm detail: `trace_raw_baseline_CLM-PROF.{json,md}` · `trace_raw_halo_CLM-PROF.{json,md}`.
