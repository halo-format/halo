# Halo on the raw Claude Messages API — REST-correct tools, baseline vs Halo
Same agent, model **claude-sonnet-4-6**, same normalized tools. `payer_get_claim` returns an attachment *manifest* (refs, not bodies); a body is fetched with `payer_get_attachment` only when a line needs documentation review. Each body is large (a raw `image_b64`); for review the agent needs only `narrative`+`findings`. Both arms fetch the **same** bodies — Halo just slices them.
| Claim | Arm | tokens | cost | turns | attachment bodies fetched | bytes in context |
|---|---|--:|--:|--:|--:|--:|
| **CLM-PROF** | baseline | 320,272 | $0.593632 | 10 | 1 | 48,032 B |
| exam + cleaning + 1 filling (8 attachments) | **halo** | 141,322 | $0.316407 | 13 | 1 | 1,580 B |
| | **Δ** | **−55.9%** | **−46.7%** | | | **−96.7%** |
| **CLM-BIG** | baseline | 678,445 | $0.852789 | 12 | 2 | 82,568 B |
| exam + 2 crowns (14 attachments, 2 need documentation) | **halo** | 150,085 | $0.264 | 13 | 3 | 2,822 B |
| | **Δ** | **−77.9%** | **−69.0%** | | | **−96.6%** |

**The win scales with the bodies opened.** A small claim where the agent opens one supporting attachment saves ~half; a large claim that opens several saves ~three-quarters — because Halo keeps the raw image bulk out of context on every body the agent reviews, and the un-reviewed attachments are never fetched in either arm. Entity accumulation: each `payer_get_attachment` folds into the claim's own map (`<CLM>.payer_get_attachment.narrative`), keyed by `argJoin` on the claim id.
