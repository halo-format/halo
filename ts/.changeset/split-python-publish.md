---
"@halo-format/halo": patch
"@halo-format/claude": patch
---

Split PyPI publishing into two per-package workflows (`publish-python-halo.yml`, `publish-python-claude.yml`) so each PyPI project has its own trusted publisher. They trigger automatically off the Release workflow via `workflow_run`, matching the npm flow. No source changes; the four packages stay on one shared version.
