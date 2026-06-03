"""Bundled helper for the Halo skill (code-execution path only), Python agents.

Re-exports the halo_format core surface — encode / walk / fetch / fetch_many — defaulting to an
in-process store, so a skill-loaded agent gets the light deployment with nothing to configure.
Same best-effort caveat as halo.ts: prefer a deterministic host adapter where one exists, and let
the skill be guidance only.

TODO: re-export from halo_format once the core is implemented.
"""
