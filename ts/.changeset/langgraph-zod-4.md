---
"@halo-format/langgraph": patch
---

Align the `zod` dependency to `^4.0.0` (was `^3.25.0`), matching `@halo-format/claude` and
the LangChain v1 ecosystem. The navigation tool's schema is built with zod, so it should
track the same major as the host.
