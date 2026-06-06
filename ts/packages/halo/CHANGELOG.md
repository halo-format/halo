# @halo-format/halo

## 0.2.0

## 0.1.1

### Patch Changes

- 77094e7: Split PyPI publishing into two per-package workflows (`publish-python-halo.yml`, `publish-python-claude.yml`) so each PyPI project has its own trusted publisher. They trigger automatically off the Release workflow via `workflow_run`, matching the npm flow. No source changes; the four packages stay on one shared version.

## 0.1.0

### Minor Changes

- 27f2bbd: Initial public release of Halo — content-addressed, navigable tool results for AI agents. Ships the framework-agnostic core (encode / navigate / verify, both TypeScript and Python against the shared conformance suite) and the Claude Agent SDK host adapter. The two Python packages (`halo-format`, `halo-format-claude`) release on the same version.
