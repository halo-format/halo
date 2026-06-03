// Bundled helper for the Halo skill (code-execution path only).
//
// Re-exports the @halo-format/halo core surface — encode / walk / fetch / fetchMany — defaulting
// to an in-process store, so a skill-loaded agent gets the light deployment with nothing to
// configure. This path is best-effort: it only fires if the model routes data through code. When
// the host can install a deterministic adapter (e.g. the Claude PostToolUse hook), use that for
// the plumbing and let the skill be guidance only.
//
// TODO: re-export from @halo-format/halo once the core is implemented.

export {};
